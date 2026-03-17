import requests
import time
import json
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup

# ═══════════════════════════════════════════════════════════════
#  KONFIGURACJA – TUTAJ WPISUJESZ SWOJE WARTOŚCI
# ═══════════════════════════════════════════════════════════════
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "WSTAW_SWOJ_WEBHOOK_URL")
CHECK_INTERVAL = 120   # sekundy (co 2 minuty)
MAX_PRICE      = 2000  # PLN – górny limit ceny ogłoszenia

# ── PRÓG OKAZJI ──────────────────────────────────────────────
# Bot wyśle powiadomienie tylko gdy cena jest CO NAJMNIEJ tyle
# procent niższa niż Twoja cena referencyjna poniżej.
DISCOUNT_THRESHOLD = 10  # % (10 = co najmniej 10% taniej)

# ── TWOJE CENY REFERENCYJNE ──────────────────────────────────
# Wpisz tutaj ile według Ciebie wart jest każdy model (w PLN).
# Bot porówna cenę ogłoszenia z tą wartością.
# Klucze MUSZĄ być małymi literami.
MY_PRICES = {
    # ── iPhone ────────────────────────────────────────────────
    "iphone 13":           2200,
    "iphone 13 pro":       2800,
    "iphone 13 pro max":   3200,
    "iphone 14":           2800,
    "iphone 14 pro":       3500,
    "iphone 14 pro max":   4000,
    "iphone 15":           3500,
    "iphone 15 pro":       4200,
    "iphone 15 pro max":   4800,
    "iphone 16":           4000,
    "iphone 16 pro":       5000,
    "iphone 16 pro max":   5600,
    # ── Samsung Galaxy S ──────────────────────────────────────
    "galaxy s23":          1800,
    "samsung s23":         1800,
    "galaxy s23+":         2200,
    "samsung s23+":        2200,
    "galaxy s23 ultra":    2800,
    "samsung s23 ultra":   2800,
    "galaxy s24":          2200,
    "samsung s24":         2200,
    "galaxy s24+":         2700,
    "samsung s24+":        2700,
    "galaxy s24 ultra":    3500,
    "samsung s24 ultra":   3500,
    "galaxy s25":          3000,
    "samsung s25":         3000,
    "galaxy s25+":         3600,
    "samsung s25+":        3600,
    "galaxy s25 ultra":    4200,
    "samsung s25 ultra":   4200,
}

# ── SŁOWA KLUCZOWE WYSZUKIWANIA ───────────────────────────────
SEARCH_QUERIES = [
    "iphone 13", "iphone 14", "iphone 15", "iphone 16",
    "samsung s23", "samsung s24", "samsung s25",
    "galaxy s23", "galaxy s24", "galaxy s25",
]

# ── SŁOWA SUGERUJĄCE USZKODZENIE ──────────────────────────────
DAMAGE_KEYWORDS = [
    "uszkodzon", "rozbity", "pęknięt", "zbity", "nie działa",
    "nie włącza", "nie ładuje", "awari", "do naprawy", "na części",
    "defekt", "wada", "problem z", "rysa", "zarysowanie",
    "damaged", "broken", "cracked", "faulty",
]

# ═══════════════════════════════════════════════════════════════
#  PAMIĘĆ
# ═══════════════════════════════════════════════════════════════
SEEN_FILE = "seen_listings.json"

def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

