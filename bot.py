import sys
import os
import requests
import time
import json
import re
import threading
from datetime import datetime
from bs4 import BeautifulSoup
from flask import Flask

os.environ["PYTHONUNBUFFERED"] = "1"
sys.stdout.reconfigure(line_buffering=True)

# ═══════════════════════════════════════════════════════════════
#  KONFIGURACJA
# ═══════════════════════════════════════════════════════════════
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
CHECK_INTERVAL     = 120   # sekundy
MIN_PRICE          = 100
MAX_PRICE          = 2000
DISCOUNT_THRESHOLD = 0     # % – 0 = wysylaj wszystko, 10 = tylko 10% taniej

MY_PRICES = {
    "iphone 13":          {128: 600,  256: 700,  512: 570},
    "iphone 13 pro":      {128: 800,  256: 900,  512: 1000, 1024: 1120},
    "iphone 13 pro max":  {128: 870,  256: 1060, 512: 1090, 1024: 1120},
    "iphone 14":          {128: 790,  256: 860,  512: 920},
    "iphone 14+":         {128: 860,  256: 890,  512: 950},
    "iphone 14 plus":     {128: 860,  256: 890,  512: 950},
    "iphone 14 pro":      {128: 1020, 256: 1140, 512: 1270, 1024: 1340},
    "iphone 14 pro max":  {128: 1210, 256: 1240, 512: 1270, 1024: 1340},
    "iphone 15":          {128: 1020, 256: 1270, 512: 1460},
    "iphone 15 plus":     {128: 1240, 256: 1300, 512: 1420},
    "iphone 15+":         {128: 1240, 256: 1300, 512: 1420},
    "iphone 15 pro":      {},
    "iphone 15 pro max":  {},
    "iphone 16":          {},
    "iphone 16 plus":     {},
    "iphone 16+":         {},
    "iphone 16 pro":      {},
    "iphone 16 pro max":  {},
    "samsung s23":        {128: 650,  256: 780},
    "galaxy s23":         {128: 650,  256: 780},
    "samsung s23+":       {128: 800,  256: 800},
    "galaxy s23+":        {128: 800,  256: 800},
    "samsung s23 ultra":  {256: 1040, 512: 1140},
    "galaxy s23 ultra":   {256: 1040, 512: 1140},
    "samsung s24":        {128: 880,  256: 940},
    "galaxy s24":         {128: 880,  256: 940},
    "samsung s24+":       {256: 1130, 512: 1200},
    "galaxy s24+":        {256: 1130, 512: 1200},
    "samsung s24 ultra":  {256: 1450, 512: 1500},
    "galaxy s24 ultra":   {256: 1450, 512: 1500},
    "samsung s25":        {},
    "galaxy s25":         {},
    "samsung s25+":       {},
    "galaxy s25+":        {},
    "samsung s25 ultra":  {},
    "galaxy s25 ultra":   {},
}

# Zapytania do wyszukiwarki OLX (format dla URL: spacje → "+")
OLX_QUERIES = [
    "iphone+13", "iphone+14", "iphone+15", "iphone+16",
    "samsung+s23", "samsung+s24", "samsung+s25",
    "galaxy+s23", "galaxy+s24", "galaxy+s25",
]

# Zapytania do Vinted
VINTED_QUERIES = [
    "iphone 13", "iphone 14", "iphone 15", "iphone 16",
    "samsung s23", "samsung s24", "samsung s25",
    "galaxy s23", "galaxy s24", "galaxy s25",
]

ACCESSORY_KEYWORDS = [
    "etui", "case", "pokrowiec", "szklo", "szkło", "folia",
    "uchwyt", "ladowarka", "ładowarka", "kabel", "cable",
    "sluchawki", "słuchawki", "earphones", "airpods",
    "powerbank", "adapter", "atrapa", "naklejka",
    "tempered glass", "screen protector", "panzer", "spigen",
    "hoops", "huse", "husă", "maska", "kryt",
    "torbica", "stojak", "plecki", "back cover",
    "silikonow", "silikonowe", "przezroczyst",
    "hartowane", "smartwatch", "zegarek", "watch",
    "wymienn", "ładowanie", "wireless",
]

