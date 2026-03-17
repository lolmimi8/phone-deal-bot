import requests
import time
import json
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
 
# ═══════════════════════════════════════════════════════════════
#  KONFIGURACJA
# ═══════════════════════════════════════════════════════════════
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1483519597867958293/xJz8iUw4im81cPHBdiKbAM-F4zcbqpiQnoTLD4soNsdFVkET9PDltRpVOD2ZshtMQlXz")
CHECK_INTERVAL     = 120   # sekundy (co 2 minuty)
MAX_PRICE          = 2000  # PLN – górny limit ceny ogłoszenia
DISCOUNT_THRESHOLD = 10    # % – bot wysyła tylko gdy cena jest >= X% niżej od referencyjnej
 
# ═══════════════════════════════════════════════════════════════
#  TABELA CEN REFERENCYJNYCH  (model → pamięć → cena PLN)
#
#  Format klucza modelu: ZAWSZE małe litery, bez "iphone"/"samsung"/"galaxy"
#  Format klucza pamięci: liczba całkowita GB (np. 128, 256, 512, 1024)
#  Jeśli dany wariant nie jest podany, bot użyje ceny bazowej lub pominie
# ═══════════════════════════════════════════════════════════════
MY_PRICES: dict[str, dict[int, int]] = {
    # ── Samsung S23 ───────────────────────────────────────────
    "samsung s23":        {128: 650,  256: 780},
    "galaxy s23":         {128: 650,  256: 780},
    "samsung s23+":       {128: 800,  256: 800},
    "galaxy s23+":        {128: 800,  256: 800},
    "samsung s23 ultra":  {256: 1040, 512: 1140},
    "galaxy s23 ultra":   {256: 1040, 512: 1140},
    # ── Samsung S24 ───────────────────────────────────────────
    "samsung s24":        {128: 880,  256: 940},
    "galaxy s24":         {128: 880,  256: 940},
    "samsung s24+":       {256: 1130, 512: 1200},
    "galaxy s24+":        {256: 1130, 512: 1200},
    "samsung s24 ultra":  {256: 1450, 512: 1500},
    "galaxy s24 ultra":   {256: 1450, 512: 1500},
    # ── Samsung S25 ── (ceny nie podane – zostawiam puste, bot pominie) ──
    "samsung s25":        {},
    "galaxy s25":         {},
    "samsung s25+":       {},
    "galaxy s25+":        {},
    "samsung s25 ultra":  {},
    "galaxy s25 ultra":   {},
    # ── iPhone 13 ─────────────────────────────────────────────
    "iphone 13":          {128: 600,  256: 700,  512: 570},
    "iphone 13 pro":      {128: 800,  256: 900,  512: 1000, 1024: 1120},
    "iphone 13 pro max":  {128: 870,  256: 1060, 512: 1090, 1024: 1120},
    # ── iPhone 14 ─────────────────────────────────────────────
    "iphone 14":          {128: 790,  256: 860,  512: 920},
    "iphone 14+":         {128: 860,  256: 890,  512: 950},
    "iphone 14 plus":     {128: 860,  256: 890,  512: 950},
    "iphone 14 pro":      {128: 1020, 256: 1140, 512: 1270, 1024: 1340},
    "iphone 14 pro max":  {128: 1210, 256: 1240, 512: 1270, 1024: 1340},
    # ── iPhone 15 ─────────────────────────────────────────────
    "iphone 15":          {128: 1020, 256: 1270, 512: 1460},
    "iphone 15 plus":     {128: 1240, 256: 1300, 512: 1420},
    "iphone 15+":         {128: 1240, 256: 1300, 512: 1420},
    # ── iPhone 15 Pro / Pro Max – ceny nie podane, zostawiam puste ──
    "iphone 15 pro":      {},
    "iphone 15 pro max":  {},
    # ── iPhone 16 – ceny nie podane, zostawiam puste ──────────
    "iphone 16":          {},
    "iphone 16 plus":     {},
    "iphone 16+":         {},
    "iphone 16 pro":      {},
    "iphone 16 pro max":  {},
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
#  PAMIĘĆ – żeby nie wysyłać dwa razy tego samego
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
#  WYKRYWANIE MODELU I PAMIĘCI Z TYTUŁU OGŁOSZENIA
# ═══════════════════════════════════════════════════════════════
 
def extract_storage_gb(text: str) -> int | None:
    """
    Wyciąga pojemność pamięci z tekstu ogłoszenia.
    Obsługuje formaty: 128gb, 128 gb, 128GB, 1TB, 1tb, 1 TB itp.
    Zwraca liczbę GB jako int (1TB → 1024).
    """
    t = text.lower()
    # szukaj TB najpierw (żeby "1tb" nie zostało złapane jako "1" przez wzorzec GB)
    tb_match = re.search(r'(\d+)\s*tb', t)
    if tb_match:
        return int(tb_match.group(1)) * 1024
 
    gb_match = re.search(r'(\d+)\s*gb', t)
    if gb_match:
        return int(gb_match.group(1))
 
    return None
 
 
def get_ref_price(title: str, description: str = "") -> tuple[int | None, int | None, str | None]:
    """
    Zwraca (cena_referencyjna, wykryta_pamięć_gb, nazwa_modelu).
    Przeszukuje tytuł + opis, dopasowuje najdłuższy klucz modelu,
    a następnie dopasowuje pojemność pamięci.
    """
    haystack = (title + " " + description).lower()
 
    # 1. Znajdź model (najdłuższy pasujący klucz)
    best_key, best_len = None, 0
    for key in MY_PRICES:
        if key in haystack and len(key) > best_len:
            best_key, best_len = key, len(key)
 
    if best_key is None:
        return None, None, None
 
    storage_variants = MY_PRICES[best_key]
 
    # Jeśli brak wariantów dla modelu – nie mamy ceny
    if not storage_variants:
        return None, None, best_key
 
    # 2. Wykryj pamięć z ogłoszenia
    detected_gb = extract_storage_gb(haystack)
 
    if detected_gb and detected_gb in storage_variants:
        return storage_variants[detected_gb], detected_gb, best_key
 
    # 3. Jeśli nie wykryto GB lub nie ma go w tabeli – weź najbliższy dostępny wariant
    #    (żeby nie odrzucać ogłoszeń gdzie sprzedający nie napisał pojemności)
    if storage_variants:
        # użyj najniższej dostępnej ceny jako "pesymistycznej" referencji
        fallback_gb    = min(storage_variants.keys())
        fallback_price = storage_variants[fallback_gb]
        return fallback_price, detected_gb, best_key   # detected_gb może być None
 
    return None, None, best_key
 
 
def discount_pct(price: float, ref: int) -> int:
    return round((1 - price / ref) * 100)
 
# ═══════════════════════════════════════════════════════════════
#  WYKRYWANIE USZKODZEŃ
# ═══════════════════════════════════════════════════════════════
def is_damaged(item: dict) -> bool:
    haystack = (item["title"] + " " + item.get("description", "")).lower()
    return any(kw in haystack for kw in DAMAGE_KEYWORDS)
 
# ═══════════════════════════════════════════════════════════════
#  POMOCNICZE
# ═══════════════════════════════════════════════════════════════
def parse_price(text: str) -> float | None:
    digits = re.sub(r"[^\d]", "", text)
    return float(digits) if digits else None
 
def gb_label(gb: int | None) -> str:
    if gb is None:
        return "nieznana"
    if gb >= 1024:
        return f"{gb // 1024}TB"
    return f"{gb}GB"
 
# ═══════════════════════════════════════════════════════════════
#  WYSYŁKA NA DISCORD
# ═══════════════════════════════════════════════════════════════
def send_discord(item: dict, ref_price: int | None, storage_gb: int | None, model_key: str | None):
    pct     = discount_pct(item["price"], ref_price) if ref_price else None
    damaged = is_damaged(item)
 
    # Kolor embeda
    if damaged:
        color = 0x808080
    elif pct and pct >= 30:
        color = 0xFF4500
    elif pct and pct >= 20:
        color = 0xFFD700
    else:
        color = 0x00CC66
 
    # Wysyłka
    if item["platform"] == "OLX":
        shipping_text = "TAK - Wysylka OLX" if item.get("has_shipping") else "NIE - tylko odbior osobisty"
    else:
        shipping_text = "TAK (Vinted)"
 
    # Cena referencyjna
    if ref_price:
        storage_info  = gb_label(storage_gb)
        ref_text      = f"{ref_price} zl ({storage_info})"
        discount_text = f"-{pct}% taniej niz cena referencyjna!" if pct else ""
    else:
        ref_text      = "brak danych dla tego modelu/pamieci"
        discount_text = ""
 
    # Model
    model_text = model_key.title() if model_key else "nieznany"
 
    # Pamiec wykryta z ogłoszenia
    storage_detected = gb_label(storage_gb)
 
    # Uszkodzenie
    damage_text = "UWAGA: moze byc uszkodzony!" if damaged else "Brak oznak uszkodzenia"
 
    desc_parts = []
    if discount_text:
        desc_parts.append(f"OKAZJA  {discount_text}")
    desc_parts.append(damage_text)
 
    embed = {
        "title":       f"Nowe ogloszenie: {item['title']}",
        "url":         item["link"],
        "color":       color,
        "description": "\n".join(desc_parts),
        "fields": [
            {"name": "Cena ogloszenia",         "value": item["price_raw"],  "inline": True},
            {"name": "Cena referencyjna",        "value": ref_text,           "inline": True},
            {"name": "Platforma",                "value": item["platform"],   "inline": True},
            {"name": "Wykryty model",            "value": model_text,         "inline": True},
            {"name": "Wykryta pamiec",           "value": storage_detected,   "inline": True},
            {"name": "Wysylka OLX",              "value": shipping_text,      "inline": False},
        ],
        "footer": {
            "text": f"PhoneDealBot  {datetime.now().strftime('%H:%M  %d.%m.%Y')}"
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
#  GŁÓWNA PĘTLA
# ═══════════════════════════════════════════════════════════════
def main():
    print("PhoneDealBot v3 uruchomiony!")
    print(f"   Co {CHECK_INTERVAL // 60} min | Max: {MAX_PRICE} zl | Prog: -{DISCOUNT_THRESHOLD}%")
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
 
            ref_price, storage_gb, model_key = get_ref_price(
                item["title"], item.get("description", "")
            )
 
            # Filtr cenowy
            if ref_price and item["price"] >= ref_price * (1 - DISCOUNT_THRESHOLD / 100):
                continue
 
            label = "(mozl. uszkodzony)" if is_damaged(item) else ""
            storage_str = gb_label(storage_gb)
            print(f"  OKAZJA {label}: {item['title']} | {item['price_raw']} | {storage_str} | {item['platform']}")
            send_discord(item, ref_price, storage_gb, model_key)
            new_count += 1
            time.sleep(0.5)
 
        save_seen(seen)
        print(f"  -> Nowych okazji: {new_count}")
        time.sleep(CHECK_INTERVAL)
 
if __name__ == "__main__":
    main()
