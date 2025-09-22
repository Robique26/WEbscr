import requests
from bs4 import BeautifulSoup
import time
import pandas as pd
import io
import json
import re

# Setări Telegram
TELEGRAM_TOKEN = '8229151011:AAF_TzWPm03IVnZ9cyXFe1vUZeYX_Vp-LjA'
TELEGRAM_CHAT_ID = '1531622471'

# LINK-UL TĂU GOOGLE SHEETS - CONFIGURAT CORECT! ✅
# Original: https://docs.google.com/spreadsheets/d/1dmpIwSgstN5S5qcCUbkWcFOablKWSk3J574iGZ5TcEI/edit?usp=sharing
# Export:   https://docs.google.com/spreadsheets/d/1dmpIwSgstN5S5qcCUbkWcFOablKWSk3J574iGZ5TcEI/export?format=csv
GOOGLE_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1dmpIwSgstN5S5qcCUbkWcFOablKWSk3J574iGZ5TcEI/export?format=csv"

def load_products_from_google_sheets():
    """Încarcă produsele din Google Sheets în timp real"""
    try:
        response = requests.get(GOOGLE_SHEETS_URL)
        response.raise_for_status()
        
        # Citește CSV-ul din Google Sheets
        df = pd.read_csv(io.StringIO(response.text))
        
        products = []
        for _, row in df.iterrows():
            products.append({
                'name': row['nume'],
                'url': row['url'],
                'selector': row['selector'],
                'last_price': None
            })
        
        print(f"✅ Încărcat {len(products)} produse din Google Sheets")
        return products
        
    except Exception as e:
        print(f"❌ Eroare la încărcarea din Google Sheets: {e}")
        # Fallback la Excel local
        print("🔄 Încerc să citesc din produse.xlsx local...")
        df = pd.read_excel('produse.xlsx')
        products = []
        for _, row in df.iterrows():
            products.append({
                'name': row['nume'],
                'url': row['url'],
                'selector': row['selector'],
                'last_price': None
            })
        return products

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
                #print(f"[{product['name']}] CSS găsește: {css_price} (din '{price_tag.text.strip()}')")
                
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
                            #print(f"[{product['name']}] JavaScript găsește: {price} lei")
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
                            #print(f"[{product['name']}] JavaScript găsește: {price} lei")
                            return price
                    except ValueError:
                        continue
        
        # Dacă JavaScript nu găsește nimic dar CSS a găsit ceva, returnează CSS
        if css_price is not None:
            #print(f"[{product['name']}] Folosesc fallback CSS: {css_price} lei")
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
                        send_telegram_message("✅ Scriptul cu Google Sheets rulează perfect! Monitorizez prețurile...")
                        # Marchează mesajul ca citit
                        offset = data['result'][-1]['update_id'] + 1
                        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}")
                    elif command == '/reload':
                        send_telegram_message("🔄 Reîncărcare produse din Google Sheets...")
                        products = load_products_from_google_sheets()
                        # Marchează mesajul ca citit
                        offset = data['result'][-1]['update_id'] + 1
                        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}")
                        return products  # Returnează lista reîncărcată
                    elif command == '/pret':
                        # Testează primul produs să vadă dacă merge
                        if products:
                            test_price = get_price(products[0])
                            if test_price:
                                send_telegram_message(f"🔍 Test: {products[0]['name']} = {test_price} lei")
                            else:
                                send_telegram_message(f"❌ Test: Nu pot găsi prețul pentru {products[0]['name']}")
                        # Marchează mesajul ca citit
                        offset = data['result'][-1]['update_id'] + 1
                        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}")
    except Exception as e:
        print(f"Eroare Telegram: {e}")
    
    return None  # Nu returnează nimic dacă nu e /reload

def main():
    print("🚀 MONITOR PREȚURI GOOGLE SHEETS - Versiunea cu fallback JavaScript universal!")
    
    # Încarcă produsele din Google Sheets
    products = load_products_from_google_sheets()
    
    while True:
        try:
            # Verifică comenzile Telegram
            reload_result = check_telegram_commands(products)
            if reload_result is not None:
                products = reload_result
            
            print(f"\n🔍 Verificare prețuri - {time.strftime('%H:%M:%S')}")
            for product in products:
                current_price = get_price(product)
                
                if current_price is not None:
                    if product['last_price'] is None:
                        # Prima verificare - doar salvează prețul
                        product['last_price'] = current_price
                        print(f"✅ {product['name']}: {current_price} lei (prima verificare)")
                    elif current_price != product['last_price']:
                        # Prețul s-a schimbat!
                        difference = current_price - product['last_price']
                        if difference > 0:
                            message = f"📈 SCUMPIRE: {product['name']}\n💰 {product['last_price']} → {current_price} lei (+{difference:.2f})\n🔗 {product['url']}"
                        else:
                            message = f"📉 IEFTINIRE: {product['name']}\n💰 {product['last_price']} → {current_price} lei ({difference:.2f})\n🔗 {product['url']}"
                        
                        send_telegram_message(message)
                        product['last_price'] = current_price
                        print(f"🔔 {product['name']}: {current_price} lei (trimis pe Telegram)")
                    else:
                        print(f"⚪ {product['name']}: {current_price} lei (neschimbat)")
                else:
                    print(f"❌ {product['name']}: Nu am putut extrage prețul")
                
                # Pauză între produse pentru a nu overloada server-ul
                time.sleep(2)
            
            print(f"⏰ Următoarea verificare în 30 de secunde...")
            time.sleep(30)  # 30 secunde
            
        except KeyboardInterrupt:
            print("\n👋 Oprire manuală. Script închis.")
            break
        except Exception as e:
            print(f"❌ Eroare: {e}")
            print("🔄 Încerc din nou în 5 minute...")
            time.sleep(300)

if __name__ == "__main__":
    main()