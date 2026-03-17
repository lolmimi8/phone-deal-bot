import sys
import os
import requests
import time
import json
import re
from datetime import datetime
from bs4 import BeautifulSoup

os.environ["PYTHONUNBUFFERED"] = "1"
sys.stdout.reconfigure(line_buffering=True)

# ═══════════════════════════════════════════════════════════════
#  KONFIGURACJA
# ═══════════════════════════════════════════════════════════════
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
CHECK_INTERVAL     = 120
MAX_PRICE          = 2000
DISCOUNT_THRESHOLD = -80

MY_PRICES = {
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
}

SEARCH_QUERIES = [
    "iphone 13", "iphone 14", "iphone 15", "iphone 16",
    "samsung s23", "samsung s24", "samsung s25",
    "galaxy s23", "galaxy s24", "galaxy s25",
]

# Słowa które na pewno oznaczają akcesorium a nie telefon
ACCESSORY_KEYWORDS = [
    "etui", "case", "pokrowiec", "szklo", "szkło", "folia",
    "uchwyt", "ladowarka", "ładowarka", "kabel", "sluchawki",
    "słuchawki", "powerbank", "adapter", "atrapa", "naklejka",
    "tempered glass", "screen protector", "hoops", "huse", "husă",
]

DAMAGE_KEYWORDS = [
    "uszkodzon", "rozbity", "peknieto", "zbity", "nie dziala",
    "nie wlacza", "nie laduje", "awari", "do naprawy", "na czesci",
    "defekt", "wada", "problem z", "rysa", "zarysowanie",
    "damaged", "broken", "cracked", "faulty",
]

# ═══════════════════════════════════════════════════════════════
#  PAMIEC WIDZIANYCH OGLOSZEN
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
#  FILTR – czy to telefon a nie akcesorium
#  Sprawdza tylko czy tytul NIE zawiera slow akcesoriow
#  oraz czy zawiera nazwę modelu z naszej tabeli
# ═══════════════════════════════════════════════════════════════
def is_phone(title):
    t = title.lower()
    for kw in ACCESSORY_KEYWORDS:
        if kw in t:
            return False
    # musi zawierac chociaz jeden klucz z tabeli cen
    for key in MY_PRICES:
        if key in t:
            return True
    return False

