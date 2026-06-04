#!/usr/bin/env python3
"""
Mensa Discord Bot – Scraper & Notifier
=======================================
Scrapt den Speiseplan der Campus-Mensa (nächste Woche) und
postet bei Änderungen eine formatierte Nachricht an Discord.

Verwendung:
    python scrape_mensa.py                    # Normaler Check
    python scrape_mensa.py --force             # Erzwingt Discord-Post (ignoriert Hash)
    python scrape_mensa.py --test              # Zeigt Output ohne Discord-Post
"""

import os
import sys
import json
import hashlib
import argparse
import logging
from datetime import datetime, timezone

# Windows-Konsole auf UTF-8 setzen damit Emojis korrekt ausgegeben werden
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests
from bs4 import BeautifulSoup

# ──────────────────────────────────────────────
# Konfiguration
# ──────────────────────────────────────────────

MENSA_URL = "https://mensa.campus-company.eu/"
NAECHSTE_WOCHE_URL = MENSA_URL + "?shortcode_render=speiseplan_grid&woche=naechste&lang=de"
AKTUELLE_WOCHE_URL = MENSA_URL + "?shortcode_render=speiseplan_grid&woche=aktuell&lang=de"
HASH_FILE = "last_plan_hash.txt"
LAST_WEEK_FILE = "last_plan_week.txt"
USER_AGENT = "MensaBot/1.0 (Discord Notification Bot)"

# Kategorie-Emojis für Discord
KATEGORIE_EMOJIS = {
    "geflügel":     "🍗",
    "gefluegel":    "🍗",
    "rind":         "🥩",
    "schwein":      "🐷",
    "rind/schwein": "🥩",
    "vegan":        "🌱",
    "vegetarisch":  "🥬",
    "fisch":        "🐟",
    "spezial":      "⭐",
    "wild":         "🦌",
}

# Embed-Farben pro Kategorie (Discord braucht Dezimalwerte)
KATEGORIE_FARBEN = {
    "geflügel":     0xF5B441,
    "rind":         0xF29938,
    "schwein":      0xF0AA6E,
    "rind/schwein": 0xE88A3A,
    "vegan":        0x6ABF4B,
    "vegetarisch":  0x78AA46,
    "fisch":        0x5B9BD5,
    "spezial":      0xFFD700,
    "wild":         0x8B4513,
}

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("MensaBot")


# ──────────────────────────────────────────────
# Scraping
# ──────────────────────────────────────────────

def fetch_html(url: str) -> str | None:
    """Fetcht den HTML-Inhalt einer URL."""
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        log.error(f"Fehler beim Laden von {url}: {e}")
        return None


