"""
generate_accueil.py
-------------------
Génère la page d'accueil HTML (accueil.html) à partir de stats_history.json.

La page contient :
  - 2 camemberts du jour : taux de réussite global XITG et XMQ1
    → clic sur un camembert → ouvre le rapport HTML de l'environnement
  - Une courbe d'évolution du taux de réussite par environnement dans le temps

Usage :
    py generate_accueil.py
    py generate_accueil.py --output accueil.html
    py generate_accueil.py --envs XITG XMQ1
"""

import argparse
import json
import os
import sys
from datetime import datetime, date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATS_FILE  = os.path.join(SCRIPT_DIR, "stats_history.json")
DEFAULT_ENVS = ["XITG", "XMQ1"]

# Couleurs Orange SI
ENV_COLORS = {
    "XITG": {"main": "#FF7900", "light": "#FFD580", "bg": "#FFF5E6"},
    "XMQ1": {"main": "#0052CC", "light": "#80ABFF", "bg": "#E6EEFF"},
    "DEFAULT": {"main": "#6554c0", "light": "#c0b8f0", "bg": "#F0EEFF"},
}

STATUS_COLORS = {
    "pass":      "#0a7a3e",
    "fail":      "#c9372c",
    "executing": "#f59f00",
    "todo":      "#0052cc",
    "aborted":   "#6554c0",
}


def load_history():
    if not os.path.exists(STATS_FILE):
        return []
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Impossible de lire stats_history.json : {e}", file=sys.stderr)
        return []


def latest_entry(history: list, env: str) -> dict | None:
    """Retourne l'entrée la plus récente pour un environnement donné."""
    entries = [e for e in history if e.get("env") == env]
    return entries[-1] if entries else None


def report_filename(env: str, entry: dict) -> str:
    """Nom du fichier HTML de rapport pour l'environnement."""
    if entry and entry.get("report"):
        return entry["report"]
    d = entry.get("date", date.today().isoformat()) if entry else date.today().isoformat()
    return f"rapport_{env}_{d}.html"


def pie_data_json(entry: dict) -> str:
    if not entry:
        return json.dumps({"labels": ["Pas de données"], "values": [1], "colors": ["#e1e4e8"]})
    labels = ["PASS", "FAIL", "EN COURS", "TODO", "ABORTED"]
    values = [
        entry.get("pass", 0),
        entry.get("fail", 0),
        entry.get("executing", 0),
        entry.get("todo", 0),
        entry.get("aborted", 0),
    ]
    colors = ["#0a7a3e", "#c9372c", "#f59f00", "#0052cc", "#6554c0"]
    # Filtrer les 0
    filtered = [(l, v, c) for l, v, c in zip(labels, values, colors) if v > 0]
    if not filtered:
        return json.dumps({"labels": ["Aucun test"], "values": [1], "colors": ["#e1e4e8"]})
    ls, vs, cs = zip(*filtered)
    return json.dumps({"labels": list(ls), "values": list(vs), "colors": list(cs)})


