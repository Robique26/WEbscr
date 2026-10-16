# PriceBot – monitorizare prețuri cu Telegram

Bot Telegram care urmărește prețurile produselor din orice magazin online și te anunță la
ieftiniri, scumpiri, preț țintă atins și revenire în stoc.

## Pornire

```bash
pip install -r requirements.txt
cp .env.example .env      # completează TELEGRAM_TOKEN și ALLOWED_CHAT_IDS
python bot.py
```

Trimite `/start` botului ca să-ți afli chat ID-ul, apoi pune-l în `ALLOWED_CHAT_IDS`.

## Folosire

- Trimite un **link de produs** → îl urmărește (nu e nevoie de selector CSS).
- Trimite `produse.xlsx` / `.csv` (coloane `nume, url, selector`) → import în masă.
- `/lista`, `/pret`, `/tinta <id> <preț>`, `/istoric <id>`, `/sterge <id>`, `/status`.

## Cum găsește prețul

Ordinea de căutare, de la cea mai sigură:

1. **JSON-LD** (schema.org `Product`), pe care îl au eMAG, PlayBike, Flip, Buzz, motoin.de și alții
2. selectorul tău CSS (dacă l-ai setat)
3. meta tag-uri / microdata (`og:price:amount`, `itemprop="price"`)
4. selectori folosiți de multe magazine (Magento, WooCommerce, AboutYou…)
5. *(opțional)* Chrome headless prin Playwright, cu `USE_BROWSER_FALLBACK=1`

Cererile pleacă în paralel prin `curl_cffi`, care imită amprenta TLS a lui Chrome, ca să nu fie
blocate de Cloudflare. Pe fiecare site rulează cel mult 2 cereri simultan, iar prețurile se
salvează în SQLite, deci istoricul rămâne și după restart.

## Pe VPS (systemd)

`/etc/systemd/system/pricebot.service`:

```ini
[Unit]
Description=PriceBot
After=network-online.target

[Service]
WorkingDirectory=/home/USER/pricebot
ExecStart=/home/USER/pricebot/.venv/bin/python bot.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now pricebot
journalctl -u pricebot -f
```
