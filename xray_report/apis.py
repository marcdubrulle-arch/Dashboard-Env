import json as _json
import os
import subprocess
from datetime import date

from rich.console import Console

from xray_report.config import (
    DYNATRACE_BASE_URL,
    DYNATRACE_TAG_DEFAULT,
    DYNATRACE_TOKEN,
    JIRA_BASE_URL,
    JIRA_PROXY,
    JIRA_TOKEN,
    PROXY_HOST,
    PROXY_PASS,
    PROXY_USER,
)

PROXY = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}" if PROXY_USER else JIRA_PROXY


def build_proxy_args() -> list[str]:
    if PROXY_HOST:
        return ["--proxy", f"http://{PROXY_HOST}", "--proxy-negotiate", "-U", ":"]
    return []


def resolve_dynatrace_tag(environment: str) -> str:
    env_upper = environment.upper()
    specific_tag = os.getenv(f"DYNATRACE_TAG_{env_upper}", "").strip()
    if specific_tag:
        return specific_tag
    if "{env}" in DYNATRACE_TAG_DEFAULT:
        return DYNATRACE_TAG_DEFAULT.format(env=env_upper).strip()
    if DYNATRACE_TAG_DEFAULT.strip():
        return DYNATRACE_TAG_DEFAULT.strip()
    return env_upper


def curl_json(method: str, url: str, params: dict = None, headers: list[str] | None = None) -> dict:
    if params:
        from urllib.parse import urlencode

        url = f"{url}?{urlencode(params)}"

    cmd = ["curl", "-s", "-k", *build_proxy_args(), "-X", method.upper()]
    for header in (headers or []):
        cmd += ["-H", header]
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"curl erreur (code {result.returncode}): {result.stderr[:300]}")
    if not result.stdout.strip():
        raise RuntimeError(f"curl vide (code {result.returncode}): {result.stderr[:200]}")
    try:
        return _json.loads(result.stdout)
    except _json.JSONDecodeError:
        raise RuntimeError(f"Réponse non-JSON: {result.stdout[:300]}")


def curl_get_jira(url: str, params: dict = None) -> dict:
    return curl_json(
        "GET",
        url,
        params=params,
        headers=[
            f"Authorization: Bearer {JIRA_TOKEN}",
            "Content-Type: application/json",
            "Accept: application/json",
        ],
    )


def get_session():
    return None


def fetch_test_executions(session, project_key: str, target_date: date, environment: str) -> list:
    jql = (
        f'project = {project_key} AND issuetype = "Test Execution"'
        f' AND "Test Environments" = "{environment}"'
        f' AND ('
        f' (created >= "{target_date.isoformat()}" AND created <= "{target_date.isoformat()} 23:59")'
        f' OR '
        f' (updated >= "{target_date.isoformat()}" AND updated <= "{target_date.isoformat()} 23:59")'
        f' )'
        f' ORDER BY updated DESC'
    )
    data = curl_get_jira(
        f"{JIRA_BASE_URL}/rest/api/2/search",
        params={"jql": jql, "maxResults": 100, "fields": "summary,status,created,environment,assignee,labels"},
    )
    return data.get("issues", [])


def fetch_test_plan(session, plan_key: str) -> dict:
    return curl_get_jira(f"{JIRA_BASE_URL}/rest/api/2/issue/{plan_key}", params={"fields": "summary,status,created,assignee"})


def fetch_test_plan_executions(session, plan_key: str) -> list:
    try:
        return curl_get_jira(
            f"{JIRA_BASE_URL}/rest/raven/1.0/api/testplan/{plan_key}/testexecution",
            params={"limit": 100},
        )
    except Exception:
        return []


def fetch_all_test_plans(session, project_key: str) -> list:
    jql = f'project = {project_key} AND issuetype = "Test Plan" ORDER BY created DESC'
    data = curl_get_jira(
        f"{JIRA_BASE_URL}/rest/api/2/search",
        params={"jql": jql, "maxResults": 200, "fields": "summary,status,created,assignee"},
    )
    return data.get("issues", [])


def fetch_test_runs(session, execution_key: str) -> list:
    try:
        return curl_get_jira(
            f"{JIRA_BASE_URL}/rest/raven/1.0/api/testexec/{execution_key}/test",
            params={"detailed": "true"},
        )
    except Exception:
        return []


def fetch_last_execution_with_tests(session, plan_key: str, console: Console) -> dict | None:
    executions = fetch_test_plan_executions(session, plan_key)
    if not executions:
        return None

    executions_sorted = sorted(executions, key=lambda x: x.get("key", ""), reverse=True)
    for exec_info in executions_sorted:
        exec_key = exec_info.get("key")
        runs = fetch_test_runs(session, exec_key)
        if runs:
            console.print(f"  [dim]{plan_key} → {exec_key} ({len(runs)} tests)[/dim]")
            exec_info["_runs"] = runs
            exec_info["_plan_key"] = plan_key
            return exec_info
        console.print(f"  [dim]{exec_key} ignorée (0 test)[/dim]")

    console.print(f"  [yellow]{plan_key} : aucune exécution avec des tests trouvée.[/yellow]")
    return None


def fetch_open_jira_issues_by_env(target_env: str) -> list:
    jql = (
        'project in projectMatch("OAG*")'
        ' AND issuetype in (Bug, Incident)'
        f' AND cf[11301] in ("{target_env}")'
        ' AND statusCategory in ("In Progress", "To Do")'
        ' ORDER BY updated DESC'
    )
    data = curl_get_jira(
        f"{JIRA_BASE_URL}/rest/api/2/search",
        params={"jql": jql, "maxResults": 100, "fields": "summary,status,priority,assignee,updated"},
    )
    return data.get("issues", [])


def fetch_dynatrace_open_problems_by_env(target_env: str) -> tuple[list, str]:
    if not DYNATRACE_BASE_URL:
        raise RuntimeError("DYNATRACE_BASE_URL non configuré.")
    if not DYNATRACE_TOKEN:
        raise RuntimeError("DYNATRACE_TOKEN non configuré.")

    env_tag = resolve_dynatrace_tag(target_env)
    if not env_tag:
        raise RuntimeError(f"Aucun tag Dynatrace trouvé pour l'environnement {target_env}.")

    selector = f'status("OPEN"),tag("{env_tag}")'
    data = curl_json(
        "GET",
        f"{DYNATRACE_BASE_URL}/api/v2/problems",
        params={"problemSelector": selector, "pageSize": 100},
        headers=[f"Authorization: Api-Token {DYNATRACE_TOKEN}", "Accept: application/json"],
    )
    return data.get("problems", []), env_tag
