"""Descărcare pagini + extragere preț.

De ce e rapid / robust:
- curl_cffi imită amprenta TLS a lui Chrome -> mult mai puține 403 (Cloudflare/Akamai) decât requests.
- totul e asincron: zeci de produse se verifică în paralel, cu limită per domeniu.
- selectolax e de ~10-30x mai rapid decât BeautifulSoup la parsare.
- prețul se caută în cascadă: selector CSS (dacă l-ai dat) -> JSON-LD (schema.org)
  -> meta/microdata -> JSON din <script> -> browser real (opțional).
  Pentru majoritatea magazinelor NU mai e nevoie de selector.
"""
import asyncio
import json
import logging
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlsplit

from curl_cffi.requests import AsyncSession
from selectolax.lexbor import LexborHTMLParser as HTMLParser

import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------- parsare preț

# Grupuri de mii de exact 3 cifre ("1.299", "1 299", "1,299") + zecimale de 1-2 cifre.
_PRICE_RE = re.compile(
    r"\d{1,3}(?:[ .,'  ]\d{3})+(?:[.,]\d{1,2})?(?!\d)"
    r"|\d+(?:[.,]\d{1,2})?(?!\d)"
)
_DECIMALS_RE = re.compile(r"[.,](\d{1,2})$")
_CURRENCIES = {"lei": "RON", "ron": "RON", "€": "EUR", "eur": "EUR", "$": "USD", "usd": "USD", "£": "GBP"}


def parse_price(raw):
    """'1.299,99 Lei' / '1,299.99' / '1 299' / 49.9 -> float. None dacă nu e preț valid."""
    if isinstance(raw, (int, float)):
        return float(raw) if raw > 0 else None
    if not raw:
        return None
    m = _PRICE_RE.search(str(raw))
    if not m:
        return None
    s = m.group()
    dec = _DECIMALS_RE.search(s)
    if dec:
        value = float(re.sub(r"\D", "", s[: dec.start()]) + "." + dec.group(1))
    else:
        value = float(re.sub(r"\D", "", s))
    return value if value > 0 else None


def guess_currency(text):
    low = (text or "").lower()
    return next((code for sym, code in _CURRENCIES.items() if sym in low), None)


# ---------------------------------------------------------------- extragere


@dataclass
class ScrapeResult:
    price: float | None = None
    currency: str | None = None
    in_stock: bool | None = None
    title: str | None = None
    method: str | None = None
    error: str | None = None


def _stock_from(value):
    if not value:
        return None
    v = str(value).lower()
    if "outofstock" in v or "soldout" in v or "discontinued" in v:
        return False
    if "instock" in v or "preorder" in v or "limitedavailability" in v:
        return True
    return None


def _walk_json(node):
    """Parcurge recursiv un obiect JSON-LD (inclusiv @graph și liste)."""
    if isinstance(node, list):
        for item in node:
            yield from _walk_json(item)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "mainEntity", "itemListElement", "hasVariant"):
            if key in node:
                yield from _walk_json(node[key])


def _from_offers(offers):
    """Primul Offer/AggregateOffer cu preț valid."""
    for offer in _walk_json(offers):
        price = offer.get("price") or offer.get("lowPrice")
        if price is None and isinstance(offer.get("priceSpecification"), dict):
            price = offer["priceSpecification"].get("price")
        price = parse_price(price)
        if price:
            return price, offer.get("priceCurrency"), _stock_from(offer.get("availability"))
    return None


def _extract_jsonld(tree):
    for script in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.text(), strict=False)
        except (ValueError, TypeError):
            continue
        for node in _walk_json(data):
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if not any(t in ("Product", "ProductGroup", "IndividualProduct") for t in types):
                continue
            found = _from_offers(node.get("offers"))
            if found:
                return ScrapeResult(*found, title=node.get("name"), method="json-ld")
    return None


def _attr_or_text(node):
    return node.attributes.get("content") or node.attributes.get("value") or node.text(strip=True)


def _extract_meta(tree):
    for sel in (
        'meta[property="product:price:amount"]',
        'meta[property="og:price:amount"]',
        '[itemprop="price"]',
        'meta[name="twitter:data1"]',
    ):
        node = tree.css_first(sel)
        price = parse_price(_attr_or_text(node)) if node else None
        if price:
            cur = tree.css_first(
                'meta[property="product:price:currency"], meta[property="og:price:currency"], [itemprop="priceCurrency"]'
            )
            avail = tree.css_first('[itemprop="availability"], meta[property="product:availability"]')
            return ScrapeResult(
                price,
                _attr_or_text(cur) if cur else None,
                _stock_from(avail.attributes.get("href") or _attr_or_text(avail)) if avail else None,
                method="meta",
            )
    return None


def _price_from_node(node):
    # Magento & co țin prețul curat în atribute.
    for attr in ("data-price-amount", "data-price", "content"):
        price = parse_price(node.attributes.get(attr))
        if price:
            return price, None
    # eMAG & co: "1.299<sup>99</sup> Lei" -> zecimalele sunt în <sup>.
    text = node.text(separator=" ", strip=True)
    sup = node.css_first("sup")
    if sup:
        decimals = re.sub(r"\D", "", sup.text())
        main = _PRICE_RE.search(text.replace(sup.text(), " ", 1))
        if main and decimals:
            return parse_price(f"{main.group()},{decimals}"), guess_currency(text)
    return parse_price(text), guess_currency(text)