def parse_speiseplan(html: str) -> dict | None:
    """
    Parst den Speiseplan-HTML und extrahiert strukturierte Daten.
    
    Rückgabe-Format:
    {
        "wochentitel": "08.06.2026 – 12.06.2026",
        "tage": [
            {
                "name": "Montag",
                "datum": "08.06.2026",
                "geschlossen": False,
                "gerichte": [
                    {
                        "kategorie": "geflügel",
                        "titel": "Puten-Burger",
                        "komponenten": "Putenschnitzel auf Brioche Bun...",
                        "inhaltsstoffe": "A, C, G, L, M, O",
                        "preis_studierende": "4,00 €",
                        "preis_gaeste": "6,40 €",
                    },
                    ...
                ]
            },
            ...
        ]
    }
    """
    soup = BeautifulSoup(html, "html.parser")
    
    # Wochentitel extrahieren
    wochentitel_el = soup.find("h2", class_="speiseplan-wochentitel")
    if not wochentitel_el:
        log.warning("Kein Wochentitel gefunden – Plan vermutlich noch nicht online.")
        return None
    
    wochentitel = wochentitel_el.get_text(strip=True)
    
    # Tage extrahieren
    tage = []
    tag_divs = soup.find_all("div", class_="speiseplan-tag")
    
    if not tag_divs:
        log.warning("Keine Tage im Speiseplan gefunden.")
        return None
    
    for tag_div in tag_divs:
        tag_name_el = tag_div.find("h3", class_="speiseplan-tag-titel")
        tag_datum_el = tag_div.find("div", class_="speiseplan-tag-datum")
        
        tag_name = tag_name_el.get_text(strip=True) if tag_name_el else "Unbekannt"
        tag_datum = tag_datum_el.get_text(strip=True) if tag_datum_el else ""
        
        # Prüfe ob Mensa geschlossen
        geschlossen_el = tag_div.find("div", class_="speiseplan-mensa-geschlossen")
        if geschlossen_el:
            tage.append({
                "name": tag_name,
                "datum": tag_datum,
                "geschlossen": True,
                "gerichte": [],
            })
            continue
        
        # Gerichte extrahieren
        gerichte = []
        gericht_divs = tag_div.find_all("div", class_="speiseplan-gericht")
        
        for gericht_div in gericht_divs:
            kategorie_el = gericht_div.find("div", class_="speiseplan-kategorie")
            titel_el = gericht_div.find("h4", class_="speiseplan-titel")
            komponenten_el = gericht_div.find("div", class_="speiseplan-komponenten")
            inhaltsstoffe_el = gericht_div.find("div", class_="speiseplan-inhaltsstoffe")
            preis_stud_el = gericht_div.find("span", class_="preis-studierende")
            preis_gast_el = gericht_div.find("span", class_="preis-gaeste")
            
            # data-kategorie Attribut bevorzugen (normalisiert)
            kategorie_raw = gericht_div.get("data-kategorie", "")
            if not kategorie_raw and kategorie_el:
                kategorie_raw = kategorie_el.get_text(strip=True)
            kategorie = kategorie_raw.lower().strip()
            
            gerichte.append({
                "kategorie": kategorie,
                "titel": titel_el.get_text(strip=True) if titel_el else "–",
                "komponenten": komponenten_el.get_text(strip=True) if komponenten_el else "",
                "inhaltsstoffe": inhaltsstoffe_el.get_text(strip=True) if inhaltsstoffe_el else "",
                "preis_studierende": preis_stud_el.get_text(strip=True) if preis_stud_el else "–",
                "preis_gaeste": preis_gast_el.get_text(strip=True) if preis_gast_el else "–",
            })
        
        tage.append({
            "name": tag_name,
            "datum": tag_datum,
            "geschlossen": False,
            "gerichte": gerichte,
        })
    
    if not tage:
        return None
    
    return {
        "wochentitel": wochentitel,
        "tage": tage,
    }


def fetch_extras() -> dict:
    """
    Holt Ankündigungen und Angebote von der Hauptseite.
    
    Rückgabe:
    {
        "ankuendigung": "📣 AKTION AM MITTWOCH: ...",     # Banner oben
        "angebote": [                                       # Popup "Angebot der Woche"
            {
                "titel": "Currywurst",
                "beschreibung": "aus Rindfleisch oder vegan, mit Pommes",
                "preis": "S: 3,10 € / G: 4,50 €"
            },
            ...
        ]
    }
    """
    result = {"ankuendigung": None, "angebote": []}
    
    html = fetch_html(MENSA_URL)
    if not html:
        return result
    
    soup = BeautifulSoup(html, "html.parser")
    
    # 1) Banner-Ankündigung (z.B. "AKTION AM MITTWOCH: Süßkartoffelpommes...")
    banner = soup.find("div", class_="speiseplan-ankuendigung-banner")
    if banner:
        text = banner.get_text(strip=True)
        if text:
            result["ankuendigung"] = text
    
    # 2) "Angebot der Woche"-Popup (Currywurst, Pasta, Pizza etc.)
    popup = soup.find("div", id="speiseplan-popup")
    if popup:
        popup_inhalt = popup.find("div", class_="popup-inhalt")
        if popup_inhalt:
            # Titel des Popups (z.B. "Angebot der Woche")
            popup_titel_el = popup_inhalt.find("h3")
            
            # Alle Angebote aus den <p>-Tags extrahieren
            angebot_paragraphs = popup_inhalt.find_all("p")
            
            current_angebot = None
            for p in angebot_paragraphs:
                text = p.get_text(separator="\n", strip=True)
                if not text:
                    continue
                
                # Jedes <p> enthält typischerweise:
                # <strong>Titel</strong>, Beschreibung\n EN-Text\n Preis
                strong = p.find("strong")
                if strong:
                    titel = strong.get_text(strip=True)
                    
                    # Restlichen Text nach dem Titel extrahieren
                    full_text = p.get_text(separator="\n", strip=True)
                    lines = [l.strip() for l in full_text.split("\n") if l.strip()]
                    
                    # Beschreibung = alles nach dem Titel, ohne EN-Text und Preis
                    beschreibung_lines = []
                    preis = ""
                    
                    for line in lines:
                        if line == titel:
                            continue
                        # Preise erkennen (S: X,XX € / G: X,XX €)
                        if "€" in line and ("S:" in line or "G:" in line):
                            preis = line
                        # Englische Übersetzungen überspringen
                        elif not any(en_word in line.lower() for en_word in ["made from", "with fries", "with tomato", "soy bolognese"]):
                            beschreibung_lines.append(line)
                    
                    # Beschreibung zusammenbauen und führende Satzzeichen entfernen
                    beschreibung = ", ".join(beschreibung_lines) if beschreibung_lines else ""
                    # Führendes Komma/Leerzeichen entfernen (z.B. ", aus Rindfleisch...")
                    beschreibung = beschreibung.lstrip(" ,;")
                    
                    result["angebote"].append({
                        "titel": titel,
                        "beschreibung": beschreibung,
                        "preis": preis,
                    })
                elif "€" in text:
                    # Manchmal ist der Preis in einem separaten <p>
                    if result["angebote"] and not result["angebote"][-1].get("preis"):
                        result["angebote"][-1]["preis"] = text.strip()
    
    return result