# ═══════════════════════════════════════════════════════════════
#  SCRAPER OLX
# ═══════════════════════════════════════════════════════════════
def scrape_olx(query: str) -> list[dict]:
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
                image = img_el.get("src", "") if img_el else ""

                card_text = card.get_text(" ", strip=True).lower()
                has_shipping = (
                    "wysyłka olx" in card_text
                    or "dostawa olx" in card_text
                    or "kurier olx" in card_text
                    or bool(card.select_one("[data-testid='delivery-badge']"))
                    or bool(card.select_one("[data-cy='olx-delivery']"))
                )

                if price and price <= MAX_PRICE:
                    results.append({
                        "id":           link,
                        "platform":     "OLX",
                        "title":        title,
                        "price":        price,
                        "price_raw":    price_raw,
                        "link":         link,
                        "image":        image,
                        "has_shipping": has_shipping,
                        "description":  card_text,
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"[OLX] Blad przy '{query}': {e}")
    return results

# ═══════════════════════════════════════════════════════════════
#  SCRAPER VINTED
# ═══════════════════════════════════════════════════════════════
def scrape_vinted(query: str) -> list[dict]:
    results = []
    url = (
        f"https://www.vinted.pl/api/v2/catalog/items"
        f"?search_text={requests.utils.quote(query)}"
        f"&price_to={MAX_PRICE}&catalog_ids=1&per_page=30&order=newest_first"
    )
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    try:
        session = requests.Session()
        session.get("https://www.vinted.pl", headers=headers, timeout=10)
        r = session.get(url, headers=headers, timeout=15)
        data = r.json()
        for item in data.get("items", []):
            try:
                price = float(item.get("price", {}).get("amount", 9999))
                if price > MAX_PRICE:
                    continue
                item_id     = str(item.get("id"))
                title       = item.get("title", "")
                description = item.get("description", "").lower()
                link        = f"https://www.vinted.pl/items/{item_id}"
                image       = item.get("photo", {}).get("url", "")
                results.append({
                    "id":           f"vinted_{item_id}",
                    "platform":     "Vinted",
                    "title":        title,
                    "price":        price,
                    "price_raw":    f"{price:.0f} zl",
                    "link":         link,
                    "image":        image,
                    "has_shipping": True,
                    "description":  description,
                })
            except Exception:
                continue
    except Exception as e:
        print(f"[Vinted] Blad przy '{query}': {e}")
    return results

# ═══════════════════════════════════════════════════════════════
#  HELPERY
# ═══════════════════════════════════════════════════════════════
def parse_price(text: str) -> float | None:
    digits = re.sub(r"[^\d]", "", text)
    return float(digits) if digits else None

def get_my_price(title: str) -> int | None:
    t = title.lower()
    best, best_len = None, 0
    for key, price in MY_PRICES.items():
        if key in t and len(key) > best_len:
            best, best_len = price, len(key)
    return best

def discount_pct(price: float, ref: int) -> int:
    return round((1 - price / ref) * 100)

def is_damaged(item: dict) -> bool:
    haystack = (item["title"] + " " + item.get("description", "")).lower()
    return any(kw in haystack for kw in DAMAGE_KEYWORDS)

# ═══════════════════════════════════════════════════════════════
#  WYSYLKA NA DISCORD
# ═══════════════════════════════════════════════════════════════
def send_discord(item: dict, ref_price: int | None):
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

    ref_text      = f"{ref_price} zl" if ref_price else "brak danych"
    discount_text = f"**-{pct}% taniej niz Twoja cena referencyjna!**" if pct else ""
    damage_text   = "UWAGA: ogloszenie moze dotyczyc uszkodzonego telefonu!" if damaged else "Brak oznak uszkodzenia"

    desc_parts = []
    if discount_text:
        desc_parts.append(f"OKAZJA {discount_text}")
    desc_parts.append(damage_text)

    embed = {
        "title":       f"Nowe ogloszenie: {item['title']}",
        "url":         item["link"],
        "color":       color,
        "description": "\n".join(desc_parts),
        "fields": [
            {"name": "Cena",                    "value": item["price_raw"], "inline": True},
            {"name": "Twoja cena referencyjna", "value": ref_text,          "inline": True},
            {"name": "Platforma",               "value": item["platform"],  "inline": True},
            {"name": "Wysylka OLX",             "value": shipping_text,     "inline": False},
        ],
        "footer": {
            "text": f"PhoneDealBot • {datetime.now().strftime('%H:%M  %d.%m.%Y')}"
        },
    }
    if item.get("image"):
        embed["thumbnail"] = {"url": item["image"]}

    payload = {"username": "PhoneDealBot", "embeds": [embed]}
    try:
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if r.status_code not in (200, 204):
            print(f"[Discord] Blad wysylki: {r.status_code} {r.text}")
    except Exception as e:
        print(f"[Discord] Wyjatek: {e}")

# ═══════════════════════════════════════════════════════════════
#  GLOWNA PETLA
# ═══════════════════════════════════════════════════════════════
def main():
    print("PhoneDealBot uruchomiony!")
    print(f"   Sprawdzam co {CHECK_INTERVAL // 60} min | Max cena: {MAX_PRICE} zl | Prog: -{DISCOUNT_THRESHOLD}%")
    seen = load_seen()

    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Sprawdzam ogloszenia...")
        all_items: list[dict] = []

        for query in SEARCH_QUERIES:
            all_items.extend(scrape_olx(query))
            all_items.extend(scrape_vinted(query))
            time.sleep(1)

        new_count = 0
        for item in all_items:
            if item["id"] in seen:
                continue
            seen.add(item["id"])

            ref = get_my_price(item["title"])

            if ref and item["price"] >= ref * (1 - DISCOUNT_THRESHOLD / 100):
                continue

            label = "OKAZJA (mozliwe uszkodzenie)" if is_damaged(item) else "OKAZJA"
            print(f"  {label}: {item['title']} | {item['price_raw']} | {item['platform']}")
            send_discord(item, ref)
            new_count += 1
            time.sleep(0.5)

        save_seen(seen)
        print(f"  -> Nowych okazji: {new_count}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
