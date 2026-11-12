#!/usr/bin/env python3
"""
Veille DJ contests Schranz / Hard Techno — France, priorité Paris.

Ce que fait le script, à chaque lancement :
  1. Lance une série de recherches web (DuckDuckGo, sans clé ; Brave Search en option)
     ciblées sur Shotgun, Instagram, Facebook, Resident Advisor, etc.
  2. Lit tes flux RSS Google Alerts (optionnel, mais très efficace).
  3. Lit les recherches Reddit publiques.
  4. Note chaque résultat (contest ? genre ? lieu ?) et garde les plus pertinents.
  5. Ne te montre que les NOUVEAUX résultats (mémoire dans une base SQLite).
  6. Écrit un rapport HTML et peut t'envoyer une notif Telegram.

Installation :
    pip install ddgs feedparser requests
Lancement local :
    python veille_dj_contest.py
Version en ligne : voir README.md (GitHub Actions + GitHub Pages).
"""

import html
import json
import os
import re
import sqlite3
import time
from datetime import datetime

import requests

try:
    import feedparser
except ImportError:
    feedparser = None

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None

# ============================================================
# CONFIGURATION — adapte ici
# ============================================================

# Clé Brave Search API (facultatif, meilleurs résultats) : https://brave.com/search/api/
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")

# Notifs Telegram (facultatif) : crée un bot via @BotFather, récupère ton chat_id
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Flux RSS Google Alerts (facultatif). Sur google.com/alerts, crée des alertes
# ("dj contest schranz", "dj contest hard techno paris", "concours dj hard techno"...)
# avec "Envoyer à : Flux RSS", puis colle les URLs ici.
GOOGLE_ALERTS_RSS = [
    # "https://www.google.com/alerts/feeds/XXXXXXXX/YYYYYYYY",
]

# Période de recherche : "d" = jour, "w" = semaine, "m" = mois
PERIODE = "m"

# Score minimum pour qu'un résultat apparaisse dans le rapport
SCORE_MIN = 5

DB_PATH = "data/veille_contests.db"
RAPPORT_HTML = "docs/index.html"

# Requêtes de recherche. Les "site:" permettent de fouiller les réseaux sociaux
# indexés par les moteurs, sans se connecter ni scraper Instagram/Facebook.
REQUETES = [
    '"dj contest" schranz',
    '"dj contest" schranz France',
    '"dj contest" "hard techno" Paris',
    '"concours dj" "hard techno"',
    '"tremplin" dj "hard techno" Paris',
    '"open deck" "hard techno" Paris',
    '"call for djs" "hard techno" France',
    '"appel à candidatures" dj techno Paris',
    'site:shotgun.live "dj contest" hard techno',
    'site:shotgun.live "dj contest" schranz',
    'site:shotgun.live "contest" "hard techno" Paris',
    'site:instagram.com "dj contest" schranz',
    'site:instagram.com "dj contest" "hard techno" paris',
    'site:facebook.com "dj contest" "hard techno" Paris',
    'site:facebook.com "dj contest" schranz',
    'site:ra.co "dj contest" Paris',
    'site:linktr.ee "dj contest" hard techno',
    'Dream Nation "dj contest" hard',
    '"dj contest" "hardtechno" France',
]

REQUETES_REDDIT = ["dj contest schranz", "dj contest hard techno paris"]

# ============================================================
# NOTATION (mots-clés et poids)
# ============================================================

MOTS_CONTEST = {
    "dj contest": 4, "dj-contest": 4, "djcontest": 4, "concours dj": 4,
    "concours de dj": 4, "tremplin": 3, "open deck": 3, "open decks": 3,
    "call for dj": 3, "call for djs": 3, "appel à candidature": 3,
    "appel a candidature": 3, "envoie ton mix": 3, "envoyez vos mix": 3,
    "warm-up contest": 3, "contest": 2, "battle dj": 2, "sélection dj": 2,
}

MOTS_GENRE = {
    "schranz": 5, "hardgroove": 2, "hard groove": 2, "hard techno": 3,
    "hardtechno": 3, "hard-techno": 3, "industrial techno": 2,
    "techno industrielle": 2, "hard music": 2, "hard bounce": 1,
    "techno": 1,
}

