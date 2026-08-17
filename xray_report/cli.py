import argparse
import os
import sys
from datetime import date, timedelta

from rich.console import Console

from xray_report.apis import (
    fetch_all_test_plans,
    fetch_dynatrace_open_problems_by_env,
    fetch_last_execution_with_tests,
    fetch_open_jira_issues_by_env,
    fetch_test_keys_from_jql,
    fetch_test_executions,
    fetch_test_plan,
    fetch_test_runs,
    get_session,
    resolve_dynatrace_tag,
)
from xray_report.config import DEFAULT_ENVIRONMENT, DEFAULT_PROJECTS, DEFAULT_TESTS_FILTER_JQL, JIRA_BASE_URL, JIRA_TOKEN
from xray_report.confluence_publish import publish_to_confluence, publish_to_confluence_child
from xray_report.history import save_report_stats
from xray_report.report_html import build_html


def main():
    parser = argparse.ArgumentParser(description="Rapport XRAY HTML multi-projets")
    parser.add_argument("--date", default=None, help="Date YYYY-MM-DD")
    parser.add_argument("--projects", nargs="+", default=DEFAULT_PROJECTS, help="Clés projets")
    parser.add_argument("--testplan", default=None, help="Clé du Test Plan (ex: OAGRCLI-123)")
    parser.add_argument("--output", default="rapport_xray.html", help="Fichier HTML de sortie")
    parser.add_argument("--env", default=None, help="Environnement XRAY (ex: XITG, XITD, XITR)")
    parser.add_argument(
        "--tests-filter-jql",
        default=DEFAULT_TESTS_FILTER_JQL,
        help="JQL de scope des tests suivis (ex: issue in testSetTests('OAGRCLI-123')). Laisser vide pour désactiver.",
    )
    parser.add_argument("--confluence", action="store_true", default=False, help="Publier le rapport sur Confluence")
    parser.add_argument("--confluence-page-title", default=None, help="Titre de la page Confluence à créer/mettre à jour")
    parser.add_argument("--confluence-parent-id", default="468779106", help="ID de la page parent Confluence (défaut: 468779106)")
    parser.add_argument(
        "--ignore-confluence-errors",
        action="store_true",
        default=False,
        help="Ne pas échouer si la publication Confluence échoue",
    )
    args = parser.parse_args()

    target_date = date.today() - timedelta(days=1)
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

    environment = args.env.upper() if args.env else DEFAULT_ENVIRONMENT
    session = get_session()
    console.print(f"\n[bold]Rapport XRAY · {environment} · {target_date.isoformat()}[/bold]\n")

    allowed_test_keys: set[str] | None = None
    if args.tests_filter_jql.strip():
        console.print("[dim]Récupération du scope de tests via filtre JQL …[/dim]")
        try:
            allowed_test_keys = fetch_test_keys_from_jql(args.tests_filter_jql)
            console.print(f"[dim]  {len(allowed_test_keys)} test(s) dans le scope[/dim]")
        except RuntimeError as e:
            console.print(f"[yellow]Filtre tests ignoré (erreur JQL): {e}[/yellow]")
            allowed_test_keys = None

    jira_open_issues = []
    jira_open_error = None
    console.print(f"[dim]Récupération des tickets Jira ouverts ({environment}) …[/dim]")
    try:
        jira_open_issues = fetch_open_jira_issues_by_env(environment)
        console.print(f"[dim]  {len(jira_open_issues)} ticket(s) ouvert(s) trouvé(s)[/dim]")
    except RuntimeError as e:
        jira_open_error = f"Erreur Jira: {e}"
        console.print(f"[yellow]{jira_open_error}[/yellow]")

    dynatrace_open_problems = []
    dynatrace_tag = resolve_dynatrace_tag(environment)
    dynatrace_error = None
    console.print(f"[dim]Récupération des problèmes Dynatrace ouverts ({environment}) …[/dim]")
    try:
        dynatrace_open_problems, dynatrace_tag = fetch_dynatrace_open_problems_by_env(environment)
        console.print(f"[dim]  {len(dynatrace_open_problems)} problème(s) ouvert(s) trouvé(s) [tag={dynatrace_tag}][/dim]")
    except RuntimeError as e:
        dynatrace_error = f"Erreur Dynatrace: {e}"
        console.print(f"[yellow]{dynatrace_error}[/yellow]")

    all_projects = []
    for pkey in args.projects:
        console.print(f"[dim]Récupération {pkey} …[/dim]")
        issues = fetch_test_executions(session, pkey, target_date, environment)
        executions_data = []
        for issue in issues:
            key = issue["key"]
            runs = fetch_test_runs(session, key)
            if allowed_test_keys is not None:
                runs = [run for run in runs if run.get("key") in allowed_test_keys]
            issue["_runs"] = runs
            if not runs:
                console.print(f"  [dim]{key} -> 0 test(s) — ignore[/dim]")
                continue
            executions_data.append(issue)
            console.print(f"  [dim]{key} -> {len(runs)} test(s)[/dim]")
        all_projects.append({"key": pkey, "executions": executions_data})

    all_plan_sections = []
    if args.testplan:
        console.print(f"\n[dim]Test Plan {args.testplan} …[/dim]")
        plan_info = fetch_test_plan(session, args.testplan)
        plan_fields = plan_info.get("fields", {})
        last_exec = fetch_last_execution_with_tests(session, args.testplan, console)
        all_plan_sections.append({"key": args.testplan, "summary": plan_fields.get("summary", "—"), "last_execution": last_exec})
    else:
        for pkey in args.projects:
            console.print(f"\n[dim]Récupération des Test Plans de {pkey} …[/dim]")
            plans = fetch_all_test_plans(session, pkey)
            console.print(f"[dim]  {len(plans)} Test Plan(s) trouvé(s) dans {pkey}[/dim]")
            for plan in plans:
                plan_key = plan["key"]
                plan_summary = plan.get("fields", {}).get("summary", "—")
                last_exec = fetch_last_execution_with_tests(session, plan_key, console)
                if last_exec and allowed_test_keys is not None:
                    plan_runs = last_exec.get("_runs", [])
                    last_exec["_runs"] = [run for run in plan_runs if run.get("key") in allowed_test_keys]
                if last_exec and last_exec.get("_runs"):
                    all_plan_sections.append({"key": plan_key, "summary": plan_summary, "last_execution": last_exec})

    html = build_html(
        all_projects,
        all_plan_sections,
        target_date,
        environment,
        JIRA_BASE_URL,
        jira_open_issues,
        dynatrace_open_problems,
        jira_open_error=jira_open_error,
        dynatrace_error=dynatrace_error,
        dynatrace_tag=dynatrace_tag,
    )
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)

    console.print(f"\n[bold green]Rapport généré : {args.output}[/bold green]")
    console.print("[dim]Ouvrez-le dans votre navigateur ou partagez-le par email.[/dim]\n")

    stats_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stats_history.json")
    save_report_stats(all_projects, target_date, environment, args.output, os.path.abspath(stats_file), console)

    if args.confluence:
        if args.confluence_page_title:
            publish_to_confluence_child(
                html,
                args.confluence_page_title,
                args.confluence_parent_id,
                console,
                fail_on_error=not args.ignore_confluence_errors,
            )
        else:
            publish_to_confluence(html, target_date, console)
