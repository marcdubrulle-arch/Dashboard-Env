"""
xray_rapport_du_jour.py
-----------------------
Récupère les Test Executions XRAY du jour sur les projets OAGRCLI et OAGDIGI,
environnement XITG, et génère un rapport HTML visuel partageable.

Prérequis :
    pip install requests python-dateutil rich

Usage :
    py xray_rapport_du_jour.py
    py xray_rapport_du_jour.py --date 2026-05-27
    py xray_rapport_du_jour.py --projects OAGRCLI OAGDIGI
    py xray_rapport_du_jour.py --testplan OAGRCLI-123
    py xray_rapport_du_jour.py --output mon_rapport.html
"""

import argparse
import os
import sys
import json
from datetime import date, datetime

import requests
import subprocess
import json as _json
from rich.console import Console
from rich import box
from rich.table import Table

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────
JIRA_BASE_URL    = os.getenv("JIRA_BASE_URL", "https://portail.agir.orange.com")
JIRA_TOKEN       = os.getenv("JIRA_TOKEN",    "VOTRE_TOKEN_ICI")
ENVIRONMENT      = os.getenv("XRAY_ENV",      "XITG")
DEFAULT_PROJECTS = ["OAGRCLI", "OAGDIGI"]

# ─────────────────────────────────────────────
#  CONFIGURATION CONFLUENCE
# ─────────────────────────────────────────────
CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL", "https://espace.agir.orange.com")
CONFLUENCE_PAGE_ID  = os.getenv("CONFLUENCE_PAGE_ID",  "3168392364")
CONFLUENCE_SPACE    = os.getenv("CONFLUENCE_SPACE",     "OAGTMA")
CONFLUENCE_TOKEN    = os.getenv("CONFLUENCE_TOKEN",     "")  # Token séparé pour Confluence

# Proxy Orange SI — identifiants réseau requis (407)
PROXY_USER       = os.getenv("PROXY_USER", "")   # ex: whdd0146
PROXY_PASS       = os.getenv("PROXY_PASS", "")   # mot de passe réseau Orange
PROXY_HOST       = os.getenv("PROXY_HOST", "proxy.si.francetelecom.fr:8080")
PROXY            = (
    f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}"
    if PROXY_USER else os.getenv("JIRA_PROXY", "")
)