MOTS_LIEU = {
    "paris": 3, "île-de-france": 3, "ile-de-france": 3, "idf": 2,
    "saint-denis": 2, "montreuil": 2, "pantin": 2, "ivry": 2, "aubervilliers": 2,
    "france": 1, "lyon": 1, "marseille": 1, "lille": 1, "bordeaux": 1,
    "toulouse": 1, "nantes": 1, "montpellier": 1, "rennes": 1, "strasbourg": 1,
}

# Signaux négatifs (scratch, hip-hop, résultats annoncés, etc.)
MOTS_NEGATIFS = {
    "dmc": -3, "scratch": -2, "turntablism": -2, "hip-hop": -2, "hip hop": -2,
    "winners": -2, "gagnants": -1, "mariage": -3, "wedding": -3,
}

SITES_BONUS = {"shotgun.live": 2, "instagram.com": 1, "facebook.com": 1, "ra.co": 1}


def noter(titre: str, texte: str, url: str) -> tuple[int, list[str]]:
    """Retourne un score et la liste des mots-clés trouvés."""
    contenu = f"{titre} {texte} {url}".lower()
    trouves, score = [], 0
    a_contest = a_genre = False

    for groupe, drapeau in ((MOTS_CONTEST, "contest"), (MOTS_GENRE, "genre"),
                            (MOTS_LIEU, None), (MOTS_NEGATIFS, None)):
        meilleur = 0
        for mot, poids in groupe.items():
            if re.search(r"(?<!\w)" + re.escape(mot) + r"(?!\w)", contenu):
                trouves.append(mot)
                meilleur = max(meilleur, poids) if poids > 0 else min(meilleur, poids)
        score += meilleur
        if drapeau == "contest" and meilleur > 0:
            a_contest = True
        if drapeau == "genre" and meilleur > 0:
            a_genre = True

    for site, bonus in SITES_BONUS.items():
        if site in url:
            score += bonus

    # Un résultat sans notion de contest OU sans genre n'est pas intéressant
    if not (a_contest and a_genre):
        score = min(score, SCORE_MIN - 1)
    return score, sorted(set(trouves))


# ============================================================
# SOURCES
# ============================================================

def recherche_ddg(requete: str) -> list[dict]:
    if DDGS is None:
        return []
    try:
        res = DDGS().text(requete, region="fr-fr", timelimit=PERIODE, max_results=20)
        return [{"titre": r.get("title", ""), "texte": r.get("body", ""),
                 "url": r.get("href", ""), "source": "DuckDuckGo"} for r in res]
    except Exception as e:
        print(f"  [DDG] erreur sur « {requete} » : {e}")
        return []


def recherche_brave(requete: str) -> list[dict]:
    if not BRAVE_API_KEY:
        return []
    fraicheur = {"d": "pd", "w": "pw", "m": "pm"}.get(PERIODE, "pm")
    try:
        r = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": BRAVE_API_KEY, "Accept": "application/json"},
            params={"q": requete, "country": "FR", "search_lang": "fr",
                    "freshness": fraicheur, "count": 20},
            timeout=20,
        )
        r.raise_for_status()
        res = r.json().get("web", {}).get("results", [])
        return [{"titre": x.get("title", ""), "texte": x.get("description", ""),
                 "url": x.get("url", ""), "source": "Brave"} for x in res]
    except Exception as e:
        print(f"  [Brave] erreur sur « {requete} » : {e}")
        return []


def lire_google_alerts() -> list[dict]:
    if feedparser is None:
        return []
    sortie = []
    for flux in GOOGLE_ALERTS_RSS:
        try:
            for e in feedparser.parse(flux).entries:
                lien = e.get("link", "")
                m = re.search(r"[?&]url=([^&]+)", lien)  # Google enveloppe les liens
                if m:
                    lien = requests.utils.unquote(m.group(1))
                sortie.append({"titre": re.sub("<[^>]+>", "", e.get("title", "")),
                               "texte": re.sub("<[^>]+>", "", e.get("summary", "")),
                               "url": lien, "source": "Google Alerts"})
        except Exception as e:
            print(f"  [Alerts] erreur : {e}")
    return sortie


