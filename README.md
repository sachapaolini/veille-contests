# Veille DJ contests Schranz / Hard Techno

Le script cherche chaque matin les nouveaux DJ contests (France, priorité Paris)
et publie une page web consultable sur iPhone.

## Mise en ligne (une seule fois, ~10 minutes)

1. Crée un compte gratuit sur https://github.com
2. Crée un nouveau dépôt (bouton « New »), par exemple `veille-contests`.
   Choisis « Public » (GitHub Pages est gratuit pour les dépôts publics).
3. Clique « uploading an existing file » et glisse TOUT le contenu de ce dossier,
   y compris le dossier caché `.github` (sur Mac : Cmd+Maj+. pour l'afficher).
4. Dans le dépôt : Settings → Pages → Source « Deploy from a branch »,
   branche `main`, dossier `/docs` → Save.
5. Onglet Actions → « Veille DJ contests » → « Run workflow » pour un premier lancement.
6. Ta page sera sur : https://TON-PSEUDO.github.io/veille-contests/

## Sur l'iPhone

Ouvre l'adresse dans Safari → bouton Partager → « Sur l'écran d'accueil ».
Elle s'ouvre ensuite comme une app.

## Options (Settings → Secrets and variables → Actions → New repository secret)

- `BRAVE_API_KEY` : fortement conseillé, DuckDuckGo bloque parfois les serveurs GitHub.
  Clé sur https://brave.com/search/api/
- `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID` : pour recevoir une notif à chaque nouveau contest.

Les flux Google Alerts se collent directement dans `veille_dj_contest.py` (liste `GOOGLE_ALERTS_RSS`).
