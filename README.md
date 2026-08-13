# XRAY Rapport

Application Python qui génère un rapport quotidien XRAY (Jira) pour les environnements `XITG` et `XMQ1`, puis met à jour une page Confluence.

## Contenu du projet

- `xray_rapport_du_jour.py` : génération du rapport HTML XRAY + publication Confluence.
- `generate_accueil.py` : génération d'une page d'accueil consolidée (`accueil.html`).
- `run_rapport_daily.ps1` : exécution quotidienne locale (Windows Task Scheduler).
- `register_task.ps1` : création de la tâche planifiée Windows.
- `.github/workflows/daily-xray-report.yml` : exécution quotidienne sur GitHub Actions.

### Structure interne (refactor)

La logique principale du rapport XRAY est désormais découpée dans [xray_report/](C:/Users/WHDD0146/XRAY%20Rapport/xray_report) :

- [config.py](C:/Users/WHDD0146/XRAY%20Rapport/xray_report/config.py) : variables d'environnement et constantes.
- [apis.py](C:/Users/WHDD0146/XRAY%20Rapport/xray_report/apis.py) : appels Jira/XRAY et Dynatrace, gestion proxy/curl.
- [report_html.py](C:/Users/WHDD0146/XRAY%20Rapport/xray_report/report_html.py) : calcul des stats + rendu HTML.
- [history.py](C:/Users/WHDD0146/XRAY%20Rapport/xray_report/history.py) : mise à jour de `stats_history.json`.
- [confluence_publish.py](C:/Users/WHDD0146/XRAY%20Rapport/xray_report/confluence_publish.py) : publication Confluence.
- [cli.py](C:/Users/WHDD0146/XRAY%20Rapport/xray_report/cli.py) : orchestration de bout en bout.

Le script [xray_rapport_du_jour.py](C:/Users/WHDD0146/XRAY%20Rapport/xray_rapport_du_jour.py) reste l’entrée publique (workflow/script local), mais délègue maintenant à ces modules.

### Reprendre rapidement le travail

1. Commencer par [xray_report/cli.py](C:/Users/WHDD0146/XRAY%20Rapport/xray_report/cli.py) pour comprendre le flux global.
2. Modifier ensuite le module concerné :
   - data/API : [apis.py](C:/Users/WHDD0146/XRAY%20Rapport/xray_report/apis.py)
   - rendu : [report_html.py](C:/Users/WHDD0146/XRAY%20Rapport/xray_report/report_html.py)
   - publication Confluence : [confluence_publish.py](C:/Users/WHDD0146/XRAY%20Rapport/xray_report/confluence_publish.py)
3. Valider localement avec :
   - `python xray_rapport_du_jour.py --env XITG --output rapport_XITG_test.html`

## Prérequis

- Python 3.12+
- Accès Jira/XRAY + Confluence
- Variables d'environnement configurées

## Configuration

1. Copier `.env.example` vers `.env`.
2. Renseigner les variables :
   - `JIRA_TOKEN`
   - `CONFLUENCE_TOKEN`
   - `DYNATRACE_BASE_URL`
   - `DYNATRACE_TOKEN`
   - `DYNATRACE_TAG_XITG` et `DYNATRACE_TAG_XMQ1` (ou `DYNATRACE_TAG_DEFAULT`)
   - (optionnel) `PROXY_USER`, `PROXY_PASS`, `PROXY_HOST`

> `.env` est ignoré par Git (`.gitignore`) pour éviter de publier des secrets.

## Installation locale

Créer un environnement virtuel, puis installer les dépendances :

- `pip install -r requirements.txt`

## Exécution locale

- Générer un rapport :
  - `python xray_rapport_du_jour.py --env XITG --output rapport_XITG_YYYY-MM-DD.html`
- Générer la page d'accueil :
  - `python generate_accueil.py --output accueil.html`

## Planification quotidienne

### Option A — Windows Task Scheduler (poste local)

1. Exécuter `register_task.ps1` (une seule fois).
2. La tâche `XRAY_Rapport_Journalier` lancera `run_rapport_daily.ps1` chaque matin (jours ouvrés).

### Option B — GitHub Actions (recommandé pour publication)

Le workflow `.github/workflows/daily-xray-report.yml` exécute automatiquement le rapport tous les jours.

Le workflow restaure aussi désormais le dernier `stats_history.json` publié avant de générer les nouveaux rapports, afin de conserver l'historique entre deux exécutions GitHub Actions.

### Rattrapage d'un trou d'historique

Le workflow GitHub peut être lancé manuellement avec `start_date` et `end_date` pour régénérer une plage complète de dates manquantes, y compris le week-end. Chaque rapport regénéré met à jour `stats_history.json`, puis la page d'accueil est reconstruite avec l'historique cumulé.

Configurer les **Repository Secrets** sur GitHub :

- `JIRA_BASE_URL`
- `JIRA_TOKEN`
- `CONFLUENCE_BASE_URL`
- `CONFLUENCE_SPACE`
- `CONFLUENCE_TOKEN`
- `DYNATRACE_BASE_URL`
- `DYNATRACE_TOKEN`
- `DYNATRACE_TAG_XITG` (optionnel si `DYNATRACE_TAG_DEFAULT` utilisé)
- `DYNATRACE_TAG_XMQ1` (optionnel si `DYNATRACE_TAG_DEFAULT` utilisé)
- `DYNATRACE_TAG_DEFAULT` (optionnel)
- `PROXY_USER` (optionnel)
- `PROXY_PASS` (optionnel)
- `PROXY_HOST` (optionnel)

## Publication sur GitHub

1. Initialiser un dépôt Git dans ce dossier (éviter d'utiliser le dépôt parent utilisateur).
2. Commit initial.
3. Ajouter le remote GitHub.
4. Push sur `main`.

## Notes

- Les fichiers `rapport_*.html` et `accueil.html` sont générés automatiquement et ignorés par Git.
- Les logs (`*.log`) sont ignorés par Git.
