from datetime import date, datetime
from html import escape


def compute_stats(runs: list) -> dict:
    stats = {"PASS": 0, "FAIL": 0, "EXECUTING": 0, "TODO": 0, "ABORTED": 0, "BLOCKED": 0, "OTHER": 0}
    for run in runs:
        raw = run.get("status") or "OTHER"
        status = (raw if isinstance(raw, str) else raw.get("name", "OTHER")).upper()
        stats[status] = stats.get(status, 0) + 1
    return stats


def success_rate(stats: dict) -> int:
    total = sum(stats.values())
    if total == 0:
        return 0
    return round(stats.get("PASS", 0) / total * 100)


def build_html(
    all_projects: list,
    plan_sections: list,
    target_date: date,
    environment: str,
    jira_base_url: str,
    jira_open_issues: list,
    dynatrace_open_problems: list,
    jira_open_error: str | None = None,
    dynatrace_error: str | None = None,
    dynatrace_tag: str | None = None,
) -> str:
    def stat_bar(stats, rate=None):
        total = sum(stats.values())
        if rate is None:
            rate = success_rate(stats)
        if total == 0:
            return '<div class="donut-wrap"><div class="donut" style="background:#ebecf0"><div class="donut-hole"><span class="donut-rate">N/A</span></div></div></div>'
        color_hex = {
            "PASS": "#0a7a3e", "FAIL": "#c9372c", "EXECUTING": "#f59f00",
            "TODO": "#0052cc", "ABORTED": "#6554c0", "BLOCKED": "#97a0af", "OTHER": "#c1c7d0",
        }
        labels = {
            "PASS": "Pass", "FAIL": "Fail", "EXECUTING": "En cours",
            "TODO": "Todo", "ABORTED": "Abandonné", "BLOCKED": "Bloqué", "OTHER": "Autre",
        }
        stops = []
        legend = ""
        cum = 0.0
        for k, hex_color in color_hex.items():
            v = stats.get(k, 0)
            if not v:
                continue
            pct = v / total * 100
            start, cum = cum, cum + pct
            stops.append(f"{hex_color} {start:.2f}% {cum:.2f}%")
            legend += (
                f'<div class="legend-item"><span class="dot" style="background:{hex_color}"></span>'
                f'{labels[k]}: <b>{v}</b></div>'
            )
        gradient = ", ".join(stops)
        return f"""<div class="donut-wrap">
          <div class="donut" style="background:conic-gradient({gradient})">
            <div class="donut-hole"><span class="donut-rate">{rate}%</span><span class="donut-rate-lbl">Taux</span></div>
          </div>
          <div class="legend">{legend}</div>
        </div>"""

    def rate_badge(rate):
        cls = "pass" if rate >= 80 else ("warn" if rate >= 50 else "fail")
        return f'<span class="rate-badge {cls}">{rate}%</span>'

    def format_dynatrace_ts(ts_ms):
        if ts_ms is None:
            return "—"
        try:
            return datetime.fromtimestamp(int(ts_ms) / 1000).strftime("%d/%m/%Y %H:%M")
        except (ValueError, TypeError, OSError):
            return str(ts_ms)

    def dynatrace_rows(problems):
        html = ""
        for problem in problems:
            pid = problem.get("problemId", "—")
            title = problem.get("title", "—")
            severity = problem.get("severityLevel", "—")
            impact = problem.get("impactLevel", "—")
            status = problem.get("status", "—")
            start_time = format_dynatrace_ts(problem.get("startTime"))
            html += f"""
            <tr>
              <td>{escape(pid)}</td>
              <td class="summary">{escape(title)[:120]}</td>
              <td>{escape(severity)}</td>
              <td>{escape(impact)}</td>
              <td>{escape(status)}</td>
              <td>{escape(start_time)}</td>
            </tr>"""
        return html

    project_blocks = ""
    grand = {"PASS": 0, "FAIL": 0, "EXECUTING": 0, "TODO": 0, "ABORTED": 0, "total": 0}
    for proj in all_projects:
        pkey = proj["key"]
        execs = proj["executions"]
        pt = {"PASS": 0, "FAIL": 0, "EXECUTING": 0, "TODO": 0, "ABORTED": 0}
        for ex in execs:
            s = compute_stats(ex.get("_runs", []))
            for k in pt:
                pt[k] += s.get(k, 0)
        ptotal = sum(pt.values())
        prate = round(pt["PASS"] / ptotal * 100) if ptotal > 0 else 0
        for k in pt:
            grand[k] += pt[k]
        grand["total"] += ptotal

        project_blocks += f"""
        <div class="project-block">
          <div class="project-header">
            <span class="project-title">{pkey}</span>
            <span class="project-meta">{len(execs)} campagne(s) · {ptotal} tests · {rate_badge(prate)}</span>
          </div>
          <div class="plan-summary">
            <div class="kpi-row">
              <div class="kpi"><span class="kpi-val">{len(execs)}</span><span class="kpi-lbl">CAMPAGNES</span></div>
              <div class="kpi"><span class="kpi-val pass-txt">{pt.get('PASS',0)}</span><span class="kpi-lbl">PASS</span></div>
              <div class="kpi"><span class="kpi-val fail-txt">{pt.get('FAIL',0)}</span><span class="kpi-lbl">FAIL</span></div>
              <div class="kpi"><span class="kpi-val exec-txt">{pt.get('EXECUTING',0)}</span><span class="kpi-lbl">EN COURS</span></div>
              <div class="kpi"><span class="kpi-val todo-txt">{pt.get('TODO',0)}</span><span class="kpi-lbl">TODO</span></div>
              <div class="kpi"><span class="kpi-val aborted-txt">{pt.get('ABORTED',0)}</span><span class="kpi-lbl">ABORT</span></div>
              <div class="kpi"><span class="kpi-val">{ptotal}</span><span class="kpi-lbl">TOTAL TESTS</span></div>
              <div class="kpi">{rate_badge(prate)}<span class="kpi-lbl">TAUX</span></div>
            </div>
            {stat_bar(pt, prate)}
          </div>
        </div>"""

    all_plan_blocks_html = ""
    for plan_section in (plan_sections or []):
        pk = plan_section.get("key", "—")
        summ = plan_section.get("summary", "—")
        ex = plan_section.get("last_execution")
        if ex:
            runs = ex.get("_runs", [])
            stats = compute_stats(runs)
            total = sum(stats.values())
            rate = success_rate(stats)
            all_plan_blocks_html += f"""
        <div class="project-block plan-block">
          <div class="project-header">
            <span class="project-title">{summ}</span>
            <span class="project-meta">{pk}</span>
          </div>
          <div class="plan-summary">
            <div class="plan-exec-key">Dernière exécution : <a href="{jira_base_url}/browse/{ex.get('key','')}" target="_blank" class="key-link">{ex.get('key','—')}</a></div>
            <div class="kpi-row">
              <div class="kpi"><span class="kpi-val pass-txt">{stats.get('PASS',0)}</span><span class="kpi-lbl">PASS</span></div>
              <div class="kpi"><span class="kpi-val fail-txt">{stats.get('FAIL',0)}</span><span class="kpi-lbl">FAIL</span></div>
              <div class="kpi"><span class="kpi-val exec-txt">{stats.get('EXECUTING',0)}</span><span class="kpi-lbl">EN COURS</span></div>
              <div class="kpi"><span class="kpi-val todo-txt">{stats.get('TODO',0)}</span><span class="kpi-lbl">TODO</span></div>
              <div class="kpi"><span class="kpi-val">{total}</span><span class="kpi-lbl">TOTAL</span></div>
              <div class="kpi">{rate_badge(rate)}<span class="kpi-lbl">TAUX</span></div>
            </div>
            {stat_bar(stats, rate)}
          </div>
        </div>"""
        else:
            all_plan_blocks_html += f"""
        <div class="project-block plan-block">
          <div class="project-header">
            <span class="project-title">{summ}</span>
            <span class="project-meta">{pk}</span>
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
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f4f5f7;color:#172b4d;font-size:14px;}}
  header{{background:#FF7900;padding:20px 32px;color:#fff;display:flex;align-items:center;justify-content:space-between;}}
  header h1{{font-size:20px;font-weight:600;letter-spacing:.3px}}
  header .sub{{font-size:13px;opacity:.85;margin-top:3px}}
  .logo{{font-size:26px;font-weight:700;letter-spacing:1px;color:#fff}}
  .main{{padding:24px 32px;max-width:1200px;margin:0 auto}}
  .kpi-strip{{display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap}}
  .kpi-card{{background:#fff;border-radius:8px;padding:14px 20px;border:1px solid #e1e4e8;flex:1;min-width:130px;text-align:center}}
  .kpi-card .val{{font-size:28px;font-weight:700;line-height:1.1}}
  .kpi-card .lbl{{font-size:11px;color:#6b778c;text-transform:uppercase;letter-spacing:.6px;margin-top:4px}}
  .pass-txt{{color:#0a7a3e}} .fail-txt{{color:#c9372c}}
  .exec-txt{{color:#974f00}} .todo-txt{{color:#0052cc}} .aborted-txt{{color:#6554c0}}
  .project-block{{background:#fff;border-radius:8px;border:1px solid #e1e4e8;margin-bottom:20px;overflow:hidden}}
  .plan-block{{border-top:3px solid #FF7900}}
  .project-header{{padding:14px 20px;background:#f8f9fa;border-bottom:1px solid #e1e4e8;display:flex;align-items:center;justify-content:space-between}}
  .project-title{{font-size:15px;font-weight:600;color:#172b4d}}
  .project-meta{{font-size:12px;color:#6b778c;display:flex;align-items:center;gap:8px}}
  .table-wrap{{overflow-x:auto}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{padding:9px 12px;text-align:left;background:#f8f9fa;border-bottom:2px solid #e1e4e8;color:#6b778c;font-size:11px;text-transform:uppercase;letter-spacing:.5px;white-space:nowrap}}
  td{{padding:9px 12px;border-bottom:1px solid #f0f0f0;vertical-align:middle}}
  tr:last-child td{{border-bottom:none}}
  tr:hover td{{background:#f8f9fa}}
  .center{{text-align:center}}
  .key-link{{color:#0052cc;text-decoration:none;font-weight:500}}
  .key-link:hover{{text-decoration:underline}}
  .summary{{color:#42526e;max-width:280px}}
  .empty{{text-align:center;color:#6b778c;padding:20px;font-style:italic}}
  .donut-wrap{{display:flex;align-items:center;gap:20px;flex-wrap:wrap}}
  .donut{{position:relative;width:96px;height:96px;min-width:96px;border-radius:50%}}
  .donut-hole{{position:absolute;inset:12px;background:#fff;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center}}
  .donut-rate{{font-size:18px;font-weight:700;color:#172b4d;line-height:1.1}}
  .donut-rate-lbl{{font-size:9px;color:#6b778c;text-transform:uppercase;letter-spacing:.5px;margin-top:2px}}
  .legend{{display:flex;flex-wrap:wrap;gap:8px 16px;font-size:12px;color:#42526e}}
  .legend-item{{display:flex;align-items:center;gap:6px;white-space:nowrap}}
  .dot{{width:9px;height:9px;border-radius:50%;display:inline-block}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;text-transform:uppercase}}
  .badge.pass,.badge.passed{{background:#e3fcef;color:#0a7a3e}}
  .badge.fail,.badge.failed{{background:#ffebe6;color:#c9372c}}
  .badge.executing{{background:#fff7d6;color:#974f00}}
  .badge.todo{{background:#e9f0fb;color:#0052cc}}
  .badge.aborted{{background:#f0ebff;color:#6554c0}}
  .badge.blocked{{background:#f4f5f7;color:#6b778c}}
  .rate-badge{{display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:700}}
  .rate-badge.pass{{background:#e3fcef;color:#0a7a3e}}
  .rate-badge.warn{{background:#fff7d6;color:#974f00}}
  .rate-badge.fail{{background:#ffebe6;color:#c9372c}}
  .plan-summary{{padding:16px 20px}}
  .plan-exec-key{{font-size:13px;color:#6b778c;margin-bottom:12px}}
  .kpi-row{{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:12px}}
  .kpi{{display:flex;flex-direction:column;align-items:center;min-width:60px}}
  .kpi-val{{font-size:24px;font-weight:700;line-height:1}}
  .kpi-lbl{{font-size:10px;color:#6b778c;text-transform:uppercase;letter-spacing:.5px;margin-top:4px}}
  .section-title{{font-size:13px;font-weight:600;color:#6b778c;text-transform:uppercase;letter-spacing:.6px;margin:24px 0 10px}}
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
  <div class="section-title">Tickets Jira ouverts ({environment})</div>
  <div class="project-block">
    <div class="plan-summary">
      {'<p class="empty" style="padding:0">' + escape(jira_open_error) + '</p>' if jira_open_error else '<div class="kpi-row"><div class="kpi"><span class="kpi-val">' + str(len(jira_open_issues)) + '</span><span class="kpi-lbl">TICKETS OUVERTS</span></div></div>'}
    </div>
  </div>
  <div class="section-title">Problèmes Dynatrace ouverts ({environment}{' · tag: ' + dynatrace_tag if dynatrace_tag else ''})</div>
  <div class="project-block"><div class="table-wrap"><table><thead><tr><th>ID</th><th>Titre</th><th>Sévérité</th><th>Impact</th><th>Statut</th><th>Début</th></tr></thead><tbody>{'<tr><td colspan="6" class="empty">' + escape(dynatrace_error) + '</td></tr>' if dynatrace_error else (dynatrace_rows(dynatrace_open_problems) if dynatrace_open_problems else '<tr><td colspan="6" class="empty">Aucun problème Dynatrace ouvert trouvé</td></tr>')}</tbody></table></div></div>
  <div class="section-title">Exécutions du jour par projet</div>
  {project_blocks}
  {"<div class='section-title'>Dernière exécution par Test Plan</div>" + all_plan_blocks_html if all_plan_blocks_html else ""}
</div>
<footer>Rapport généré automatiquement · Orange SI · XRAY / Jira</footer>
</body>
</html>"""