DAMAGE_KEYWORDS = [
    "uszkodzon", "rozbity", "peknieto", "zbity", "nie dziala",
    "nie wlacza", "nie laduje", "awari", "do naprawy", "na czesci",
    "defekt", "wada", "problem z", "damaged", "broken", "cracked",
]

# ═══════════════════════════════════════════════════════════════
#  PAMIEC WIDZIANYCH
# ═══════════════════════════════════════════════════════════════
SEEN_FILE = "seen_listings.json"

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

# ═══════════════════════════════════════════════════════════════
#  FILTR AKCESORIUM (tylko Vinted)
# ═══════════════════════════════════════════════════════════════
def is_accessory(title_lower):
    return any(kw in title_lower for kw in ACCESSORY_KEYWORDS)

def is_damaged(title_lower, desc_lower=""):
    haystack = title_lower + " " + desc_lower
    return any(kw in haystack for kw in DAMAGE_KEYWORDS)

# ═══════════════════════════════════════════════════════════════
#  SCRAPER OLX – wzorowany na działającym kodzie
# ═══════════════════════════════════════════════════════════════
def scrape_olx(query):
    results = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pl,en;q=0.9",
    }

    for page in range(1, 3):  # 2 strony = ~100 ogloszen
        url = (
            f"https://www.olx.pl/elektronika/telefony/"
            f"smartfony-telefony-komorkowe/"
            f"q-{query}/?search%5Border%5D=created_at:desc&page={page}"
        )
        try:
            r = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")

            # Selektory z działającego kodu
            cards = (
                soup.select('div[data-cy="l-card"]') or
                soup.select('div[data-testid="l-card"]')
            )
            print(f"[OLX] '{query}' str.{page}: {len(cards)} kart", flush=True)

            for card in cards:
                try:
                    a = card.find("a", href=True)
                    if not a:
                        continue

                    title = re.sub(r"\s+", " ", a.get_text()).strip()
                    title_low = title.lower()

                    # Odrzuc akcesoria po tytule
                    if is_accessory(title_low):
                        continue

                    href = a["href"]
                    if not href.startswith("http"):
                        href = "https://www.olx.pl" + href

                    # Cena – sposob z dzialajacego kodu
                    card_text = card.get_text()
                    price_match = re.search(r"([\d\s]+)\s?zł", card_text)
                    if not price_match:
                        continue
                    price = float(price_match.group(1).replace(" ", "").replace("\xa0", ""))

                    if not (MIN_PRICE <= price <= MAX_PRICE):
                        continue

                    # Wysylka OLX
                    card_low = card_text.lower()
                    has_shipping = (
                        "wysyłka olx" in card_low or
                        "dostawa olx" in card_low or
                        bool(card.select_one("[data-testid='delivery-badge']"))
                    )

                    img_el = card.select_one("img")
                    image  = img_el.get("src", "") if img_el else ""

                    results.append({
                        "id": href, "platform": "OLX",
                        "title": title, "price": price,
                        "price_raw": f"{price:.0f} zl",
                        "link": href, "image": image,
                        "has_shipping": has_shipping,
                        "description": card_low,
                    })
                except Exception:
                    continue

            time.sleep(0.5)
        except Exception as e:
            print(f"[OLX] Blad '{query}' str.{page}: {e}", flush=True)

    print(f"[OLX] '{query}': telefonow={len(results)}", flush=True)
    return results

