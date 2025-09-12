import requests
from bs4 import BeautifulSoup
import time
import pandas as pd
import io

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
        resp = requests.get(product['url'], headers={'User-Agent': 'Mozilla/5.0'})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        price_tag = soup.select_one(product['selector'])
        if price_tag:
            price_str = price_tag.text.strip().replace('Lei', '').replace('.', '').replace(',', '.')
            return float(price_str)
        else:
            print(f"[{product['name']}] Selectorul nu a găsit prețul!")
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

def check_telegram_commands():
    """Verifică dacă ai trimis /test sau /reload pe Telegram"""
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
                        send_telegram_message("✅ Scriptul rulează perfect! Monitorizez prețurile...")
                        # Marchează mesajul ca citit
                        offset = data['result'][-1]['update_id'] + 1
                        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}")
                    elif command == '/reload':
                        send_telegram_message("🔄 Reîncărcare produse din Google Sheets...")
                        # Marchează mesajul ca citit
                        offset = data['result'][-1]['update_id'] + 1
                        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}")
                        return True  # Signal to reload products
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
    print("🚀 Monitor prețuri pornit cu Google Sheets!")
    print("💬 Comenzi Telegram:")
    print("   /test - verifică dacă scriptul rulează")
    print("   /reload - reîncarcă produsele din Google Sheets")
    
    # Încarcă produsele inițial
    products = load_products_from_google_sheets()
    
    cycle_count = 0
    while True:
        try:
            # Verifică comenzi Telegram
            should_reload = check_telegram_commands()
            
            # Reîncarcă produsele la fiecare 10 cicluri sau la comandă
            if should_reload or cycle_count % 10 == 0:
                print("🔄 Reîncărcare produse din Google Sheets...")
                products = load_products_from_google_sheets()
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