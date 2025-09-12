import requests
from bs4 import BeautifulSoup
import time
import pandas as pd

# Setări Telegram
TELEGRAM_TOKEN = '8229151011:AAF_TzWPm03IVnZ9cyXFe1vUZeYX_Vp-LjA'
TELEGRAM_CHAT_ID = '1531622471'

# Listă de produse de urmărit
df = pd.read_excel('produse.xlsx')  # Numele fișierului Excel

PRODUCTS = []
for _, row in df.iterrows():
    PRODUCTS.append({
        'name': row['nume'],
        'url': row['url'],
        'selector': row['selector'],
        'last_price': None
    })

# Acum PRODUCTS conține lista ca înainte!
print(PRODUCTS)

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

def check_prices():
    print("\n=== VERIFICARE PREȚURI ===")
    print(f"Timp verificare: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)
    
    for product in PRODUCTS:
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
    while True:
        check_prices()
        print("Mai verific peste 5 secunde")
        time.sleep(5)  # verifică la fiecare 5 secunde