# ═══════════════════════════════════════════════════════════════
#  SCRAPER VINTED
# ═══════════════════════════════════════════════════════════════
def scrape_vinted(query):
    results = []
    url = (
        f"https://www.vinted.pl/api/v2/catalog/items"
        f"?search_text={requests.utils.quote(query)}"
        f"&price_from={MIN_PRICE}&price_to={MAX_PRICE}"
        f"&per_page=30&order=newest_first"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "pl-PL,pl;q=0.9",
        "Referer": "https://www.vinted.pl/",
        "Origin": "https://www.vinted.pl",
    }
    try:
        session = requests.Session()
        session.get(
            "https://www.vinted.pl/catalog?search_text=" + requests.utils.quote(query),
            headers=headers, timeout=15
        )
        time.sleep(2)
        r = session.get(url, headers=headers, timeout=15)
        if r.status_code != 200 or not r.text.strip():
            print(f"[Vinted] Brak odpowiedzi '{query}' status={r.status_code}", flush=True)
            return results
        data = r.json()
        raw = len(data.get("items", []))
        print(f"[Vinted] '{query}': raw={raw}", flush=True)
        for item in data.get("items", []):
            try:
                price = float(item.get("price", {}).get("amount", 9999))
                if not (MIN_PRICE <= price <= MAX_PRICE):
                    continue
                title     = item.get("title", "")
                title_low = title.lower()
                # Odrzuc akcesoria
                if is_accessory(title_low):
                    continue
                # Musi zawierac nazwe modelu
                if not any(k in title_low for k in MY_PRICES):
                    continue
                item_id     = str(item.get("id"))
                description = item.get("description", "").lower()
                link        = f"https://www.vinted.pl/items/{item_id}"
                image       = item.get("photo", {}).get("url", "")
                results.append({
                    "id": f"vinted_{item_id}", "platform": "Vinted",
                    "title": title, "price": price,
                    "price_raw": f"{price:.0f} zl",
                    "link": link, "image": image,
                    "has_shipping": True,
                    "description": title_low + " " + description,
                })
            except Exception:
                continue
        print(f"[Vinted] '{query}': telefonow={len(results)}", flush=True)
    except Exception as e:
        print(f"[Vinted] Blad '{query}': {e}", flush=True)
    return results

# ═══════════════════════════════════════════════════════════════
#  HELPERY
# ═══════════════════════════════════════════════════════════════
def extract_storage_gb(text):
    t = text.lower()
    tb = re.search(r'(\d+)\s*tb', t)
    if tb:
        return int(tb.group(1)) * 1024
    gb = re.search(r'\b(64|128|256|512)\s*gb\b', t)
    if gb:
        return int(gb.group(1))
    standalone = re.search(r'\b(128|256|512)\b', t)
    if standalone:
        return int(standalone.group(1))
    return None

def get_ref_price(title, description=""):
    haystack = (title + " " + description).lower()
    best_key, best_len = None, 0
    for key in MY_PRICES:
        if key in haystack and len(key) > best_len:
            best_key, best_len = key, len(key)
    if best_key is None:
        return None, None, None
    variants = MY_PRICES[best_key]
    if not variants:
        return None, None, best_key
    detected_gb = extract_storage_gb(haystack)
    if detected_gb and detected_gb in variants:
        return variants[detected_gb], detected_gb, best_key
    fallback_gb = min(variants.keys())
    return variants[fallback_gb], detected_gb, best_key

def discount_pct(price, ref):
    return round((1 - price / ref) * 100)

def gb_label(gb):
    if gb is None:
        return "nieznana"
    if gb >= 1024:
        return f"{gb // 1024}TB"
    return f"{gb}GB"

