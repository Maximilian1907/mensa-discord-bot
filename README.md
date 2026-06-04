# 🍽️ Mensa Discord Bot

Automatische Discord-Benachrichtigung wenn ein neuer Wochenplan für die Campus-Mensa online geht.

## So funktioniert's

```
Alle 30 Min (via GitHub Actions):
  → Mensa-Website scrapen ("Nächste Woche")
  → Mit letztem bekannten Plan vergleichen  
  → Wenn NEU → Schöne Nachricht an Discord senden 📨
```

## Setup in 5 Minuten

### 1️⃣ Discord Webhook erstellen

1. Öffne deinen **Discord Server**
2. Gehe zu **Server-Einstellungen → Integrationen → Webhooks**
3. Klicke **Neuer Webhook**
4. Wähle den Channel aus, in dem die Nachrichten erscheinen sollen
5. **Kopiere die Webhook-URL** (sieht aus wie `https://discord.com/api/webhooks/123.../abc...`)

### 2️⃣ GitHub Repository erstellen

1. Erstelle ein neues Repository auf [github.com](https://github.com/new) (kann privat sein)
2. Pushe diesen Ordner dorthin:
   ```bash
   cd Mensa_DC
   git init
   git add .
   git commit -m "Initial commit: Mensa Discord Bot"
   git branch -M main
   git remote add origin https://github.com/DEIN-USERNAME/mensa-discord-bot.git
   git push -u origin main
   ```

### 3️⃣ Webhook-URL als GitHub Secret speichern

1. Gehe in deinem Repo zu **Settings → Secrets and variables → Actions**
2. Klicke **New repository secret**
3. Name: `DISCORD_WEBHOOK_URL`
4. Value: Die kopierte Webhook-URL von Schritt 1
5. **Add secret**

### 4️⃣ GitHub Actions aktivieren

- GitHub Actions ist standardmäßig aktiviert
- Der Workflow läuft automatisch **alle 30 Minuten**
- Du kannst ihn auch manuell auslösen: **Actions → Mensa Speiseplan Check → Run workflow**

## Lokaler Test

```bash
# Dependencies installieren
pip install -r requirements.txt

# Test-Modus (zeigt Nachricht an, sendet nichts)
python scrape_mensa.py --test

# Mit echtem Discord-Post (Webhook-URL setzen)
set DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
python scrape_mensa.py

# Post erzwingen (auch wenn kein neuer Plan)
python scrape_mensa.py --force

# Aktuelle Woche statt nächste Woche prüfen
python scrape_mensa.py --check-current --test
```

## Befehle

| Flag | Beschreibung |
|---|---|
| `--test` | Zeigt die Discord-Nachricht nur an, sendet sie nicht |
| `--force` | Sendet auch wenn kein neuer Plan erkannt wurde |
| `--check-current` | Prüft die aktuelle statt die nächste Woche |

## Cron-Intervall ändern

In `.github/workflows/mensa_check.yml` die Zeile anpassen:

```yaml
# Alle 15 Minuten
- cron: '*/15 * * * *'

# Alle 30 Minuten (Standard)
- cron: '*/30 * * * *'

# Jede Stunde
- cron: '0 * * * *'

# Nur werktags 8-18 Uhr (spart Minuten)
- cron: '*/30 8-18 * * 1-5'
```

> 💡 **Tipp**: `*/30 8-18 * * 1-5` ist empfohlen – Speisepläne werden nur an Werktagen tagsüber aktualisiert. Das spart ~70% der GitHub Actions Minuten!

## Kosten

**Null.** GitHub Actions Free Tier bietet 2.000 Minuten/Monat. Dieser Bot braucht ca. 300-700 Min/Monat je nach Intervall.