# ═══════════════════════════════════════════════════════════════
#  SCRAPER OLX
# ═══════════════════════════════════════════════════════════════
def scrape_olx(query):
    results = []
    url = (
        f"https://www.olx.pl/elektronika/telefony/smartfony/"
        f"?search%5Bfilter_float_price%3Ato%5D={MAX_PRICE}"
        f"&search%5Bfilter_refiners%5D=spell_checker"
        f"&search%5Bq%5D={requests.utils.quote(query)}"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("div[data-cy='l-card']")
        print(f"[OLX] '{query}': kart={len(cards)}", flush=True)
        for card in cards:
            try:
                title_el = card.select_one("h6")
                price_el = card.select_one("p[data-testid='ad-price']")
                link_el  = card.select_one("a")
                img_el   = card.select_one("img")
                if not (title_el and price_el and link_el):
                    continue
                title     = title_el.text.strip()
                price_raw = price_el.text.strip()
                price     = parse_price(price_raw)
                link      = link_el.get("href", "")
                if not link.startswith("http"):
                    link = "https://www.olx.pl" + link
                image     = img_el.get("src", "") if img_el else ""
                card_text = card.get_text(" ", strip=True).lower()
                has_shipping = (
                    "wysylka olx" in card_text
                    or "dostawa olx" in card_text
                    or "kurier olx" in card_text
                    or bool(card.select_one("[data-testid='delivery-badge']"))
                    or bool(card.select_one("[data-cy='olx-delivery']"))
                )
                if price and price <= MAX_PRICE and is_phone(title):
                    results.append({
                        "id": link, "platform": "OLX",
                        "title": title, "price": price, "price_raw": price_raw,
                        "link": link, "image": image,
                        "has_shipping": has_shipping, "description": card_text,
                    })
            except Exception:
                continue
        print(f"[OLX] '{query}': telefonow={len(results)}", flush=True)
    except Exception as e:
        print(f"[OLX] Blad przy '{query}': {e}", flush=True)
    return results

# ═══════════════════════════════════════════════════════════════
#  SCRAPER VINTED
# ═══════════════════════════════════════════════════════════════
def scrape_vinted(query):
    results = []
    url = (
        f"https://www.vinted.pl/api/v2/catalog/items"
        f"?search_text={requests.utils.quote(query)}"
        f"&price_to={MAX_PRICE}&catalog_ids=2640&per_page=30&order=newest_first"
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
        raw_count = len(data.get("items", []))
        print(f"[Vinted] '{query}': raw={raw_count}", flush=True)
        for item in data.get("items", []):
            try:
                price = float(item.get("price", {}).get("amount", 9999))
                if price > MAX_PRICE:
                    continue
                title       = item.get("title", "")
                if not is_phone(title):
                    continue
                item_id     = str(item.get("id"))
                description = item.get("description", "").lower()
                link        = f"https://www.vinted.pl/items/{item_id}"
                image       = item.get("photo", {}).get("url", "")
                desc_full   = (title + " " + description).lower()
                results.append({
                    "id": f"vinted_{item_id}", "platform": "Vinted",
                    "title": title, "price": price, "price_raw": f"{price:.0f} zl",
                    "link": link, "image": image,
                    "has_shipping": True, "description": desc_full,
                })
            except Exception:
                continue
        print(f"[Vinted] '{query}': telefonow={len(results)}", flush=True)
    except Exception as e:
        print(f"[Vinted] Blad przy '{query}': {e}", flush=True)
    return results

# ═══════════════════════════════════════════════════════════════
#  HELPERY
# ═══════════════════════════════════════════════════════════════
def parse_price(text):
    digits = re.sub(r"[^\d]", "", text)
    return float(digits) if digits else None

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

def is_damaged(item):
    haystack = (item["title"] + " " + item.get("description", "")).lower()
    return any(kw in haystack for kw in DAMAGE_KEYWORDS)

# ═══════════════════════════════════════════════════════════════
#  WYSYLKA NA DISCORD
# ═══════════════════════════════════════════════════════════════
def send_discord(item, ref_price, storage_gb, model_key):
    pct     = discount_pct(item["price"], ref_price) if ref_price else None
    damaged = is_damaged(item)

    if damaged:
        color = 0x808080
    elif pct and pct >= 30:
        color = 0xFF4500
    elif pct and pct >= 20:
        color = 0xFFD700
    else:
        color = 0x00CC66

    if item["platform"] == "OLX":
        shipping_text = "TAK - Wysylka OLX" if item.get("has_shipping") else "NIE - tylko odbior osobisty"
    else:
        shipping_text = "TAK (Vinted)"

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
            {"name": "Cena ogloszenia",   "value": item["price_raw"],                               "inline": True},
            {"name": "Cena referencyjna", "value": ref_text,                                         "inline": True},
            {"name": "Platforma",         "value": item["platform"],                                 "inline": True},
            {"name": "Wykryty model",     "value": model_key.title() if model_key else "nieznany",   "inline": True},
            {"name": "Wykryta pamiec",    "value": gb_label(storage_gb),                             "inline": True},
            {"name": "Wysylka OLX",       "value": shipping_text,                                    "inline": False},
        ],
        "footer": {"text": f"PhoneDealBot  {datetime.now().strftime('%H:%M  %d.%m.%Y')}"},
    }
    if item.get("image"):
        embed["thumbnail"] = {"url": item["image"]}

    payload = {"username": "PhoneDealBot", "embeds": [embed]}
    for attempt in range(3):
        try:
            r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
            if r.status_code == 429:
                retry_after = float(r.json().get("retry_after", 2))
                print(f"[Discord] Rate limit, czekam {retry_after}s...", flush=True)
                time.sleep(retry_after + 0.5)
                continue
            if r.status_code not in (200, 204):
                print(f"[Discord] Blad: {r.status_code}", flush=True)
            break
        except Exception as e:
            print(f"[Discord] Wyjatek: {e}", flush=True)
            break
    time.sleep(1.5)

# ═══════════════════════════════════════════════════════════════
#  WSPOLNA LOGIKA PRZETWARZANIA
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
    for query in SEARCH_QUERIES:
        all_items.extend(scrape_olx(query))
        time.sleep(1)
        all_items.extend(scrape_vinted(query))
        time.sleep(1)
    return all_items

# ═══════════════════════════════════════════════════════════════
#  GLOWNA PETLA
# ═══════════════════════════════════════════════════════════════
def main():
    print("PhoneDealBot uruchomiony!", flush=True)
    print(f"Co {CHECK_INTERVAL // 60} min | Max: {MAX_PRICE} zl | Prog: {DISCOUNT_THRESHOLD}%", flush=True)

    seen      = load_seen()
    first_run = len(seen) == 0

    if first_run:
        print("Pierwsze uruchomienie – szukam okazji i zapisuje reszte...", flush=True)
        items = fetch_all()
        deal_count, skip_count = process_items(items, seen, send=True)
        save_seen(seen)
        print(f"Start: wyslano {deal_count} okazji, pominieto {skip_count} zwyklych.", flush=True)
        print(f"Nastepne sprawdzenie za {CHECK_INTERVAL // 60} min...", flush=True)
        time.sleep(CHECK_INTERVAL)

    while True:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sprawdzam nowe ogloszenia...", flush=True)
        items = fetch_all()
        deal_count, _ = process_items(items, seen, send=True)
        save_seen(seen)
        print(f"Nowych okazji: {deal_count}", flush=True)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
