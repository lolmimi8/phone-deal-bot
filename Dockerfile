FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

Kliknij **Commit changes**.

---

## 🚀 Krok 2 – Rejestracja na Back4app

1. Wejdź na **https://www.back4app.com**
2. Kliknij **Sign up with GitHub** – nie wymaga karty kredytowej 
3. Zatwierdź dostęp do GitHub

---

## 🔗 Krok 3 – Utwórz aplikację

1. Po zalogowaniu kliknij **Build new app**
2. Wybierz **Containers as a Service** (nie "Backend as a Service")
3. Kliknij **Create app from GitHub repo**
4. Połącz konto GitHub jeśli jeszcze nie połączone → daj dostęp do swojego repo
5. Wybierz swoje repozytorium z listy → kliknij **Select**

---

## ⚙️ Krok 4 – Konfiguracja

Back4app Containers pozwala ustawić domyślny branch, katalog główny, auto-deploy i zmienne środowiskowe. 

Przed kliknięciem Deploy ustaw zmienną środowiskową:
- Znajdź sekcję **Environment Variables**
- Dodaj: **Key** = `DISCORD_WEBHOOK_URL`, **Value** = Twój URL webhooka z Discorda

Resztę zostaw domyślnie, wpisz nazwę aplikacji np. `phone-deal-bot` i kliknij **Create app**.

---

## ✅ Krok 5 – Czekasz na build

Back4app zajmie chwilę na zbudowanie kontenera i jego uruchomienie. Gdy status zmieni się na "Ready" – bot działa. 

W panelu wejdź w **Logs** i powinieneś zobaczyć:
```
PhoneDealBot v3 uruchomiony!
Co 2 min | Max: 2000 zl | Prog: -10%
[10:32:00] Sprawdzam ogloszenia...