# ═══════════════════════════════════════════════════════════════
#  WYSYLKA NA DISCORD
# ═══════════════════════════════════════════════════════════════
def send_discord(item, ref_price, storage_gb, model_key):
    pct     = discount_pct(item["price"], ref_price) if ref_price else None
    damaged = is_damaged(item["title"].lower(), item.get("description", ""))

    if damaged:
        color = 0x808080
    elif pct and pct >= 30:
        color = 0xFF4500
    elif pct and pct >= 20:
        color = 0xFFD700
    else:
        color = 0x00CC66

    shipping_text = (
        ("TAK - Wysylka OLX" if item.get("has_shipping") else "NIE - tylko odbior osobisty")
        if item["platform"] == "OLX" else "TAK (Vinted)"
    )

    if ref_price:
        ref_text      = f"{ref_price} zl ({gb_label(storage_gb)})"
        discount_text = f"-{pct}% taniej niz cena referencyjna!" if pct else ""
    else:
        ref_text      = "brak danych dla tego modelu/pamieci"
        discount_text = ""

    damage_text = "UWAGA: moze byc uszkodzony!" if damaged else "Brak oznak uszkodzenia"
    desc_parts  = []
    if discount_text:
        desc_parts.append(f"OKAZJA {discount_text}")
    desc_parts.append(damage_text)

    embed = {
        "title":       f"Nowe ogloszenie: {item['title']}",
        "url":         item["link"],
        "color":       color,
        "description": "\n".join(desc_parts),
        "fields": [
            {"name": "Cena",              "value": item["price_raw"],                               "inline": True},
            {"name": "Cena ref.",         "value": ref_text,                                         "inline": True},
            {"name": "Platforma",         "value": item["platform"],                                 "inline": True},
            {"name": "Model",             "value": model_key.title() if model_key else "nieznany",   "inline": True},
            {"name": "Pamiec",            "value": gb_label(storage_gb),                             "inline": True},
            {"name": "Wysylka OLX",       "value": shipping_text,                                    "inline": False},
        ],
        "footer": {"text": f"PhoneDealBot  {datetime.now().strftime('%H:%M  %d.%m.%Y')}"},
    }
    if item.get("image"):
        embed["thumbnail"] = {"url": item["image"]}

    payload = {"username": "PhoneDealBot", "embeds": [embed]}
    for _ in range(3):
        try:
            r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
            if r.status_code == 429:
                wait = float(r.json().get("retry_after", 2))
                print(f"[Discord] Rate limit, czekam {wait}s...", flush=True)
                time.sleep(wait + 0.5)
                continue
            if r.status_code not in (200, 204):
                print(f"[Discord] Blad: {r.status_code}", flush=True)
            break
        except Exception as e:
            print(f"[Discord] Wyjatek: {e}", flush=True)
            break
    time.sleep(1.5)

# ═══════════════════════════════════════════════════════════════
#  PRZETWARZANIE
# ═══════════════════════════════════════════════════════════════
def process_items(items, seen, send=True):
    deal_count = 0
    skip_count = 0
    for item in items:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        ref_price, storage_gb, model_key = get_ref_price(
            item["title"], item.get("description", "")
        )
        is_deal = not (ref_price and item["price"] >= ref_price * (1 - DISCOUNT_THRESHOLD / 100))
        if is_deal:
            if send:
                print(f"OKAZJA: {item['title']} | {item['price_raw']} | {gb_label(storage_gb)} | {item['platform']}", flush=True)
                send_discord(item, ref_price, storage_gb, model_key)
            deal_count += 1
        else:
            skip_count += 1
    return deal_count, skip_count

def fetch_all():
    all_items = []
    for query in OLX_QUERIES:
        all_items.extend(scrape_olx(query))
        time.sleep(1)
    for query in VINTED_QUERIES:
        all_items.extend(scrape_vinted(query))
        time.sleep(1)
    return all_items

# ═══════════════════════════════════════════════════════════════
#  KEEP-ALIVE (Flask)
# ═══════════════════════════════════════════════════════════════
app = Flask(__name__)

@app.route("/")
def home():
    return "OK"

def start_flask():
    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=8080)

# ═══════════════════════════════════════════════════════════════
#  GLOWNA PETLA
# ═══════════════════════════════════════════════════════════════
def main():
    print("PhoneDealBot uruchomiony!", flush=True)
    print(f"Co {CHECK_INTERVAL // 60} min | {MIN_PRICE}-{MAX_PRICE} zl | Prog: {DISCOUNT_THRESHOLD}%", flush=True)

    seen      = load_seen()
    first_run = len(seen) == 0

    if first_run:
        print("Pierwsze uruchomienie – szukam okazji i zapisuje reszte...", flush=True)
        items = fetch_all()
        deal_count, skip_count = process_items(items, seen, send=True)
        save_seen(seen)
        print(f"Start: wyslano {deal_count} okazji, pominieto {skip_count}.", flush=True)
        time.sleep(CHECK_INTERVAL)

    while True:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sprawdzam...", flush=True)
        items = fetch_all()
        deal_count, _ = process_items(items, seen, send=True)
        save_seen(seen)
        print(f"Nowych okazji: {deal_count}", flush=True)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    main()