def recherche_reddit(requete: str) -> list[dict]:
    t = {"d": "day", "w": "week", "m": "month"}.get(PERIODE, "month")
    try:
        r = requests.get("https://www.reddit.com/search.json",
                         params={"q": requete, "sort": "new", "t": t, "limit": 25},
                         headers={"User-Agent": "veille-dj-contest/1.0"}, timeout=20)
        r.raise_for_status()
        posts = r.json().get("data", {}).get("children", [])
        return [{"titre": p["data"].get("title", ""),
                 "texte": p["data"].get("selftext", "")[:500],
                 "url": "https://www.reddit.com" + p["data"].get("permalink", ""),
                 "source": "Reddit"} for p in posts]
    except Exception as e:
        print(f"  [Reddit] erreur : {e}")
        return []


# ============================================================
# MÉMOIRE, RAPPORT, NOTIFS
# ============================================================

def normaliser_url(url: str) -> str:
    url = re.sub(r"[?#].*$", "", url.strip())
    return url.rstrip("/").lower().replace("://www.", "://").replace("://m.", "://")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS vus (
        url TEXT PRIMARY KEY, titre TEXT, score INTEGER,
        mots TEXT, source TEXT, vu_le TEXT, lien TEXT)""")
    return con


def generer_rapport(con):
    lignes = con.execute(
        "SELECT titre, COALESCE(lien, url), score, mots, source, vu_le FROM vus "
        "WHERE score >= ? ORDER BY vu_le DESC, score DESC LIMIT 300", (SCORE_MIN,)
    ).fetchall()
    data = [{"t": t or u, "u": u if u.startswith("http") else "https://" + u, "s": s,
             "k": json.loads(m), "src": src, "d": v[:10]} for t, u, s, m, src, v in lignes]
    with open("modele_page.html", encoding="utf-8") as f:
        page = f.read()
    page = page.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    page = page.replace("__MAJ__", datetime.now().strftime("%d/%m/%Y à %H:%M"))
    os.makedirs(os.path.dirname(RAPPORT_HTML), exist_ok=True)
    with open(RAPPORT_HTML, "w", encoding="utf-8") as f:
        f.write(page)


def notifier_telegram(nouveaux: list[dict]):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID and nouveaux):
        return
    texte = "🔊 Nouveaux DJ contests repérés :\n\n" + "\n\n".join(
        f"• {n['titre'][:120]}\n  (score {n['score']}) {n['url']}" for n in nouveaux[:15])
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                      data={"chat_id": TELEGRAM_CHAT_ID, "text": texte,
                            "disable_web_page_preview": True}, timeout=20)
    except Exception as e:
        print(f"  [Telegram] erreur : {e}")


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():
    if DDGS is None and not BRAVE_API_KEY:
        print("Installe le moteur de recherche : pip install ddgs (ou configure BRAVE_API_KEY)")
    con = init_db()
    bruts = []

    print("Recherche web…")
    for q in REQUETES:
        bruts += recherche_ddg(q)
        bruts += recherche_brave(q)
        time.sleep(1.5)  # rester poli avec les moteurs

    print("Google Alerts…")
    bruts += lire_google_alerts()

    print("Reddit…")
    for q in REQUETES_REDDIT:
        bruts += recherche_reddit(q)
        time.sleep(1)

    nouveaux, deja = [], set()
    for r in bruts:
        if not r["url"]:
            continue
        cle = normaliser_url(r["url"])
        if cle in deja:
            continue
        deja.add(cle)
        if con.execute("SELECT 1 FROM vus WHERE url = ?", (cle,)).fetchone():
            continue
        score, mots = noter(r["titre"], r["texte"], r["url"])
        con.execute("INSERT INTO vus VALUES (?,?,?,?,?,?,?)",
                    (cle, r["titre"], score, json.dumps(mots), r["source"],
                     datetime.now().isoformat(), r["url"]))
        if score >= SCORE_MIN:
            nouveaux.append({**r, "score": score, "mots": mots})
    con.commit()

    nouveaux.sort(key=lambda x: -x["score"])
    print(f"\n{len(bruts)} résultats analysés, {len(nouveaux)} nouveaux pertinents.\n")
    for n in nouveaux:
        print(f"[{n['score']:>2}] {n['titre'][:90]}\n     {n['url']}\n     {', '.join(n['mots'])}\n")

    generer_rapport(con)
    notifier_telegram(nouveaux)
    print(f"Rapport : {os.path.abspath(RAPPORT_HTML)}")


if __name__ == "__main__":
    main()