# ─────────────────────────────────────────────
#  SESSION
# ─────────────────────────────────────────────
def curl_get(url: str, params: dict = None) -> dict:
    """
    Effectue un GET via curl avec proxy Negotiate (comme le navigateur).
    Utilise urllib pour encoder proprement l'URL complète.
    """
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode(params)}"

    cmd = [
        "curl", "-s", "-k",
        "--proxy", f"http://{PROXY_HOST}",
        "--proxy-negotiate", "-U", ":",
        "-H", f"Authorization: Bearer {JIRA_TOKEN}",
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json",
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not result.stdout.strip():
        raise RuntimeError(f"curl vide (code {result.returncode}): {result.stderr[:200]}")
    try:
        return _json.loads(result.stdout)
    except _json.JSONDecodeError:
        raise RuntimeError(f"Réponse non-JSON: {result.stdout[:300]}")

def get_session():
    """Conservé pour compatibilité — non utilisé avec curl."""
    return None

# ─────────────────────────────────────────────
#  TEST EXECUTIONS DU JOUR
# ─────────────────────────────────────────────
def fetch_test_executions(session, project_key: str, target_date: date) -> list:
    """
    Récupère les Test Executions créées à la date cible (heure locale +0200)
    pour l'environnement XRAY configuré (variable ENVIRONMENT).
    """
    jql = (
        f'project = {project_key} AND issuetype = "Test Execution"'
        f' AND "Test Environments" = "{ENVIRONMENT}"'
        f' AND created >= "{target_date.isoformat()}"'
        f' AND created <= "{target_date.isoformat()} 23:59"'
        f' ORDER BY created DESC'
    )
    data = curl_get(f"{JIRA_BASE_URL}/rest/api/2/search", params={
        "jql": jql, "maxResults": 100,
        "fields": "summary,status,created,environment,assignee,labels",
    })
    return data.get("issues", [])

# ─────────────────────────────────────────────
#  TEST PLAN SPÉCIFIQUE — dernière exécution
# ─────────────────────────────────────────────
def fetch_test_plan(session, plan_key: str) -> dict:
    """Récupère les infos du Test Plan."""
    return curl_get(f"{JIRA_BASE_URL}/rest/api/2/issue/{plan_key}",
                    params={"fields": "summary,status,created,assignee"})

def fetch_test_plan_executions(session, plan_key: str) -> list:
    """Récupère toutes les Test Executions liées au Test Plan."""
    try:
        return curl_get(
            f"{JIRA_BASE_URL}/rest/raven/1.0/api/testplan/{plan_key}/testexecution",
            params={"limit": 100}
        )
    except Exception:
        return []

def fetch_all_test_plans(session, project_key: str) -> list:
    """Récupère tous les Test Plans d'un projet via JQL."""
    jql = f'project = {project_key} AND issuetype = "Test Plan" ORDER BY created DESC'
    data = curl_get(f"{JIRA_BASE_URL}/rest/api/2/search", params={
        "jql": jql, "maxResults": 200,
        "fields": "summary,status,created,assignee",
    })
    return data.get("issues", [])

def fetch_last_execution_with_tests(session, plan_key: str, console: Console) -> dict | None:
    """
    Retourne la dernière Test Execution du Test Plan qui contient réellement des tests.
    Parcourt les exécutions de la plus récente à la plus ancienne et s'arrête
    dès qu'une exécution non vide est trouvée.
    """
    executions = fetch_test_plan_executions(session, plan_key)
    if not executions:
        return None

    executions_sorted = sorted(executions, key=lambda x: x.get("key", ""), reverse=True)

    for exec_info in executions_sorted:
        exec_key = exec_info.get("key")
        runs = fetch_test_runs(session, exec_key)
        if runs:
            console.print(f"  [dim]{plan_key} → {exec_key} ({len(runs)} tests)[/dim]")
            exec_info["_runs"]     = runs
            exec_info["_plan_key"] = plan_key
            return exec_info
        else:
            console.print(f"  [dim]{exec_key} ignorée (0 test)[/dim]")

    console.print(f"  [yellow]{plan_key} : aucune exécution avec des tests trouvée.[/yellow]")
    return None

# ─────────────────────────────────────────────
#  RUNS
# ─────────────────────────────────────────────
def fetch_test_runs(session, execution_key: str) -> list:
    try:
        return curl_get(
            f"{JIRA_BASE_URL}/rest/raven/1.0/api/testexec/{execution_key}/test",
            params={"detailed": "true"}
        )
    except Exception:
        return []

# ─────────────────────────────────────────────
#  STATISTIQUES
# ─────────────────────────────────────────────
def compute_stats(runs: list) -> dict:
    stats = {"PASS": 0, "FAIL": 0, "EXECUTING": 0, "TODO": 0,
             "ABORTED": 0, "BLOCKED": 0, "OTHER": 0}
    for run in runs:
        raw    = run.get("status") or "OTHER"
        status = (raw if isinstance(raw, str) else raw.get("name", "OTHER")).upper()
        stats[status] = stats.get(status, 0) + 1
    return stats

def success_rate(stats: dict) -> int:
    total = sum(stats.values())
    if total == 0:
        return 0
    return round(stats.get("PASS", 0) / total * 100)

# ─────────────────────────────────────────────
#  GÉNÉRATION HTML
# ─────────────────────────────────────────────
def build_html(all_projects: list, plan_sections: list,
               target_date: date, environment: str) -> str:

    def stat_bar(stats):
        total = sum(stats.values())
        if total == 0:
            return '<div class="bar"><span class="seg todo" style="width:100%">N/A</span></div>'
        segs = ""
        colors = {"PASS":"pass","FAIL":"fail","EXECUTING":"exec","TODO":"todo",
                  "ABORTED":"aborted","BLOCKED":"blocked","OTHER":"other"}
        for k, cls in colors.items():
            v = stats.get(k, 0)
            if v:
                pct = round(v / total * 100)
                segs += f'<span class="seg {cls}" style="width:{pct}%" title="{k}: {v}"></span>'
        return f'<div class="bar">{segs}</div>'

    def badge(label, cls):
        return f'<span class="badge {cls}">{label}</span>'

    def rate_badge(rate):
        cls = "pass" if rate >= 80 else ("warn" if rate >= 50 else "fail")
        return f'<span class="rate-badge {cls}">{rate}%</span>'

    def rows_for_executions(executions):
        html = ""
        for ex in executions:
            key     = ex.get("key", "—")
            summary = (ex.get("fields") or ex).get("summary", ex.get("summary", "—"))
            runs    = ex.get("_runs", [])
            stats   = compute_stats(runs)
            total   = sum(stats.values())
            rate    = success_rate(stats)
            link    = f"{JIRA_BASE_URL}/browse/{key}"
            html += f"""
            <tr>
              <td><a href="{link}" target="_blank" class="key-link">{key}</a></td>
              <td class="summary">{summary[:60]}</td>
              <td class="center">{total}</td>
              <td class="center pass-txt">{stats.get('PASS',0)}</td>
              <td class="center fail-txt">{stats.get('FAIL',0)}</td>
              <td class="center exec-txt">{stats.get('EXECUTING',0)}</td>
              <td class="center todo-txt">{stats.get('TODO',0)}</td>
              <td class="center aborted-txt">{stats.get('ABORTED',0)}</td>
              <td>{stat_bar(stats)}</td>
              <td class="center">{rate_badge(rate)}</td>
            </tr>"""
        return html

    # Blocs par projet
    project_blocks = ""
    grand = {"PASS":0,"FAIL":0,"EXECUTING":0,"TODO":0,"ABORTED":0,"total":0}
    for proj in all_projects:
        pkey  = proj["key"]
        execs = proj["executions"]
        pt    = {"PASS":0,"FAIL":0,"EXECUTING":0,"TODO":0,"ABORTED":0}
        for ex in execs:
            s = compute_stats(ex.get("_runs", []))
            for k in pt:
                pt[k] += s.get(k, 0)
        ptotal = sum(pt.values())
        prate  = round(pt["PASS"] / ptotal * 100) if ptotal > 0 else 0
        for k in pt:
            grand[k] += pt[k]
        grand["total"] += ptotal

        project_blocks += f"""
        <div class="project-block">
          <div class="project-header">
            <span class="project-title">{pkey}</span>
            <span class="project-meta">{len(execs)} campagne(s) · {ptotal} tests · {rate_badge(prate)}</span>
          </div>
          <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>TE Key</th><th>Résumé</th><th>Total</th>
                <th class="pass-txt">PASS</th><th class="fail-txt">FAIL</th>
                <th class="exec-txt">EXEC</th><th class="todo-txt">TODO</th>
                <th class="aborted-txt">ABORT</th>
                <th style="min-width:140px">Répartition</th><th>Taux</th>
              </tr>
            </thead>
            <tbody>
              {rows_for_executions(execs) if execs else '<tr><td colspan="10" class="empty">Aucune exécution trouvée</td></tr>'}
            </tbody>
          </table>
          </div>
        </div>"""

    # Blocs Test Plans (liste)
    all_plan_blocks_html = ""
    for plan_section in (plan_sections or []):
        pk   = plan_section.get("key", "—")
        summ = plan_section.get("summary", "—")
        ex   = plan_section.get("last_execution")
        plan_block = ""
        if ex:
            runs  = ex.get("_runs", [])
            stats = compute_stats(runs)
            total = sum(stats.values())
            rate  = success_rate(stats)
            run_rows = ""
            for run in runs[:50]:
                rkey    = run.get("key", "—")
                rsumm   = run.get("summary", "—")
                raw     = run.get("status") or "OTHER"
                rstatus = raw if isinstance(raw, str) else raw.get("name", "OTHER")
                cls     = rstatus.lower().replace(" ", "-")
                run_rows += f"""
                <tr>
                  <td><a href="{JIRA_BASE_URL}/browse/{rkey}" target="_blank" class="key-link">{rkey}</a></td>
                  <td class="summary">{rsumm[:55]}</td>
                  <td class="center"><span class="badge {cls}">{rstatus}</span></td>
                </tr>"""

            plan_block = f"""
        <div class="project-block plan-block">
          <div class="project-header">
            <span class="project-title">Test Plan — {pk}</span>
            <span class="project-meta">{summ[:60]}</span>
          </div>
          <div class="plan-summary">
            <div class="plan-exec-key">Dernière exécution : <a href="{JIRA_BASE_URL}/browse/{ex.get('key','')}" target="_blank" class="key-link">{ex.get('key','—')}</a></div>
            <div class="kpi-row">
              <div class="kpi"><span class="kpi-val pass-txt">{stats.get('PASS',0)}</span><span class="kpi-lbl">PASS</span></div>
              <div class="kpi"><span class="kpi-val fail-txt">{stats.get('FAIL',0)}</span><span class="kpi-lbl">FAIL</span></div>
              <div class="kpi"><span class="kpi-val exec-txt">{stats.get('EXECUTING',0)}</span><span class="kpi-lbl">EN COURS</span></div>
              <div class="kpi"><span class="kpi-val todo-txt">{stats.get('TODO',0)}</span><span class="kpi-lbl">TODO</span></div>
              <div class="kpi"><span class="kpi-val">{total}</span><span class="kpi-lbl">TOTAL</span></div>
              <div class="kpi">{rate_badge(rate)}<span class="kpi-lbl">TAUX</span></div>
            </div>
            {stat_bar(stats)}
          </div>
          <div class="table-wrap" style="margin-top:16px">
          <table>
            <thead><tr><th>Test Key</th><th>Résumé</th><th class="center">Statut</th></tr></thead>
            <tbody>{run_rows if run_rows else '<tr><td colspan="3" class="empty">Aucun test</td></tr>'}</tbody>
          </table>
          </div>
        </div>"""
        else:
            plan_block = f"""
        <div class="project-block plan-block">
          <div class="project-header">
            <span class="project-title">Test Plan — {pk}</span>
            <span class="project-meta">{summ[:60]}</span>
          </div>
          <p class="empty" style="padding:16px">Aucune exécution trouvée pour ce Test Plan.</p>
        </div>"""

    grand_rate = round(grand["PASS"] / grand["total"] * 100) if grand["total"] > 0 else 0

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rapport XRAY — {target_date.isoformat()}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
        background:#f4f5f7;color:#172b4d;font-size:14px;}}
  header{{background:#FF7900;padding:20px 32px;color:#fff;display:flex;
          align-items:center;justify-content:space-between;}}
  header h1{{font-size:20px;font-weight:600;letter-spacing:.3px}}
  header .sub{{font-size:13px;opacity:.85;margin-top:3px}}
  .logo{{font-size:26px;font-weight:700;letter-spacing:1px;color:#fff}}
  .main{{padding:24px 32px;max-width:1200px;margin:0 auto}}
  .kpi-strip{{display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap}}
  .kpi-card{{background:#fff;border-radius:8px;padding:14px 20px;
             border:1px solid #e1e4e8;flex:1;min-width:130px;text-align:center}}
  .kpi-card .val{{font-size:28px;font-weight:700;line-height:1.1}}
  .kpi-card .lbl{{font-size:11px;color:#6b778c;text-transform:uppercase;
                  letter-spacing:.6px;margin-top:4px}}
  .pass-txt{{color:#0a7a3e}} .fail-txt{{color:#c9372c}}
  .exec-txt{{color:#974f00}} .todo-txt{{color:#0052cc}} .aborted-txt{{color:#6554c0}}
  .project-block{{background:#fff;border-radius:8px;border:1px solid #e1e4e8;
                  margin-bottom:20px;overflow:hidden}}
  .plan-block{{border-top:3px solid #FF7900}}
  .project-header{{padding:14px 20px;background:#f8f9fa;border-bottom:1px solid #e1e4e8;
                   display:flex;align-items:center;justify-content:space-between}}
  .project-title{{font-size:15px;font-weight:600;color:#172b4d}}
  .project-meta{{font-size:12px;color:#6b778c;display:flex;align-items:center;gap:8px}}
  .table-wrap{{overflow-x:auto}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{padding:9px 12px;text-align:left;background:#f8f9fa;
      border-bottom:2px solid #e1e4e8;color:#6b778c;
      font-size:11px;text-transform:uppercase;letter-spacing:.5px;white-space:nowrap}}
  td{{padding:9px 12px;border-bottom:1px solid #f0f0f0;vertical-align:middle}}
  tr:last-child td{{border-bottom:none}}
  tr:hover td{{background:#f8f9fa}}
  .center{{text-align:center}}
  .key-link{{color:#0052cc;text-decoration:none;font-weight:500}}
  .key-link:hover{{text-decoration:underline}}
  .summary{{color:#42526e;max-width:280px}}
  .empty{{text-align:center;color:#6b778c;padding:20px;font-style:italic}}
  .bar{{display:flex;height:8px;border-radius:4px;overflow:hidden;
        background:#ebecf0;min-width:120px}}
  .seg{{height:100%;transition:width .3s}}
  .seg.pass{{background:#0a7a3e}} .seg.fail{{background:#c9372c}}
  .seg.exec{{background:#f59f00}} .seg.todo{{background:#0052cc}}
  .seg.aborted{{background:#6554c0}} .seg.blocked{{background:#97a0af}}
  .seg.other{{background:#c1c7d0}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:3px;font-size:11px;
          font-weight:600;text-transform:uppercase}}
  .badge.pass,.badge.passed{{background:#e3fcef;color:#0a7a3e}}
  .badge.fail,.badge.failed{{background:#ffebe6;color:#c9372c}}
  .badge.executing{{background:#fff7d6;color:#974f00}}
  .badge.todo{{background:#e9f0fb;color:#0052cc}}
  .badge.aborted{{background:#f0ebff;color:#6554c0}}
  .badge.blocked{{background:#f4f5f7;color:#6b778c}}
  .rate-badge{{display:inline-block;padding:3px 10px;border-radius:12px;
              font-size:12px;font-weight:700}}
  .rate-badge.pass{{background:#e3fcef;color:#0a7a3e}}
  .rate-badge.warn{{background:#fff7d6;color:#974f00}}
  .rate-badge.fail{{background:#ffebe6;color:#c9372c}}
  .plan-summary{{padding:16px 20px}}
  .plan-exec-key{{font-size:13px;color:#6b778c;margin-bottom:12px}}
  .kpi-row{{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:12px}}
  .kpi{{display:flex;flex-direction:column;align-items:center;min-width:60px}}
  .kpi-val{{font-size:24px;font-weight:700;line-height:1}}
  .kpi-lbl{{font-size:10px;color:#6b778c;text-transform:uppercase;
            letter-spacing:.5px;margin-top:4px}}
  .section-title{{font-size:13px;font-weight:600;color:#6b778c;text-transform:uppercase;
                  letter-spacing:.6px;margin:24px 0 10px}}
  footer{{text-align:center;color:#97a0af;font-size:11px;padding:20px 0 32px}}
</style>
</head>
<body>
<header>
  <div>
    <div class="logo">Orange</div>
    <h1>Rapport XRAY — Systèmes d'information</h1>
    <div class="sub">Environnement : {environment} &nbsp;·&nbsp; Date : {target_date.strftime('%d/%m/%Y')} &nbsp;·&nbsp; Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}</div>
  </div>
</header>
<div class="main">
  <div class="kpi-strip">
    <div class="kpi-card"><div class="val">{grand['total']}</div><div class="lbl">Tests total</div></div>
    <div class="kpi-card"><div class="val pass-txt">{grand['PASS']}</div><div class="lbl">Pass</div></div>
    <div class="kpi-card"><div class="val fail-txt">{grand['FAIL']}</div><div class="lbl">Fail</div></div>
    <div class="kpi-card"><div class="val exec-txt">{grand['EXECUTING']}</div><div class="lbl">En cours</div></div>
    <div class="kpi-card"><div class="val todo-txt">{grand['TODO']}</div><div class="lbl">Todo</div></div>
    <div class="kpi-card"><div class="val">{grand_rate}%</div><div class="lbl">Taux réussite</div></div>
  </div>

  <div class="section-title">Exécutions du jour par projet</div>
  {project_blocks}

  {"<div class='section-title'>Dernière exécution par Test Plan</div>" + all_plan_blocks_html if all_plan_blocks_html else ""}
</div>
<footer>Rapport généré automatiquement · Orange SI · XRAY / Jira</footer>
</body>
</html>"""

def publish_to_confluence_child(html_content: str, page_title: str,
                                parent_id: str, console: Console):
    """
    Crée ou met à jour une page Confluence enfant identifiée par son titre.
    - Si la page existe déjà dans l'espace, elle est mise à jour (PUT).
    - Sinon elle est créée sous la page parent (POST).
    """
    from urllib.parse import quote as urlquote
    token = CONFLUENCE_TOKEN or JIRA_TOKEN

    confluence_body = (
        '<ac:structured-macro ac:name="html">'
        '<ac:plain-text-body><![CDATA['
        + html_content +
        ']]></ac:plain-text-body>'
        '</ac:structured-macro>'
    )

    def _curl(method, url, payload=None, max_retries=4):
        import time as _time
        cmd = [
            "curl", "-s", "-k",
            "--proxy", f"http://{PROXY_HOST}",
            "--proxy-negotiate", "-U", ":",
            "-X", method,
            "-H", f"Authorization: Bearer {token}",
            "-H", "Content-Type: application/json",
            "-H", "Accept: application/json",
        ]
        if payload:
            cmd += ["-d", payload]
        cmd.append(url)
        for attempt in range(max_retries):
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            try:
                data = _json.loads(r.stdout)
            except _json.JSONDecodeError:
                raise RuntimeError(f"Réponse non-JSON : {r.stdout[:300]}")
            if isinstance(data, dict) and "Rate limit" in data.get("message", ""):
                wait = 10 * (2 ** attempt)
                console.print(f"[yellow]Rate limit Confluence — attente {wait}s (essai {attempt+1}/{max_retries})…[/yellow]")
                _time.sleep(wait)
                continue
            return data
        raise RuntimeError("Rate limit Confluence : nombre max de tentatives atteint.")

    # Cache local des IDs de pages pour éviter la recherche GET (soumise au rate limit)
    import os as _os, sys as _sys
    _cache_file = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "confluence_page_ids.json")
    try:
        with open(_cache_file, "r", encoding="utf-8") as _f:
            _page_cache = _json.load(_f)
    except Exception:
        _page_cache = {}

    def _save_page_cache(title, pid, ver):
        _page_cache[title] = {"id": pid, "version": ver}
        try:
            with open(_cache_file, "w", encoding="utf-8") as _f:
                _json.dump(_page_cache, _f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _do_put(pid, ver):
        payload = _json.dumps({
            "id":    pid,
            "type":  "page",
            "title": page_title,
            "space": {"key": CONFLUENCE_SPACE},
            "body":  {"storage": {"value": confluence_body, "representation": "storage"}},
            "version": {"number": ver},
        })
        return _curl("PUT", f"{CONFLUENCE_BASE_URL}/rest/api/content/{pid}", payload)

    published = False
    cached = _page_cache.get(page_title)

    if cached:
        # Chemin rapide : PUT direct (1 seul appel API, pas de recherche)
        page_id = cached["id"]
        next_ver = cached["version"] + 1
        console.print(f"[dim]Mise à jour directe (cache) page {page_id} v{next_ver}…[/dim]")
        try:
            resp = _do_put(page_id, next_ver)
            if resp.get("id"):
                link = f"{CONFLUENCE_BASE_URL}/spaces/{CONFLUENCE_SPACE}/pages/{page_id}"
                console.print(f"[bold green]Page mise à jour : {link}[/bold green]")
                print(f"[CONFLUENCE_URL] {link}")
                _save_page_cache(page_title, page_id, next_ver)
                published = True
            elif resp.get("statusCode") in (409, 400) or "version" in str(resp.get("message", "")).lower():
                # Conflit de version → récupérer la version courante et réessayer
                console.print("[yellow]Conflit de version, récupération en cours…[/yellow]")
                try:
                    page_data = _curl("GET",
                                      f"{CONFLUENCE_BASE_URL}/rest/api/content/{page_id}?expand=version")
                    cur_ver = page_data["version"]["number"]
                    resp2 = _do_put(page_id, cur_ver + 1)
                    if resp2.get("id"):
                        link = f"{CONFLUENCE_BASE_URL}/spaces/{CONFLUENCE_SPACE}/pages/{page_id}"
                        console.print(f"[bold green]Page mise à jour : {link}[/bold green]")
                        print(f"[CONFLUENCE_URL] {link}")
                        _save_page_cache(page_title, page_id, cur_ver + 1)
                        published = True
                    else:
                        console.print(f"[red]Erreur mise à jour (retry) : {_json.dumps(resp2)[:300]}[/red]")
                except Exception as e2:
                    console.print(f"[red]Erreur récupération version : {e2}[/red]")
            else:
                console.print(f"[red]Erreur mise à jour (cache) : {_json.dumps(resp)[:300]}[/red]")
        except Exception as e:
            console.print(f"[red]Erreur PUT (cache) : {e}[/red]")
    else:
        # Pas de cache → recherche par titre (2 appels API)
        search_url = (
            f"{CONFLUENCE_BASE_URL}/rest/api/content"
            f"?spaceKey={CONFLUENCE_SPACE}&title={urlquote(page_title)}&expand=version"
        )
        try:
            search_data = _curl("GET", search_url)
            results     = search_data.get("results", [])
        except Exception as e:
            console.print(f"[red]Erreur recherche Confluence : {e}[/red]")
            _sys.exit(1)

        import time as _time_pause
        _time_pause.sleep(2)

        if results:
            page_id         = results[0]["id"]
            current_version = results[0]["version"]["number"]
            try:
                resp = _do_put(page_id, current_version + 1)
                if resp.get("id"):
                    link = f"{CONFLUENCE_BASE_URL}/spaces/{CONFLUENCE_SPACE}/pages/{page_id}"
                    console.print(f"[bold green]Page mise à jour : {link}[/bold green]")
                    print(f"[CONFLUENCE_URL] {link}")
                    _save_page_cache(page_title, page_id, current_version + 1)
                    published = True
                else:
                    console.print(f"[red]Erreur mise à jour : {_json.dumps(resp)[:300]}[/red]")
            except Exception as e:
                console.print(f"[red]Erreur PUT : {e}[/red]")
        else:
            # Page inexistante → création (POST)
            payload = _json.dumps({
                "type":      "page",
                "title":     page_title,
                "space":     {"key": CONFLUENCE_SPACE},
                "ancestors": [{"id": parent_id}],
                "body":      {"storage": {"value": confluence_body,
                                          "representation": "storage"}},
            })
            try:
                resp = _curl("POST", f"{CONFLUENCE_BASE_URL}/rest/api/content", payload)
                if resp.get("id"):
                    new_id = resp["id"]
                    link   = f"{CONFLUENCE_BASE_URL}/spaces/{CONFLUENCE_SPACE}/pages/{new_id}"
                    console.print(f"[bold green]Page créée : {link}[/bold green]")
                    print(f"[CONFLUENCE_URL] {link}")
                    _save_page_cache(page_title, new_id, 1)
                    published = True
                else:
                    console.print(f"[red]Erreur création : {_json.dumps(resp)[:300]}[/red]")
            except Exception as e:
                console.print(f"[red]Erreur POST : {e}[/red]")

    if not published:
        console.print(f"[bold red]Publication Confluence échouée pour '{page_title}'.[/bold red]")
        _sys.exit(1)


def publish_to_confluence(html_content: str, target_date, console):
    console.print(f"[dim]Publication sur Confluence (page {CONFLUENCE_PAGE_ID}) …[/dim]")

    # 1. Récupérer version actuelle
    page_url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{CONFLUENCE_PAGE_ID}?expand=version,title"
    cmd_get = [
        "curl", "-s", "-k",
        "--proxy", f"http://{PROXY_HOST}",
        "--proxy-negotiate", "-U", ":",
        "-H", f"Authorization: Bearer {CONFLUENCE_TOKEN or JIRA_TOKEN}",
        "-H", "Accept: application/json",
        page_url
    ]
    result = subprocess.run(cmd_get, capture_output=True, text=True, encoding="utf-8", errors="replace")
    import time; time.sleep(5)  # Respecter le rate limit Confluence
    if not result.stdout.strip():
        console.print("[red]Impossible de récupérer la page Confluence.[/red]")
        return
    try:
        page_data = _json.loads(result.stdout)
    except _json.JSONDecodeError:
        console.print(f"[red]Réponse Confluence invalide : {result.stdout[:200]}[/red]")
        return

    current_version = page_data.get("version", {}).get("number", 1)
    page_title      = page_data.get("title", f"Tests automatises {ENVIRONMENT}")
    new_version     = current_version + 1

    # 2. Body Confluence avec macro HTML
    confluence_body = (
        '<ac:structured-macro ac:name="html">'
        '<ac:plain-text-body><![CDATA['
        + html_content +
        ']]></ac:plain-text-body>'
        '</ac:structured-macro>'
    )

    payload = _json.dumps({
        "id":    CONFLUENCE_PAGE_ID,
        "type":  "page",
        "title": page_title,
        "space": {"key": CONFLUENCE_SPACE},
        "body":  {
            "storage": {
                "value":          confluence_body,
                "representation": "storage"
            }
        },
        "version": {"number": new_version}
    })

    # 3. PUT pour mettre à jour
    update_url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{CONFLUENCE_PAGE_ID}"
    cmd_put = [
        "curl", "-s", "-k",
        "--proxy", f"http://{PROXY_HOST}",
        "--proxy-negotiate", "-U", ":",
        "-X", "PUT",
        "-H", f"Authorization: Bearer {CONFLUENCE_TOKEN or JIRA_TOKEN}",
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json",
        "-d", payload,
        update_url
    ]
    result_put = subprocess.run(cmd_put, capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        resp = _json.loads(result_put.stdout)
        if resp.get("id"):
            page_link = f"{CONFLUENCE_BASE_URL}/spaces/{CONFLUENCE_SPACE}/pages/{CONFLUENCE_PAGE_ID}"
            console.print(f"[bold green]Page Confluence mise à jour : {page_link}[/bold green]")
        else:
            console.print(f"[red]Erreur Confluence : {result_put.stdout[:300]}[/red]")
    except _json.JSONDecodeError:
        console.print(f"[red]Réponse invalide : {result_put.stdout[:300]}[/red]")

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    arg_parser = argparse.ArgumentParser(description="Rapport XRAY HTML multi-projets")
    arg_parser.add_argument("--date",     default=None,               help="Date YYYY-MM-DD")
    arg_parser.add_argument("--projects", nargs="+", default=DEFAULT_PROJECTS, help="Clés projets")
    arg_parser.add_argument("--testplan", default=None,               help="Clé du Test Plan (ex: OAGRCLI-123)")
    arg_parser.add_argument("--output",   default="rapport_xray.html",help="Fichier HTML de sortie")
    arg_parser.add_argument("--env",        default=None,  help="Environnement XRAY (ex: XITG, XITD, XITR)")
    arg_parser.add_argument("--confluence",            action="store_true", default=False, help="Publier le rapport sur Confluence")
    arg_parser.add_argument("--confluence-page-title", default=None,        help="Titre de la page Confluence à créer/mettre à jour")
    arg_parser.add_argument("--confluence-parent-id",  default="468779106", help="ID de la page parent Confluence (défaut: 468779106)")
    args = arg_parser.parse_args()

    target_date = date.today() - __import__('datetime').timedelta(days=1)
    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"Date invalide : {args.date}")
            sys.exit(1)

    console = Console()

    if JIRA_TOKEN == "VOTRE_TOKEN_ICI":
        console.print("[bold red]Token non configuré. Définissez JIRA_TOKEN.[/bold red]")
        sys.exit(1)

    # Surcharger l'environnement si --env est précisé
    global ENVIRONMENT
    if args.env:
        ENVIRONMENT = args.env.upper()

    session = get_session()
    console.print(f"\n[bold]Rapport XRAY · {ENVIRONMENT} · {target_date.isoformat()}[/bold]\n")

    # Projets
    all_projects = []
    for pkey in args.projects:
        console.print(f"[dim]Récupération {pkey} …[/dim]")
        issues = fetch_test_executions(session, pkey, target_date)
        executions_data = []
        for issue in issues:
            key  = issue["key"]
            runs = fetch_test_runs(session, key)
            issue["_runs"] = runs
            if not runs:
                console.print(f"  [dim]{key} → 0 test(s) — ignoré[/dim]")
                continue  # Ne pas inclure les exécutions sans tests
            executions_data.append(issue)
            console.print(f"  [dim]{key} → {len(runs)} test(s)[/dim]")
        all_projects.append({"key": pkey, "executions": executions_data})

    # Test Plans — tous les plans des projets, dernière exécution avec tests
    all_plan_sections = []
    if args.testplan:
        # Mode clé unique (rétrocompatible)
        console.print(f"\n[dim]Test Plan {args.testplan} …[/dim]")
        plan_info   = fetch_test_plan(session, args.testplan)
        plan_fields = plan_info.get("fields", {})
        last_exec   = fetch_last_execution_with_tests(session, args.testplan, console)
        all_plan_sections.append({
            "key":            args.testplan,
            "summary":        plan_fields.get("summary", "—"),
            "last_execution": last_exec,
        })
    else:
        # Mode automatique : tous les Test Plans de chaque projet
        for pkey in args.projects:
            console.print(f"\n[dim]Récupération des Test Plans de {pkey} …[/dim]")
            plans = fetch_all_test_plans(session, pkey)
            console.print(f"[dim]  {len(plans)} Test Plan(s) trouvé(s) dans {pkey}[/dim]")
            for plan in plans:
                plan_key    = plan["key"]
                plan_summary = plan.get("fields", {}).get("summary", "—")
                last_exec   = fetch_last_execution_with_tests(session, plan_key, console)
                if last_exec and last_exec.get("_runs"):  # Plans avec au moins 1 test
                    all_plan_sections.append({
                        "key":            plan_key,
                        "summary":        plan_summary,
                        "last_execution": last_exec,
                    })
    plan_section = all_plan_sections  # on passe la liste complète

    # Génération HTML
    html = build_html(all_projects, plan_section if plan_section else [], target_date, ENVIRONMENT)
    output_path = args.output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    console.print(f"\n[bold green]Rapport généré : {output_path}[/bold green]")
    console.print(f"[dim]Ouvrez-le dans votre navigateur ou partagez-le par email.[/dim]\n")

    # Sauvegarde des stats dans le fichier historique JSON (pour la page d'accueil)
    _stats_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats_history.json")
    try:
        with open(_stats_file, "r", encoding="utf-8") as _sf:
            _history = json.load(_sf)
    except Exception:
        _history = []

    # Calcul des stats globales du rapport courant
    _grand = {"PASS": 0, "FAIL": 0, "EXECUTING": 0, "TODO": 0, "ABORTED": 0}
    for _proj in all_projects:
        for _ex in _proj.get("executions", []):
            _s = compute_stats(_ex.get("_runs", []))
            for _k in _grand:
                _grand[_k] += _s.get(_k, 0)
    _total = sum(_grand.values())
    _rate  = round(_grand["PASS"] / _total * 100) if _total > 0 else 0

    # Supprime l'entrée existante pour (date, env) si elle existe déjà
    # On utilise la date du fichier de sortie (= date de génération = aujourd'hui)
    # pour que le sélecteur de date dans accueil.html corresponde au nom du fichier rapport.
    _date_str = date.today().isoformat()
    _history = [e for e in _history if not (e.get("date") == _date_str and e.get("env") == ENVIRONMENT)]
    _history.append({
        "date":       _date_str,
        "env":        ENVIRONMENT,
        "report":     os.path.basename(output_path),
        "total":      _total,
        "pass":       _grand["PASS"],
        "fail":       _grand["FAIL"],
        "executing":  _grand["EXECUTING"],
        "todo":       _grand["TODO"],
        "aborted":    _grand["ABORTED"],
        "rate":       _rate,
        "generated":  datetime.now().isoformat(timespec="seconds"),
    })
    # Trier par date pour la courbe
    _history.sort(key=lambda e: (e.get("date", ""), e.get("env", "")))
    try:
        with open(_stats_file, "w", encoding="utf-8") as _sf:
            json.dump(_history, _sf, indent=2, ensure_ascii=False)
        console.print(f"[dim]Statistiques sauvegardées dans stats_history.json[/dim]")
    except Exception as _e:
        console.print(f"[yellow]Avertissement : impossible d'écrire stats_history.json : {_e}[/yellow]")

    if args.confluence:
        if args.confluence_page_title:
            # Mode page enfant nommée (usage quotidien)
            global CONFLUENCE_TOKEN
            if not CONFLUENCE_TOKEN:
                CONFLUENCE_TOKEN = os.getenv("CONFLUENCE_TOKEN", "")
            publish_to_confluence_child(
                html,
                args.confluence_page_title,
                args.confluence_parent_id,
                console,
            )
        else:
            # Mode historique (page fixe par ID)
            publish_to_confluence(html, target_date, console)

if __name__ == "__main__":
    main()

