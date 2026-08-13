import json as _json
import os
import subprocess
import sys
import time
from urllib.parse import quote as urlquote

from rich.console import Console

from xray_report.apis import build_proxy_args
from xray_report.config import (
    CONFLUENCE_BASE_URL,
    CONFLUENCE_PAGE_ID,
    CONFLUENCE_SPACE,
    CONFLUENCE_TOKEN,
    JIRA_TOKEN,
)


def _token() -> str:
    return CONFLUENCE_TOKEN or os.getenv("CONFLUENCE_TOKEN", "") or JIRA_TOKEN


def publish_to_confluence_child(
    html_content: str,
    page_title: str,
    parent_id: str,
    console: Console,
    fail_on_error: bool = True,
):
    token = _token()
    confluence_body = (
        '<ac:structured-macro ac:name="html"><ac:plain-text-body><![CDATA[' + html_content + "]]></ac:plain-text-body></ac:structured-macro>"
    )

    def _curl(method, url, payload=None, max_retries=4):
        cmd = [
            "curl",
            "-s",
            "-k",
            *build_proxy_args(),
            "-X",
            method,
            "-H",
            f"Authorization: Bearer {token}",
            "-H",
            "Content-Type: application/json",
            "-H",
            "Accept: application/json",
        ]
        if payload:
            cmd += ["-d", payload]
        cmd.append(url)
        for attempt in range(max_retries):
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            try:
                data = _json.loads(r.stdout)
            except _json.JSONDecodeError:
                raise RuntimeError(f"Réponse non-JSON : {r.stdout[:300]}")
            if isinstance(data, dict) and "Rate limit" in data.get("message", ""):
                wait = 10 * (2**attempt)
                console.print(f"[yellow]Rate limit Confluence — attente {wait}s (essai {attempt+1}/{max_retries})…[/yellow]")
                time.sleep(wait)
                continue
            return data
        raise RuntimeError("Rate limit Confluence : nombre max de tentatives atteint.")

    cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "confluence_page_ids.json")
    cache_file = os.path.abspath(cache_file)
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            page_cache = _json.load(f)
    except Exception:
        page_cache = {}

    def _save_page_cache(title, pid, ver):
        page_cache[title] = {"id": pid, "version": ver}
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                _json.dump(page_cache, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _do_put(pid, ver):
        payload = _json.dumps(
            {
                "id": pid,
                "type": "page",
                "title": page_title,
                "space": {"key": CONFLUENCE_SPACE},
                "body": {"storage": {"value": confluence_body, "representation": "storage"}},
                "version": {"number": ver},
            }
        )
        return _curl("PUT", f"{CONFLUENCE_BASE_URL}/rest/api/content/{pid}", payload)

    published = False
    cached = page_cache.get(page_title)
    if cached:
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
                page_data = _curl("GET", f"{CONFLUENCE_BASE_URL}/rest/api/content/{page_id}?expand=version")
                cur_ver = page_data["version"]["number"]
                resp2 = _do_put(page_id, cur_ver + 1)
                if resp2.get("id"):
                    link = f"{CONFLUENCE_BASE_URL}/spaces/{CONFLUENCE_SPACE}/pages/{page_id}"
                    console.print(f"[bold green]Page mise à jour : {link}[/bold green]")
                    print(f"[CONFLUENCE_URL] {link}")
                    _save_page_cache(page_title, page_id, cur_ver + 1)
                    published = True
        except Exception as e:
            console.print(f"[red]Erreur PUT (cache) : {e}[/red]")
    else:
        search_url = f"{CONFLUENCE_BASE_URL}/rest/api/content?spaceKey={CONFLUENCE_SPACE}&title={urlquote(page_title)}&expand=version"
        try:
            search_data = _curl("GET", search_url)
            results = search_data.get("results", [])
        except Exception as e:
            console.print(f"[red]Erreur recherche Confluence : {e}[/red]")
            if fail_on_error:
                sys.exit(1)
            return False
        time.sleep(2)
        if results:
            page_id = results[0]["id"]
            current_version = results[0]["version"]["number"]
            try:
                resp = _do_put(page_id, current_version + 1)
                if resp.get("id"):
                    link = f"{CONFLUENCE_BASE_URL}/spaces/{CONFLUENCE_SPACE}/pages/{page_id}"
                    console.print(f"[bold green]Page mise à jour : {link}[/bold green]")
                    print(f"[CONFLUENCE_URL] {link}")
                    _save_page_cache(page_title, page_id, current_version + 1)
                    published = True
            except Exception as e:
                console.print(f"[red]Erreur PUT : {e}[/red]")
        else:
            payload = _json.dumps(
                {
                    "type": "page",
                    "title": page_title,
                    "space": {"key": CONFLUENCE_SPACE},
                    "ancestors": [{"id": parent_id}],
                    "body": {"storage": {"value": confluence_body, "representation": "storage"}},
                }
            )
            try:
                resp = _curl("POST", f"{CONFLUENCE_BASE_URL}/rest/api/content", payload)
                if resp.get("id"):
                    new_id = resp["id"]
                    link = f"{CONFLUENCE_BASE_URL}/spaces/{CONFLUENCE_SPACE}/pages/{new_id}"
                    console.print(f"[bold green]Page créée : {link}[/bold green]")
                    print(f"[CONFLUENCE_URL] {link}")
                    _save_page_cache(page_title, new_id, 1)
                    published = True
            except Exception as e:
                console.print(f"[red]Erreur POST : {e}[/red]")

    if not published:
        console.print(f"[bold red]Publication Confluence échouée pour '{page_title}'.[/bold red]")
        if fail_on_error:
            sys.exit(1)
        return False
    return True


def publish_to_confluence(html_content: str, target_date, console):
    token = _token()
    console.print(f"[dim]Publication sur Confluence (page {CONFLUENCE_PAGE_ID}) …[/dim]")
    page_url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{CONFLUENCE_PAGE_ID}?expand=version,title"
    cmd_get = ["curl", "-s", "-k", *build_proxy_args(), "-H", f"Authorization: Bearer {token}", "-H", "Accept: application/json", page_url]
    result = subprocess.run(cmd_get, capture_output=True, text=True, encoding="utf-8", errors="replace")
    time.sleep(5)
    if not result.stdout.strip():
        console.print("[red]Impossible de récupérer la page Confluence.[/red]")
        return
    try:
        page_data = _json.loads(result.stdout)
    except _json.JSONDecodeError:
        console.print(f"[red]Réponse Confluence invalide : {result.stdout[:200]}[/red]")
        return

    current_version = page_data.get("version", {}).get("number", 1)
    page_title = page_data.get("title", f"Tests automatises {target_date}")
    confluence_body = (
        '<ac:structured-macro ac:name="html"><ac:plain-text-body><![CDATA[' + html_content + "]]></ac:plain-text-body></ac:structured-macro>"
    )
    payload = _json.dumps(
        {
            "id": CONFLUENCE_PAGE_ID,
            "type": "page",
            "title": page_title,
            "space": {"key": CONFLUENCE_SPACE},
            "body": {"storage": {"value": confluence_body, "representation": "storage"}},
            "version": {"number": current_version + 1},
        }
    )
    update_url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{CONFLUENCE_PAGE_ID}"
    cmd_put = [
        "curl",
        "-s",
        "-k",
        *build_proxy_args(),
        "-X",
        "PUT",
        "-H",
        f"Authorization: Bearer {token}",
        "-H",
        "Content-Type: application/json",
        "-H",
        "Accept: application/json",
        "-d",
        payload,
        update_url,
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
