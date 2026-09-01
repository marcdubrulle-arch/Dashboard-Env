import json
import os
from datetime import datetime

from rich.console import Console

from xray_report.report_html import compute_stats


def load_history_file(stats_file: str) -> list:
    try:
        with open(stats_file, "r", encoding="utf-8") as sf:
            data = json.load(sf)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def write_history_file(history: list, stats_file: str) -> None:
    with open(stats_file, "w", encoding="utf-8") as sf:
        json.dump(history, sf, indent=2, ensure_ascii=False)


def save_report_stats(
    all_projects: list,
    target_date,
    environment: str,
    output_path: str,
    stats_file: str,
    console: Console,
    all_plan_sections: list | None = None,
):
    history = load_history_file(stats_file)

    grand = {"PASS": 0, "FAIL": 0, "EXECUTING": 0, "TODO": 0, "ABORTED": 0}
    if all_plan_sections is not None:
        for section in all_plan_sections:
            last_exec = section.get("last_execution")
            if not last_exec:
                continue
            stats = compute_stats(last_exec.get("_runs", []))
            for k in grand:
                grand[k] += stats.get(k, 0)
    else:
        for proj in all_projects:
            for ex in proj.get("executions", []):
                stats = compute_stats(ex.get("_runs", []))
                for k in grand:
                    grand[k] += stats.get(k, 0)
    total = sum(grand.values())
    rate = round(grand["PASS"] / total * 100) if total > 0 else 0

    date_str = target_date.isoformat()
    history = [e for e in history if not (e.get("date") == date_str and e.get("env") == environment)]
    history.append(
        {
            "date": date_str,
            "env": environment,
            "report": os.path.basename(output_path),
            "total": total,
            "pass": grand["PASS"],
            "fail": grand["FAIL"],
            "executing": grand["EXECUTING"],
            "todo": grand["TODO"],
            "aborted": grand["ABORTED"],
            "rate": rate,
            "generated": datetime.now().isoformat(timespec="seconds"),
        }
    )
    history.sort(key=lambda e: (e.get("date", ""), e.get("env", "")))
    try:
        write_history_file(history, stats_file)
        console.print("[dim]Statistiques sauvegardées dans stats_history.json[/dim]")
    except Exception as e:
        console.print(f"[yellow]Avertissement : impossible d'écrire stats_history.json : {e}[/yellow]")