# ──────────────────────────────────────────────
# Hash / State Management
# ──────────────────────────────────────────────

def compute_hash(plan: dict) -> str:
    """Berechnet einen SHA256-Hash über den Speiseplan-Inhalt."""
    # Nur die relevanten Daten hashen, nicht Timestamps etc.
    content = json.dumps(plan, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_last_hash() -> str | None:
    """Lädt den zuletzt gespeicherten Hash."""
    if os.path.exists(HASH_FILE):
        with open(HASH_FILE, "r") as f:
            return f.read().strip()
    return None


def load_last_week() -> str | None:
    """Lädt den zuletzt gespeicherten Wochentitel."""
    if os.path.exists(LAST_WEEK_FILE):
        with open(LAST_WEEK_FILE, "r") as f:
            return f.read().strip()
    return None


def save_state(plan_hash: str, wochentitel: str):
    """Speichert den aktuellen Hash und Wochentitel."""
    with open(HASH_FILE, "w") as f:
        f.write(plan_hash)
    with open(LAST_WEEK_FILE, "w") as f:
        f.write(wochentitel)


# ──────────────────────────────────────────────
# Discord Embeds
# ──────────────────────────────────────────────

def build_discord_message(plan: dict, extras: dict | None = None, is_update: bool = False) -> dict:
    """
    Baut die Discord Webhook-Nachricht mit Embeds.
    
    Struktur:
    - 1 Hauptembed mit Wochentitel + Vollständigkeitsanzeige
    - Inhalt: Pro Tag die Gerichte als formatierter Text
    - Angebote der Woche (Currywurst, Pizza etc.)
    """
    if extras is None:
        extras = {"ankuendigung": None, "angebote": []}
    
    ankuendigung = extras.get("ankuendigung")
    angebote = extras.get("angebote", [])
    wochentitel = plan["wochentitel"]
    
    # KW berechnen aus dem ersten Datum
    kw_str = ""
    kw_nr = ""
    if plan["tage"]:
        first_datum = plan["tage"][0].get("datum", "")
        try:
            dt = datetime.strptime(first_datum, "%d.%m.%Y")
            kw_nr = str(dt.isocalendar()[1])
            kw_str = f" (KW {kw_nr})"
        except ValueError:
            pass
    
    # Vollständigkeit berechnen
    total_tage = len(plan["tage"])
    tage_mit_inhalt = sum(
        1 for t in plan["tage"]
        if t["geschlossen"] or len(t["gerichte"]) > 0
    )
    is_vollstaendig = tage_mit_inhalt == total_tage
    
    # Embed-Beschreibung aufbauen
    description_parts = []
    
    if ankuendigung:
        description_parts.append(f"📣 **{ankuendigung}**\n")
    
    description_parts.append(f"🗓️ **Woche: {wochentitel}{kw_str}**")
    
    # Vollständigkeitsstatus
    if is_vollstaendig:
        description_parts.append(f"✅ *Plan vollständig – {tage_mit_inhalt}/{total_tage} Tage*\n")
    else:
        description_parts.append(f"⏳ *Plan noch unvollständig – {tage_mit_inhalt}/{total_tage} Tage geplant*\n")
    
    # Pro Tag
    for tag in plan["tage"]:
        # Tag-Datum kürzen (nur Tag.Monat.)
        datum_kurz = tag["datum"]
        if datum_kurz:
            parts = datum_kurz.split(".")
            if len(parts) >= 2:
                datum_kurz = f"{parts[0]}.{parts[1]}."
        
        tag_header = f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n📅 **{tag['name'].upper()}** ({datum_kurz})\n"
        description_parts.append(tag_header)
        
        if tag["geschlossen"]:
            description_parts.append("🚫 *Mensa geschlossen*\n")
            continue
        
        if not tag["gerichte"]:
            description_parts.append("🕐 *Noch nicht geplant – wird nachgereicht*\n")
            continue
        
        for gericht in tag["gerichte"]:
            emoji = KATEGORIE_EMOJIS.get(gericht["kategorie"], "🍽️")
            kat_label = gericht["kategorie"].upper() if gericht["kategorie"] else "GERICHT"
            
            lines = []
            lines.append(f"{emoji} **{kat_label}:** {gericht['titel']}")
            
            if gericht["komponenten"]:
                lines.append(f"┗ {gericht['komponenten']}")
            
            preis_line = f"💰 Stud: **{gericht['preis_studierende']}** │ Gäste: **{gericht['preis_gaeste']}**"
            lines.append(preis_line)
            
            if gericht["inhaltsstoffe"]:
                lines.append(f"🏷️ _{gericht['inhaltsstoffe']}_")
            
            description_parts.append("\n".join(lines) + "\n")
    
    # Angebote der Woche hinzufügen
    if angebote:
        description_parts.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━")
        description_parts.append("🏷️ **ANGEBOTE DER WOCHE** *(Mo–Do)*\n")
        for angebot in angebote:
            angebot_lines = [f"🔸 **{angebot['titel']}**"]
            if angebot.get("beschreibung"):
                angebot_lines.append(f"┗ {angebot['beschreibung']}")
            if angebot.get("preis"):
                angebot_lines.append(f"💰 {angebot['preis']}")
            description_parts.append("\n".join(angebot_lines) + "\n")
    
    full_description = "\n".join(description_parts)
    
    # Titel und Content je nach Erst-/Aktualisierungsnachricht
    if is_update:
        content_text = f"🔄 **Speiseplan KW {kw_nr} wurde aktualisiert!**"
        title_text = f"🔄 Aktualisierung Mensa-Wochenplan{kw_str}"
    else:
        content_text = "📢 **Der Speiseplan für nächste Woche ist da!**"
        title_text = f"🍽️ Neuer Mensa-Wochenplan{kw_str}"
    
    # Discord Embeds haben ein Limit von 4096 Zeichen pro Beschreibung.
    # Falls zu lang, splitten wir auf mehrere Embeds auf.
    embeds = []
    
    if len(full_description) <= 4096:
        embeds.append({
            "title": title_text,
            "description": full_description,
            "color": 0x2ECC71 if is_vollstaendig else 0xF39C12,  # Grün oder Orange
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {
                "text": "Campus Restaurant Culinaria │ Automatisch geprüft"
            },
            "url": MENSA_URL,
        })
    else:
        # Aufteilen: Header-Embed + ein Embed pro Tag
        header_desc = ""
        if ankuendigung:
            header_desc += f"📣 **{ankuendigung}**\n\n"
        header_desc += f"🗓️ **Woche: {wochentitel}{kw_str}**\n\n"
        if is_vollstaendig:
            header_desc += f"✅ Plan vollständig – {tage_mit_inhalt}/{total_tage} Tage"
        else:
            header_desc += f"⏳ Plan noch unvollständig – {tage_mit_inhalt}/{total_tage} Tage geplant"
        
        embeds.append({
            "title": title_text,
            "description": header_desc,
            "color": 0x2ECC71 if is_vollstaendig else 0xF39C12,
            "url": MENSA_URL,
        })
        
        for tag in plan["tage"]:
            tag_desc_parts = []
            
            if tag["geschlossen"]:
                tag_desc_parts.append("🚫 *Mensa geschlossen*")
            elif not tag["gerichte"]:
                tag_desc_parts.append("🕐 *Noch nicht geplant – wird nachgereicht*")
            else:
                for gericht in tag["gerichte"]:
                    emoji = KATEGORIE_EMOJIS.get(gericht["kategorie"], "🍽️")
                    kat_label = gericht["kategorie"].upper() if gericht["kategorie"] else "GERICHT"
                    
                    lines = []
                    lines.append(f"{emoji} **{kat_label}:** {gericht['titel']}")
                    if gericht["komponenten"]:
                        lines.append(f"┗ {gericht['komponenten']}")
                    lines.append(f"💰 Stud: **{gericht['preis_studierende']}** │ Gäste: **{gericht['preis_gaeste']}**")
                    if gericht["inhaltsstoffe"]:
                        lines.append(f"🏷️ _{gericht['inhaltsstoffe']}_")
                    tag_desc_parts.append("\n".join(lines))
            
            datum_kurz = tag["datum"]
            if datum_kurz:
                parts = datum_kurz.split(".")
                if len(parts) >= 2:
                    datum_kurz = f"{parts[0]}.{parts[1]}."
            
            # Farbe basierend auf erstem Gericht
            farbe = 0x95A5A6  # Grau als Standard
            if tag["gerichte"]:
                first_kat = tag["gerichte"][0].get("kategorie", "")
                farbe = KATEGORIE_FARBEN.get(first_kat, 0x95A5A6)
            elif tag["geschlossen"]:
                farbe = 0xE74C3C  # Rot für geschlossen
            
            embeds.append({
                "title": f"📅 {tag['name']} ({datum_kurz})",
                "description": "\n\n".join(tag_desc_parts),
                "color": farbe,
            })
        
        # Footer nur beim letzten Embed
        embeds[-1]["timestamp"] = datetime.now(timezone.utc).isoformat()
        embeds[-1]["footer"] = {
            "text": "Campus Restaurant Culinaria │ Automatisch geprüft"
        }
    
    return {
        "content": content_text,
        "embeds": embeds,
    }


def send_to_discord(message: dict, webhook_url: str) -> bool:
    """Sendet die Nachricht an den Discord Webhook."""
    try:
        # Discord erlaubt max 10 Embeds pro Nachricht
        embeds = message.get("embeds", [])
        
        if len(embeds) <= 10:
            response = requests.post(
                webhook_url,
                json=message,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            log.info(f"✅ Discord-Nachricht gesendet! (Status: {response.status_code})")
            return True
        else:
            # In Batches aufteilen
            first_batch = {
                "content": message.get("content", ""),
                "embeds": embeds[:10],
            }
            response = requests.post(
                webhook_url,
                json=first_batch,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            
            for i in range(10, len(embeds), 10):
                batch = {"embeds": embeds[i:i+10]}
                response = requests.post(
                    webhook_url,
                    json=batch,
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )
                response.raise_for_status()
            
            log.info(f"✅ Discord-Nachricht in {(len(embeds) + 9) // 10} Teilen gesendet!")
            return True
            
    except requests.RequestException as e:
        log.error(f"❌ Fehler beim Senden an Discord: {e}")
        if hasattr(e, 'response') and e.response is not None:
            log.error(f"   Response: {e.response.text[:500]}")
        return False


# ──────────────────────────────────────────────
# Hauptlogik
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Mensa Speiseplan Discord Bot")
    parser.add_argument("--force", action="store_true", help="Erzwingt Discord-Post auch ohne Änderung")
    parser.add_argument("--test", action="store_true", help="Zeigt die Nachricht nur an, sendet nicht")
    parser.add_argument("--check-current", action="store_true", help="Prüft die aktuelle statt nächste Woche")
    args = parser.parse_args()
    
    # Webhook URL aus Umgebungsvariable
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook_url and not args.test:
        log.error("❌ DISCORD_WEBHOOK_URL nicht gesetzt!")
        log.info("💡 Setze die Variable: export DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...'")
        log.info("💡 Oder nutze --test um die Ausgabe nur anzuzeigen.")
        sys.exit(1)
    
    # Speiseplan der nächsten Woche laden
    url = AKTUELLE_WOCHE_URL if args.check_current else NAECHSTE_WOCHE_URL
    log.info(f"🔍 Lade Speiseplan von: {url}")
    
    html = fetch_html(url)
    if not html:
        log.error("❌ Konnte die Mensa-Seite nicht laden.")
        sys.exit(1)
    
    # Prüfe ob der Inhalt leer ist oder nur Platzhalter enthält
    html_stripped = html.strip()
    if not html_stripped or len(html_stripped) < 50:
        log.info("ℹ️ Speiseplan für nächste Woche ist noch nicht online.")
        sys.exit(0)
    
    # Speiseplan parsen
    plan = parse_speiseplan(html)
    if not plan:
        log.info("ℹ️ Kein gültiger Speiseplan gefunden – vermutlich noch nicht veröffentlicht.")
        sys.exit(0)
    
    log.info(f"📋 Speiseplan gefunden: {plan['wochentitel']} ({len(plan['tage'])} Tage)")
    for tag in plan["tage"]:
        if tag["geschlossen"]:
            log.info(f"   {tag['name']}: 🚫 geschlossen")
        else:
            gerichte_namen = [g["titel"] for g in tag["gerichte"]]
            log.info(f"   {tag['name']}: {', '.join(gerichte_namen)}")
    
    # Hash berechnen und vergleichen
    current_hash = compute_hash(plan)
    last_hash = load_last_hash()
    
    if current_hash == last_hash and not args.force:
        log.info("✅ Kein neuer Speiseplan – keine Änderung seit dem letzten Check.")
        sys.exit(0)
    
    # Ist das ein Update für die gleiche Woche oder ein komplett neuer Plan?
    last_week = load_last_week()
    is_update = (last_week == plan["wochentitel"] and last_hash is not None)
    
    if current_hash != last_hash:
        if is_update:
            log.info("🔄 Speiseplan wurde aktualisiert (gleiche Woche, neuer Inhalt)!")
        else:
            log.info("🆕 Neuer Speiseplan erkannt!")
    elif args.force:
        log.info("⚡ Erzwungener Post (--force)")
    
    # Ankündigungen und Angebote von der Hauptseite holen
    extras = fetch_extras()
    if extras["ankuendigung"]:
        log.info(f"📣 Ankündigung: {extras['ankuendigung']}")
    if extras["angebote"]:
        log.info(f"🏷️ {len(extras['angebote'])} Angebot(e) der Woche gefunden:")
        for a in extras["angebote"]:
            log.info(f"   🔸 {a['titel']}: {a.get('beschreibung', '')} – {a.get('preis', '')}")
    
    # Discord-Nachricht bauen
    message = build_discord_message(plan, extras, is_update=is_update)
    
    if args.test:
        log.info("🧪 TEST-MODUS – Nachricht wird nicht gesendet:")
        print("\n" + "=" * 60)
        print(json.dumps(message, indent=2, ensure_ascii=False))
        print("=" * 60)
        
        # Auch den formatierten Text anzeigen
        print("\n📨 So sieht die Nachricht in Discord ungefähr aus:\n")
        print(message.get("content", ""))
        for embed in message.get("embeds", []):
            if "title" in embed:
                print(f"\n{'─' * 40}")
                print(f"  {embed['title']}")
            if "description" in embed:
                print(embed["description"])
        print()
    else:
        # An Discord senden
        success = send_to_discord(message, webhook_url)
        if not success:
            sys.exit(1)
    
    # Hash speichern (auch im Test-Modus nicht, damit man wiederholt testen kann)
    if not args.test:
        save_state(current_hash, plan["wochentitel"])
        log.info(f"💾 State gespeichert: {current_hash[:16]}... (Woche: {plan['wochentitel']})")
    else:
        log.info(f"🧪 Test-Modus: State nicht gespeichert (Hash: {current_hash[:16]}...)")
    
    log.info("🎉 Fertig!")


if __name__ == "__main__":
    main()