def _extract_css(tree, selector, method="css"):
    for node in tree.css(selector)[:3]:
        price, currency = _price_from_node(node)
        if price:
            return ScrapeResult(price, currency, method=method)
    return None


# Selectori folosiți de multe magazine (Magento, WooCommerce, eMAG, AboutYou, ...).
COMMON_SELECTORS = ", ".join([
    '[data-testid="finalPrice"]',
    '[data-price-type="finalPrice"]',
    ".product-new-price",
    ".product-info-main .price",
    ".summary .price ins .amount",
    ".summary .price .amount",
    '[data-testid="product-price"]',
    ".product-price-value",
    ".current-price",
    ".price-current",
])


def _extract_known_scripts(tree):
    """Formate de date cunoscute din <script>. (Nu căutăm orbește "price": pagina are
    și produse recomandate, iar așa am lua prețul altui produs.)"""
    for script in tree.css("script"):
        text = script.text()
        # PlayBike: window['plyPageData'] = {... "price": 12999 ...} în bani
        if text and "plyPageData" in text:
            m = re.search(r"window\['plyPageData'\]\s*=\s*({.*?});", text, re.S)
            if m:
                try:
                    price = json.loads(m.group(1))["productDetails"]["price"] / 100
                    return ScrapeResult(price, "RON", method="script")
                except (ValueError, KeyError, TypeError):
                    pass
    return None


def _title(tree):
    node = tree.css_first("h1") or tree.css_first('meta[property="og:title"]') or tree.css_first("title")
    if not node:
        return None
    return (_attr_or_text(node) or "").strip()[:120] or None


def extract(html, selector=None):
    tree = HTMLParser(html)
    title = _title(tree)
    # Datele structurate (JSON-LD) sunt cele mai sigure: un selector CSS poate nimeri
    # prețul unui accesoriu/variante (ex. motoin.de: CSS 55 RON vs real 639 RON).
    steps = [
        lambda: _extract_jsonld(tree),
        lambda: selector and _extract_css(tree, selector),
        lambda: _extract_meta(tree),
        lambda: _extract_css(tree, COMMON_SELECTORS, method="common-css"),
        lambda: _extract_known_scripts(tree),
    ]
    for step in steps:
        try:
            result = step()
        except Exception as e:  # un selector invalid nu trebuie să oprească restul cascadei
            log.debug("Pas extragere eșuat: %s", e)
            continue
        if result and result.price:
            result.title = result.title or title
            result.currency = result.currency.upper() if result.currency else None
            return result
    return ScrapeResult(title=title, error="preț negăsit în pagină")


# ---------------------------------------------------------------- descărcare


class Scraper:
    def __init__(self):
        self._session = None
        self._global = asyncio.Semaphore(config.MAX_CONCURRENCY)
        self._domains = defaultdict(lambda: asyncio.Semaphore(config.PER_DOMAIN_CONCURRENCY))
        self._browser = None
        self._pw = None

    async def __aenter__(self):
        self._session = AsyncSession(
            impersonate="chrome",
            timeout=config.REQUEST_TIMEOUT,
            max_clients=config.MAX_CONCURRENCY,
            headers={"Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7"},
        )
        return self

    async def __aexit__(self, *exc):
        await self._session.close()
        if self._browser:
            await self._browser.close()
            await self._pw.stop()

    async def _fetch(self, url):
        """GET cu retry + backoff exponențial pentru 429/5xx/erori de rețea."""
        last_error = None
        for attempt in range(config.MAX_RETRIES):
            try:
                resp = await self._session.get(url, allow_redirects=True)
                if resp.status_code == 200:
                    return resp.text, None
                last_error = f"HTTP {resp.status_code}"
                if resp.status_code in (403, 404, 410):
                    break  # nu ajută să reîncercăm
            except Exception as e:
                last_error = type(e).__name__
            await asyncio.sleep(2**attempt + random.random())
        return None, last_error

    async def _fetch_browser(self, url):
        if self._browser is None:
            from playwright.async_api import async_playwright  # import leneș: dependență opțională

            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)
        page = await self._browser.new_page(locale="ro-RO")
        try:
            # nu descărcăm imagini/fonturi/video -> mult mai rapid
            await page.route(
                "**/*",
                lambda r: r.abort() if r.request.resource_type in ("image", "font", "media") else r.continue_(),
            )
            await page.goto(url, wait_until="domcontentloaded", timeout=config.REQUEST_TIMEOUT * 1000)
            await page.wait_for_timeout(2500)  # lasă JS-ul să pună prețul în pagină
            return await page.content()
        finally:
            await page.close()

    async def scrape(self, url, selector=None):
        domain = urlsplit(url).netloc
        async with self._global, self._domains[domain]:
            html, error = await self._fetch(url)
            result = extract(html, selector) if html else ScrapeResult(error=error)
            if not result.price and config.USE_BROWSER_FALLBACK:
                try:
                    result = extract(await self._fetch_browser(url), selector)
                    result.method = f"browser/{result.method}" if result.price else None
                except Exception as e:
                    log.warning("Browser fallback eșuat pentru %s: %s", url, e)
            await asyncio.sleep(random.uniform(0.3, 1.0))  # mică pauză, să nu părem robot
            return result