def build_html(history: list, envs: list) -> str:
    today_str = date.today().isoformat()

    # ── Données statiques Python (courbe + KPI + tableau) ─────────────────
    latest   = {env: latest_entry(history, env) for env in envs}
    all_dates = sorted({e.get("date") for e in history if e.get("date")})

    # Couleurs par env pour JS
    env_colors_js = json.dumps({
        env: ENV_COLORS.get(env, ENV_COLORS["DEFAULT"])
        for env in envs
    })

    # Séries courbe
    series_js = []
    for env in envs:
        col = ENV_COLORS.get(env, ENV_COLORS["DEFAULT"])
        rates = []
        for d in all_dates:
            entry = next((e for e in history if e.get("env") == env and e.get("date") == d), None)
            rates.append(entry.get("rate") if entry else None)
        series_js.append(f"""{{
            label: '{env}',
            data: {json.dumps(rates)},
            borderColor: '{col["main"]}',
            backgroundColor: '{col["main"]}22',
            fill: true,
            tension: 0.4,
            pointRadius: 5,
            pointHoverRadius: 8,
            spanGaps: true,
        }}""")
    chart_dates_js  = json.dumps(all_dates)
    chart_series_js = ",\n      ".join(series_js)

    # KPI strip (dernier rapport, statique)
    kpi_strip = ""
    for env in envs:
        e   = latest[env]
        col = ENV_COLORS.get(env, ENV_COLORS["DEFAULT"])
        if e:
            rc = "pass" if e.get("rate",0) > 5 else "fail"
            kpi_strip += f"""
            <div class="kpi-card" style="border-left:4px solid {col['main']}">
              <div class="kpi-env" style="color:{col['main']}">{env}</div>
              <div class="kpi-row-inner">
                <div class="kpi-item"><span class="kv pass-txt">{e.get('pass',0)}</span><span class="kl">PASS</span></div>
                <div class="kpi-item"><span class="kv fail-txt">{e.get('fail',0)}</span><span class="kl">FAIL</span></div>
                <div class="kpi-item"><span class="kv">{e.get('total',0)}</span><span class="kl">TOTAL</span></div>
                <div class="kpi-item"><span class="kv rate-{rc}">{e.get('rate',0)}%</span><span class="kl">TAUX</span></div>
              </div>
            </div>"""
        else:
            kpi_strip += f"""
            <div class="kpi-card" style="border-left:4px solid {col['main']}">
              <div class="kpi-env" style="color:{col['main']}">{env}</div>
              <div style="color:#6b778c;font-size:13px;padding:8px 0">Aucune donnée</div>
            </div>"""

    # Options du sélecteur de date (dates disponibles dans l'historique)
    date_options = ""
    latest_date  = all_dates[-1] if all_dates else ""
    for d in reversed(all_dates):
        sel = ' selected' if d == latest_date else ''
        date_options += f'<option value="{d}"{sel}>{d}</option>\n'

    # Tableau historique
    history_rows = ""
    for e in reversed(history[-60:]):
        env      = e.get("env", "—")
        col      = ENV_COLORS.get(env, ENV_COLORS["DEFAULT"])
        rate     = e.get("rate", 0)
        rate_cls = "pass" if rate > 5 else "fail"
        rep      = e.get("report", "")
        history_rows += f"""
        <tr>
          <td>{e.get('date','—')}</td>
          <td><span class="env-badge-sm" style="background:{col['main']}">{env}</span></td>
          <td class="center">{e.get('total',0)}</td>
          <td class="center pass-txt">{e.get('pass',0)}</td>
          <td class="center fail-txt">{e.get('fail',0)}</td>
          <td class="center exec-txt">{e.get('executing',0)}</td>
          <td class="center"><span class="rate-badge-sm {rate_cls}">{rate}%</span></td>
          <td class="center"><a href="{rep}" class="report-link-sm" style="color:{col['main']}">Rapport</a></td>
        </tr>"""

    # Bloc canevas camemberts (un par env, rendu dynamique par JS)
    pie_canvases = ""
    for env in envs:
        col = ENV_COLORS.get(env, ENV_COLORS["DEFAULT"])
        pie_canvases += f"""
        <div class="pie-card" id="piecard_{env}" style="border-top:4px solid {col['main']}">
          <div class="pie-card-header">
            <div class="env-badge" style="background:{col['main']}">{env}</div>
            <div class="pie-meta">
              <span id="pie_date_{env}">—</span>
              <span class="total-badge" id="pie_total_{env}">— tests</span>
            </div>
          </div>
          <div class="pie-wrapper">
            <canvas id="pie_{env}" width="240" height="240"></canvas>
            <div class="pie-center-label">
              <span class="rate-big" id="pie_rate_{env}">—%</span>
              <span class="rate-lbl">réussite</span>
            </div>
          </div>
          <div class="pie-legend" id="legend_{env}"></div>
          <a id="pie_link_{env}" href="#" class="report-link" style="color:{col['main']}">
            Voir le rapport détaillé →
          </a>
        </div>"""

    # Tout l'historique embarqué en JSON pour le JS
    all_history_js = json.dumps(history, ensure_ascii=False)
    all_envs_js    = json.dumps(envs)
    now_str = datetime.now().strftime("%d/%m/%Y à %H:%M")

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>XRAY — Tableau de bord</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.2/dist/chart.umd.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
        background:#f4f5f7;color:#172b4d;font-size:14px}}
  header{{background:#FF7900;padding:18px 32px;color:#fff;
          display:flex;align-items:center;justify-content:space-between}}
  header h1{{font-size:20px;font-weight:600}}
  header .sub{{font-size:12px;opacity:.85;margin-top:4px}}
  .logo{{font-size:26px;font-weight:700;letter-spacing:1px}}
  .main{{padding:28px 32px;max-width:1200px;margin:0 auto}}
  .section-title{{font-size:13px;font-weight:600;color:#6b778c;
                  text-transform:uppercase;letter-spacing:.6px;margin:0 0 14px}}
  /* KPI strip */
  .kpi-strip{{display:flex;gap:16px;margin-bottom:28px;flex-wrap:wrap}}
  .kpi-card{{background:#fff;border-radius:8px;padding:16px 20px;
             flex:1;min-width:200px;border:1px solid #e1e4e8;
             box-shadow:0 1px 3px rgba(0,0,0,.06)}}
  .kpi-env{{font-size:15px;font-weight:700;margin-bottom:10px}}
  .kpi-row-inner{{display:flex;gap:16px;flex-wrap:wrap}}
  .kpi-item{{display:flex;flex-direction:column;align-items:center;min-width:50px}}
  .kv{{font-size:22px;font-weight:700;line-height:1}}
  .kl{{font-size:10px;color:#6b778c;text-transform:uppercase;
       letter-spacing:.5px;margin-top:3px}}
  /* Sélecteur de date */
  .date-bar{{display:flex;align-items:center;gap:12px;margin-bottom:16px;
             background:#fff;border:1px solid #e1e4e8;border-radius:8px;
             padding:12px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
  .date-bar label{{font-size:13px;font-weight:600;color:#42526e;white-space:nowrap}}
  .date-bar select{{font-size:13px;padding:6px 10px;border:1px solid #dfe1e6;
                    border-radius:6px;background:#f8f9fa;color:#172b4d;cursor:pointer;
                    min-width:140px}}
  .date-bar select:focus{{outline:none;border-color:#FF7900;box-shadow:0 0 0 2px #FF790022}}
  .date-nav{{display:flex;gap:4px}}
  .date-nav button{{background:#fff;border:1px solid #dfe1e6;border-radius:6px;
                    padding:5px 10px;cursor:pointer;font-size:14px;color:#42526e;
                    transition:background .15s}}
  .date-nav button:hover{{background:#f0f0f0}}
  .date-nav button:disabled{{opacity:.35;cursor:not-allowed}}
  /* Camemberts */
  .pies-row{{display:flex;gap:20px;margin-bottom:32px;flex-wrap:wrap}}
  .pie-card{{background:#fff;border-radius:10px;border:1px solid #e1e4e8;
             padding:20px;flex:1;min-width:280px;max-width:420px;
             box-shadow:0 1px 3px rgba(0,0,0,.06)}}
  .pie-card-header{{display:flex;align-items:center;gap:10px;margin-bottom:16px}}
  .env-badge{{color:#fff;font-weight:700;font-size:13px;
              padding:3px 10px;border-radius:4px}}
  .pie-meta{{display:flex;flex-direction:column;gap:2px;font-size:12px;color:#6b778c}}
  .total-badge{{font-weight:600;color:#172b4d}}
  .pie-wrapper{{position:relative;width:240px;height:240px;margin:0 auto 16px;cursor:pointer}}
  .pie-wrapper canvas{{display:block}}
  .pie-center-label{{position:absolute;top:50%;left:50%;
                      transform:translate(-50%,-50%);text-align:center;
                      pointer-events:none}}
  .rate-big{{font-size:32px;font-weight:800;display:block}}
  .rate-big.pass{{color:#0a7a3e}} .rate-big.fail{{color:#c9372c}}
  .rate-lbl{{font-size:11px;color:#6b778c;text-transform:uppercase;letter-spacing:.5px}}
  .pie-legend{{display:flex;flex-wrap:wrap;gap:6px 14px;margin-bottom:14px;
               justify-content:center;font-size:12px;color:#42526e}}
  .pie-legend-item{{display:flex;align-items:center;gap:5px}}
  .pie-legend-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
  .report-link{{display:block;text-align:center;font-weight:600;font-size:13px;
                text-decoration:none;padding:8px;border-radius:6px;
                background:#f4f5f7;transition:background .15s}}
  .report-link:hover{{background:#e8e9eb}}
  .no-data-pie{{text-align:center;color:#6b778c;font-style:italic;
                padding:30px 0;font-size:13px}}
  /* Courbe */
  .chart-card{{background:#fff;border-radius:10px;border:1px solid #e1e4e8;
               padding:24px;margin-bottom:32px;
               box-shadow:0 1px 3px rgba(0,0,0,.06)}}
  .chart-card canvas{{max-height:320px}}
  /* Tableau historique */
  .history-card{{background:#fff;border-radius:10px;border:1px solid #e1e4e8;
                 overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{padding:9px 14px;background:#f8f9fa;border-bottom:2px solid #e1e4e8;
      font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#6b778c;text-align:left}}
  td{{padding:9px 14px;border-bottom:1px solid #f0f0f0;vertical-align:middle}}
  tr:last-child td{{border-bottom:none}}
  tr:hover td{{background:#f8f9fa}}
  .center{{text-align:center}}
  .pass-txt{{color:#0a7a3e;font-weight:600}}
  .fail-txt{{color:#c9372c;font-weight:600}}
  .exec-txt{{color:#974f00;font-weight:600}}
  .env-badge-sm{{color:#fff;font-weight:600;font-size:11px;padding:2px 7px;border-radius:3px}}
  .rate-badge-sm{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700}}
  .rate-badge-sm.pass{{background:#e3fcef;color:#0a7a3e}}
  .rate-badge-sm.warn{{background:#fff7d6;color:#974f00}}
  .rate-badge-sm.fail{{background:#ffebe6;color:#c9372c}}
  .report-link-sm{{font-weight:600;font-size:12px;text-decoration:none}}
  .report-link-sm:hover{{text-decoration:underline}}
  .rate-warn{{color:#974f00}}
  footer{{text-align:center;color:#97a0af;font-size:11px;padding:20px 0 32px}}
</style>
</head>
<body>
<header>
  <div>
    <div class="logo">Orange</div>
    <h1>Tableau de bord XRAY — Qualité logicielle</h1>
    <div class="sub">Généré le {now_str} &nbsp;·&nbsp; Données : {len(history)} entrée(s) historiques</div>
  </div>
</header>

<div class="main">

  <!-- KPI dernier rapport -->
  <div class="section-title">Résultats du dernier rapport</div>
  <div class="kpi-strip">{kpi_strip}</div>

  <!-- Sélecteur de date + camemberts -->
  <div class="section-title">Taux de réussite par environnement</div>
  <div class="date-bar">
    <label>📅 Date du rapport :</label>
    <div class="date-nav">
      <button id="btnPrev" title="Rapport précédent">◀</button>
    </div>
    <select id="dateSelect">
      {date_options if date_options else '<option value="">Aucune donnée</option>'}
    </select>
    <div class="date-nav">
      <button id="btnNext" title="Rapport suivant">▶</button>
    </div>
    <span id="dateLabel" style="font-size:12px;color:#6b778c;margin-left:4px"></span>
  </div>
  <div class="pies-row">{pie_canvases}</div>

  <!-- Courbe évolution -->
  <div class="section-title">Évolution du taux de réussite</div>
  <div class="chart-card">
    <canvas id="lineChart"></canvas>
  </div>

  <!-- Historique tabulaire -->
  <div class="section-title">Historique détaillé</div>
  <div class="history-card">
    <table>
      <thead>
        <tr>
          <th>Date</th><th>Env.</th><th class="center">Total</th>
          <th class="center pass-txt">PASS</th>
          <th class="center fail-txt">FAIL</th>
          <th class="center exec-txt">EN COURS</th>
          <th class="center">Taux</th>
          <th class="center">Rapport</th>
        </tr>
      </thead>
      <tbody>
        {history_rows if history_rows else '<tr><td colspan="8" style="text-align:center;color:#6b778c;padding:20px;font-style:italic">Aucun historique disponible</td></tr>'}
      </tbody>
    </table>
  </div>

</div>
<footer>Tableau de bord généré automatiquement · Orange SI · XRAY / Jira</footer>

<script>
// ── Données embarquées ────────────────────────────────────────────────────────
var ALL_HISTORY  = {all_history_js};
var ALL_ENVS     = {all_envs_js};
var ENV_COLORS   = {env_colors_js};
var pieCharts    = {{}};  // {{env: Chart}}

// ── Utilitaires ───────────────────────────────────────────────────────────────
function getEntry(date, env) {{
  return ALL_HISTORY.find(function(e) {{ return e.date === date && e.env === env; }}) || null;
}}

function pieDataForEntry(entry) {{
  if (!entry || entry.total === 0) {{
    return {{ labels: ['Pas de données'], values: [1], colors: ['#e1e4e8'] }};
  }}
  var labels = [], values = [], colors = [];
  var map = [
    ['PASS',     entry.pass      || 0, '#0a7a3e'],
    ['FAIL',     entry.fail      || 0, '#c9372c'],
    ['EN COURS', entry.executing || 0, '#f59f00'],
    ['TODO',     entry.todo      || 0, '#0052cc'],
    ['ABORTED',  entry.aborted   || 0, '#6554c0'],
  ];
  map.forEach(function(row) {{
    if (row[1] > 0) {{ labels.push(row[0]); values.push(row[1]); colors.push(row[2]); }}
  }});
  if (labels.length === 0) return {{ labels: ['Aucun test'], values: [1], colors: ['#e1e4e8'] }};
  return {{ labels: labels, values: values, colors: colors }};
}}

// ── Initialisation des camemberts ─────────────────────────────────────────────
ALL_ENVS.forEach(function(env) {{
  var canvas = document.getElementById('pie_' + env);
  if (!canvas) return;
  var ctx = canvas.getContext('2d');
  pieCharts[env] = new Chart(ctx, {{
    type: 'doughnut',
    data: {{ labels: [], datasets: [{{ data: [], backgroundColor: [], borderWidth: 2, borderColor: '#fff', hoverOffset: 8 }}] }},
    options: {{
      cutout: '68%',
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{
            label: function(ctx) {{
              var total = ctx.dataset.data.reduce(function(a,b){{return a+b;}},0);
              var pct = total > 0 ? Math.round(ctx.parsed / total * 100) : 0;
              return ' ' + ctx.label + ' : ' + ctx.parsed + ' (' + pct + '%)';
            }}
          }}
        }}
      }},
      animation: {{ animateScale: true }},
    }}
  }});
  // Clic → ouvrir le rapport
  canvas.style.cursor = 'pointer';
  canvas.addEventListener('click', function(e) {{
    var pts = pieCharts[env].getElementsAtEventForMode(e, 'nearest', {{intersect:true}}, true);
    var link = document.getElementById('pie_link_' + env);
    if (pts.length && link && link.href && link.href !== '#') {{
      window.open(link.href, '_blank');
    }}
  }});
}});

// ── Mise à jour des camemberts pour une date donnée ───────────────────────────
function updatePies(date) {{
  ALL_ENVS.forEach(function(env) {{
    var entry  = getEntry(date, env);
    var chart  = pieCharts[env];
    var col    = ENV_COLORS[env] || {{ main: '#6554c0' }};
    var data   = pieDataForEntry(entry);

    // Mettre à jour le chart
    chart.data.labels                        = data.labels;
    chart.data.datasets[0].data             = data.values;
    chart.data.datasets[0].backgroundColor  = data.colors;
    chart.update();

    // Mettre à jour les métadonnées
    var rate    = entry ? entry.rate  : 0;
    var total   = entry ? entry.total : 0;
    var rateEl  = document.getElementById('pie_rate_'  + env);
    var totalEl = document.getElementById('pie_total_' + env);
    var dateEl  = document.getElementById('pie_date_'  + env);
    var linkEl  = document.getElementById('pie_link_'  + env);

    if (rateEl) {{
      rateEl.textContent = (entry ? rate + '%' : '—');
      rateEl.className   = 'rate-big ' + (rate > 5 ? 'pass' : 'fail');
    }}
    if (totalEl) {{ totalEl.textContent = (entry ? total + ' tests' : '— tests'); }}
    if (dateEl)  {{ dateEl.textContent  = (entry ? 'Rapport du ' + date : 'Aucune donnée pour cette date'); }}
    if (linkEl)  {{
      linkEl.href  = entry ? entry.report : '#';
      linkEl.style.opacity = entry ? '1' : '0.4';
      linkEl.style.pointerEvents = entry ? '' : 'none';
    }}

    // Légende personnalisée
    var legendEl = document.getElementById('legend_' + env);
    if (legendEl) {{
      var html = '';
      data.labels.forEach(function(label, i) {{
        html += '<div class="pie-legend-item"><div class="pie-legend-dot" style="background:'+data.colors[i]+'"></div>' + label + ' (' + data.values[i] + ')</div>';
      }});
      legendEl.innerHTML = html;
    }}
  }});
}}

// ── Sélecteur de date ─────────────────────────────────────────────────────────
var sel     = document.getElementById('dateSelect');
var btnPrev = document.getElementById('btnPrev');
var btnNext = document.getElementById('btnNext');

function updateNavButtons() {{
  var i = sel.selectedIndex;
  btnPrev.disabled = (i <= 0);
  btnNext.disabled = (i >= sel.options.length - 1);
}}

sel.addEventListener('change', function() {{
  updatePies(sel.value);
  updateNavButtons();
}});
btnPrev.addEventListener('click', function() {{
  if (sel.selectedIndex > 0) {{ sel.selectedIndex--; updatePies(sel.value); updateNavButtons(); }}
}});
btnNext.addEventListener('click', function() {{
  if (sel.selectedIndex < sel.options.length - 1) {{ sel.selectedIndex++; updatePies(sel.value); updateNavButtons(); }}
}});

// Initialiser avec la date sélectionnée
if (sel.value) {{ updatePies(sel.value); }}
updateNavButtons();

// ── Courbe d'évolution ────────────────────────────────────────────────────────
(function() {{
  var dates  = {chart_dates_js};
  var series = [
    {chart_series_js}
  ];
  if (dates.length === 0) return;
  var ctx = document.getElementById('lineChart').getContext('2d');
  var lineChart = new Chart(ctx, {{
    type: 'line',
    data: {{ labels: dates, datasets: series }},
    options: {{
      responsive: true,
      interaction: {{ intersect: false, mode: 'index' }},
      scales: {{
        y: {{
          min: 0, max: 100,
          title: {{ display: true, text: 'Taux de réussite (%)', color: '#6b778c' }},
          ticks: {{ callback: function(v) {{ return v + '%'; }} }},
          grid: {{ color: '#f0f0f0' }},
        }},
        x: {{ grid: {{ color: '#f0f0f0' }}, ticks: {{ maxRotation: 45, minRotation: 30 }} }}
      }},
      plugins: {{
        legend: {{ position: 'top' }},
        tooltip: {{
          callbacks: {{
            label: function(ctx) {{
              return ' ' + ctx.dataset.label + ' : ' + (ctx.parsed.y !== null ? ctx.parsed.y + '%' : '—');
            }}
          }}
        }}
      }}
    }}
  }});
  // Clic sur un point de la courbe → changer la date sélectionnée
  document.getElementById('lineChart').addEventListener('click', function(e) {{
    var pts = lineChart.getElementsAtEventForMode(e, 'nearest', {{intersect: false}}, true);
    if (pts.length) {{
      var dateClicked = dates[pts[0].index];
      if (dateClicked) {{
        for (var i = 0; i < sel.options.length; i++) {{
          if (sel.options[i].value === dateClicked) {{
            sel.selectedIndex = i;
            updatePies(dateClicked);
            updateNavButtons();
            break;
          }}
        }}
      }}
    }}
  }});
}})();
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Génère la page d'accueil XRAY")
    parser.add_argument("--output", default=os.path.join(SCRIPT_DIR, "accueil.html"),
                        help="Chemin du fichier HTML à générer")
    parser.add_argument("--envs", nargs="+", default=DEFAULT_ENVS,
                        help="Liste des environnements à inclure")
    args = parser.parse_args()

    history = load_history()
    if not history:
        print("[WARN] stats_history.json vide ou absent — la page d'accueil sera générée avec des données vides.",
              file=sys.stderr)

    html = build_html(history, args.envs)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[ACCUEIL] Page d'accueil générée : {args.output}")


if __name__ == "__main__":
    main()
