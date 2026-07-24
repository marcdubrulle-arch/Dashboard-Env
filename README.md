# XRAY Rapport

Application Python qui génère un rapport quotidien XRAY (Jira) pour les environnements `XITG` et `XMQ1`, puis met à jour une page Confluence.

## Contenu du projet

- `xray_rapport_du_jour.py` : génération du rapport HTML XRAY + publication Confluence.
- `generate_accueil.py` : génération d'une page d'accueil consolidée (`accueil.html`).
- `run_rapport_daily.ps1` : exécution quotidienne locale (Windows Task Scheduler).
- `register_task.ps1` : création de la tâche planifiée Windows.
- `.github/workflows/daily-xray-report.yml` : exécution quotidienne sur GitHub Actions.

## Prérequis

- Python 3.12+
- Accès Jira/XRAY + Confluence
- Variables d'environnement configurées

## Configuration

1. Copier `.env.example` vers `.env`.
2. Renseigner les variables :
   - `JIRA_TOKEN`
   - `CONFLUENCE_TOKEN`
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

Le workflow `.github/workflows/daily-xray-report.yml` exécute automatiquement le rapport tous les jours ouvrés.

Configurer les **Repository Secrets** sur GitHub :

- `JIRA_BASE_URL`
- `JIRA_TOKEN`
- `CONFLUENCE_BASE_URL`
- `CONFLUENCE_SPACE`
- `CONFLUENCE_TOKEN`
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
