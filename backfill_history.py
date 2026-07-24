"""
backfill_history.py
-------------------
Parse les rapports HTML existants (rapport_{ENV}_{DATE}.html) et alimente
stats_history.json avec les données extraites.

Usage :
    py backfill_history.py
"""

import json
import os
import re
import sys
from datetime import datetime

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
STATS_FILE  = os.path.join(SCRIPT_DIR, "stats_history.json")


def parse_report(filepath: str) -> dict | None:
    """Extrait les stats d'un rapport HTML. Retourne None si non parseable."""
    filename = os.path.basename(filepath)

    # Nom du fichier : rapport_{ENV}_{YYYY-MM-DD}.html
    m = re.match(r"rapport_([A-Z0-9]+)_(\d{4}-\d{2}-\d{2})\.html", filename)
    if not m:
        return None
    env      = m.group(1)
    date_str = m.group(2)

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        print(f"  [WARN] Impossible de lire {filename} : {e}")
        return None

    def extract_kpi(label_pattern: str) -> int:
        """Cherche <div class="val ...">N</div> suivi du label donné."""
        pat = r'<div class="val[^"]*">(\d+)(?:%)?</div>\s*<div class="lbl">[^<]*' + label_pattern
        m2 = re.search(pat, content, re.IGNORECASE)
        return int(m2.group(1)) if m2 else 0

    total      = extract_kpi("Tests total")
    pass_      = extract_kpi("Pass")
    fail       = extract_kpi("Fail")
    executing  = extract_kpi("En cours")
    todo       = extract_kpi("Todo")
    rate       = round(pass_ / total * 100) if total > 0 else 0

    # Date de génération depuis le header HTML
    gm = re.search(r"Généré le (\d{2}/\d{2}/\d{4} à \d{2}:\d{2})", content)
    generated = ""
    if gm:
        try:
            generated = datetime.strptime(gm.group(1), "%d/%m/%Y à %H:%M").isoformat(timespec="seconds")
        except Exception:
            pass

    return {
        "date":       date_str,
        "env":        env,
        "report":     filename,
        "total":      total,
        "pass":       pass_,
        "fail":       fail,
        "executing":  executing,
        "todo":       todo,
        "aborted":    0,
        "rate":       rate,
        "generated":  generated,
    }


def main():
    # Charger l'historique existant
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        history = []

    existing_keys = {(e.get("date"), e.get("env")) for e in history}

    # Chercher tous les rapports datés
    added = 0
    for fname in sorted(os.listdir(SCRIPT_DIR)):
        if not re.match(r"rapport_[A-Z0-9]+_\d{4}-\d{2}-\d{2}\.html", fname):
            continue
        fpath = os.path.join(SCRIPT_DIR, fname)
        entry = parse_report(fpath)
        if not entry:
            print(f"  [SKIP] {fname} — non parseable")
            continue
        key = (entry["date"], entry["env"])
        if key in existing_keys:
            print(f"  [SKIP] {fname} — déjà dans l'historique")
            continue
        history.append(entry)
        existing_keys.add(key)
        added += 1
        print(f"  [ADD]  {fname} → {entry['env']} {entry['date']} : "
              f"{entry['pass']}/{entry['total']} ({entry['rate']}%)")

    if added == 0:
        print("Aucune nouvelle entrée à ajouter.")
    else:
        history.sort(key=lambda e: (e.get("date", ""), e.get("env", "")))
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        print(f"\n{added} entrée(s) ajoutée(s) dans stats_history.json ({len(history)} total)")


if __name__ == "__main__":
    main()
