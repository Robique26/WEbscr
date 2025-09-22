import requests
from bs4 import BeautifulSoup
import time
import pandas as pd
import json
import re

# Setări Telegram
TELEGRAM_TOKEN = '8229151011:AAF_TzWPm03IVnZ9cyXFe1vUZeYX_Vp-LjA'
TELEGRAM_CHAT_ID = '1531622471'

# Fișierul Excel local
EXCEL_FILE = "produse.xlsx"

def load_products_from_excel():
    """Încarcă produsele din fișierul Excel local"""
    try:
        df = pd.read_excel(EXCEL_FILE)
        
        products = []
        for _, row in df.iterrows():
            products.append({
                'name': row['nume'],
                'url': row['url'],
                'selector': row['selector'],
                'last_price': None
            })
        
        print(f"✅ Încărcat {len(products)} produse din Excel")
        return products
        
    except Exception as e:
        print(f"❌ Eroare la încărcarea din Excel: {e}")
        return []

def get_price(product):
    try:
        # Headers mai bune pentru anti-blocking (fără compression pentru simplitate)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ro-RO,ro;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        resp = requests.get(product['url'], headers=headers, timeout=10)
        
        # Verifică dacă site-ul blochează (403 Cloudflare)
        if resp.status_code == 403:
            print(f"[{product['name']}] Site blocat cu 403 (probabil Cloudflare)")
            return None
            
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Detectează site-uri internaționale care au probleme cu CSS
        # Pentru site-uri românești (.ro), dă prioritate CSS chiar dacă conține RON/EUR
        is_romanian_site = '.ro/' in product['url'] or product['url'].endswith('.ro')
        
        # Site internațional = orice site non-românesc (.de, .com, .fr, .it, .es, etc.)
        is_international_site = not is_romanian_site
        
        # METODA 1: Încearcă selectorul CSS
        css_price = None
        price_tag = soup.select_one(product['selector'])
        if price_tag:
            try:
                price_str = price_tag.text.strip().replace('Lei', '').replace('lei', '').replace('.', '').replace(',', '.').strip()
                css_price = float(price_str)
                print(f"[{product['name']}] CSS găsește: {css_price} (din '{price_tag.text.strip()}')")
                
                # Pentru site-uri românești, returnează imediat CSS
                if not is_international_site:
                    return css_price
                    
            except (ValueError, AttributeError):
                print(f"[{product['name']}] Selectorul găsit dar eroare la procesare: '{price_tag.text.strip()}'")
        
        # METODA 2: JavaScript - pentru site-uri internaționale sau ca fallback
        #print(f"[{product['name']}] Încerc fallback JavaScript...")
        scripts = soup.find_all('script')
        
        for script in scripts:
            if not script.string:
                continue
                
            # Pentru PlayBike.ro - caută plyPageData
            if 'plyPageData' in script.string:
                match = re.search(r'window\[\'plyPageData\'\]\s*=\s*({.*?});', script.string, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        if 'productDetails' in data and 'price' in data['productDetails']:
                            price_cents = data['productDetails']['price']
                            price = price_cents / 100
                            #print(f"[{product['name']}] Preț găsit în plyPageData: {price} lei")
                            return price
                    except json.JSONDecodeError:
                        continue
            
            # Pentru alte site-uri - caută pattern-uri generale de preț în JSON
            price_patterns = [
                r'"price":\s*(\d+(?:\.\d+)?)',  # "price": 123.45
                r'"currentPrice":\s*(\d+(?:\.\d+)?)',  # "currentPrice": 123.45
                r'"sellPrice":\s*(\d+(?:\.\d+)?)',     # "sellPrice": 123.45
                r'"finalPrice":\s*(\d+(?:\.\d+)?)',    # "finalPrice": 123.45
                r'price["\']:\s*["\']?(\d+(?:\.\d+)?)', # price: "123.45" sau price: 123.45
            ]
            
            for pattern in price_patterns:
                matches = re.finditer(pattern, script.string, re.IGNORECASE)
                for match in matches:
                    try:
                        price = float(match.group(1))
                        # Verifică dacă prețul pare rezonabil (între 1 și 50000 lei)
                        if 1 <= price <= 50000:
                            print(f"[{product['name']}] JavaScript găsește: {price} lei")
                            return price
                    except ValueError:
                        continue
        
        # Dacă JavaScript nu găsește nimic dar CSS a găsit ceva, returnează CSS
        if css_price is not None:
            print(f"[{product['name']}] Folosesc fallback CSS: {css_price} lei")
            return css_price
            
        print(f"[{product['name']}] Nu am găsit prețul nici cu CSS nici cu JavaScript")
        return None
            
    except Exception as e:
        print(f"[{product['name']}] Eroare la get_price: {e}")
        return None

def send_telegram_message(message):
    from urllib.parse import quote_plus
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={TELEGRAM_CHAT_ID}&text={quote_plus(message)}"
    try:
        resp = requests.get(url)
        if resp.status_code != 200:
            print(f"Eroare Telegram: {resp.text}")
    except Exception as e:
        print(f"Eroare la trimiterea mesajului Telegram: {e}")

def check_telegram_commands(products):
    """Verifică dacă ai trimis /test, /reload sau /pret pe Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        resp = requests.get(url)
        if resp.status_code == 200:
            data = resp.json()
            if data['result']:
                last_message = data['result'][-1]['message']
                if 'text' in last_message:
                    command = last_message['text']
                    if command == '/test':
                        send_telegram_message("✅ Scriptul rulează perfect cu Excel! Monitorizez prețurile...")
                        # Marchează mesajul ca citit
                        offset = data['result'][-1]['update_id'] + 1
                        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}")
                    elif command == '/reload':
                        send_telegram_message("🔄 Reîncărcare produse din fișierul Excel...")
                        # Marchează mesajul ca citit
                        offset = data['result'][-1]['update_id'] + 1
                        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}")
                        return True  # Signal to reload products
                    elif command == '/pret':
                        # Afișează toate prețurile curente
                        price_list = "📊 PREȚURI CURENTE (din Excel):\n\n"
                        for product in products:
                            if product['last_price'] is not None:
                                price_list += f"• {product['name']}: {product['last_price']} Lei\n"
                            else:
                                price_list += f"• {product['name']}: Preț indisponibil\n"
                        
                        send_telegram_message(price_list)
                        # Marchează mesajul ca citit
                        offset = data['result'][-1]['update_id'] + 1
                        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}")
    except Exception as e:
        print(f"Eroare verificare comenzi: {e}")
    return False

def check_prices(products):
    print("\n=== VERIFICARE PREȚURI ===")
    print(f"Timp verificare: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)
    
    for product in products:
        price = get_price(product)
        if price is not None:
            # Afișează prețul în terminal
            print(f"✓ {product['name']}: {price} Lei")
            
            if product['last_price'] is None:
                product['last_price'] = price
                print(f"  → Primul preț înregistrat")
            elif price < product['last_price']:
                msg = f"Preț scăzut la {product['name']}: {product['last_price']} -> {price} Lei!\n{product['url']}"
                print(f"  → 📉 SCĂDERE! Trimis mesaj Telegram")
                send_telegram_message(msg)
                product['last_price'] = price
            elif price > product['last_price']:
                print(f"  → 📈 Creștere: {product['last_price']} -> {price}")
                product['last_price'] = price
            else:
                print(f"  → 📊 Preț neschimbat")
                product['last_price'] = price
        else:
            print(f"✗ {product['name']}: Nu am putut obține prețul")
    
    print("-" * 50)

if __name__ == '__main__':
    print("🚀 Monitor prețuri pornit cu Excel!")
    print("💬 Comenzi Telegram:")
    print("   /test - verifică dacă scriptul rulează")
    print("   /reload - reîncarcă produsele din Excel")
    print("   /pret - afișează toate prețurile curente")
    
    # Încarcă produsele inițial
    products = load_products_from_excel()
    
    cycle_count = 0
    while True:
        try:
            # Verifică comenzi Telegram
            should_reload = check_telegram_commands(products)
            
            # Reîncarcă produsele la fiecare 10 cicluri sau la comandă
            if should_reload or cycle_count % 10 == 0:
                print("🔄 Reîncărcare produse din Excel...")
                products = load_products_from_excel()
                cycle_count = 0
            
            check_prices(products)
            print("Mai verific peste 30 secunde")
            time.sleep(30)  # 30 secunde între verificări
            cycle_count += 1
            
        except KeyboardInterrupt:
            print("\n⛔ Oprire manuală...")
            break
        except Exception as e:
            print(f"❌ Eroare generală: {e}")
            time.sleep(10)