import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

TELEGRAM_TOKEN = '8229151011:AAF_TzWPm03IVnZ9cyXFe1vUZeYX_Vp-LjA'
TELEGRAM_CHAT_ID = '1531622471'

# Citește produsele din Excel
df = pd.read_excel('produse.xlsx')
PRODUCTS = []
for _, row in df.iterrows():
    PRODUCTS.append({
        'name': row['nume'],
        'url': row['url'],
        'selector': row['selector'],
    })

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
    url = (
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?"
        f"chat_id={TELEGRAM_CHAT_ID}&text={quote_plus(message)}"
    )
    try:
        resp = requests.get(url)
        if resp.status_code != 200:
            print(f"Eroare Telegram: {resp.text}")
    except Exception as e:
        print(f"Eroare la trimiterea mesajului Telegram: {e}")

# Verifică și trimite prețul actual pentru fiecare produs
for product in PRODUCTS:
    price = get_price(product)
    if price is not None:
        print(f"[{product['name']}] Preț actual: {price} Lei")
        mesaj = f"Pretul actual la {product['name']}: {price} Lei\n{product['url']}"
        send_telegram_message(mesaj)
    else:
        print(f"[{product['name']}] Nu am putut obține prețul.")