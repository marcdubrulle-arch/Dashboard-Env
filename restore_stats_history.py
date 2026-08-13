import argparse
import io
import json
import os
import urllib.error
import urllib.request
import zipfile
from datetime import datetime

from xray_report.history import write_history_file


def load_history_from_bytes(payload: bytes) -> list:
    data = json.loads(payload.decode("utf-8"))
    return data if isinstance(data, list) else []


def fetch_url(url: str, headers: dict | None = None) -> bytes:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def try_fetch_history_url(url: str) -> list | None:
    try:
        return load_history_from_bytes(fetch_url(url))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def try_fetch_artifact_history(repo: str, token: str, artifact_name: str) -> list | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        payload = fetch_url(
            f"https://api.github.com/repos/{repo}/actions/artifacts?name={artifact_name}&per_page=100",
            headers=headers,
        )
        response = json.loads(payload.decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None

    artifacts = response.get("artifacts", [])
    for artifact in artifacts:
        if artifact.get("expired"):
            continue
        download_url = artifact.get("archive_download_url")
        if not download_url:
            continue
        try:
            archive_bytes = fetch_url(download_url, headers=headers)
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                for name in archive.namelist():
                    if os.path.basename(name) == "stats_history.json":
                        return load_history_from_bytes(archive.read(name))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, zipfile.BadZipFile, KeyError, json.JSONDecodeError):
            continue
    return None


def parse_generated(value: str) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.min


def merge_histories(histories: list[tuple[str, list]]) -> tuple[list, list[str]]:
    merged: dict[tuple[str, str], dict] = {}
    used_sources: set[str] = set()

    for source_name, history in histories:
        for entry in history:
            if not isinstance(entry, dict):
                continue
            key = (entry.get("date", ""), entry.get("env", ""))
            if not key[0] or not key[1]:
                continue
            current = merged.get(key)
            if current is None or parse_generated(entry.get("generated", "")) >= parse_generated(current.get("generated", "")):
                merged[key] = entry
                used_sources.add(source_name)

    merged_history = sorted(merged.values(), key=lambda entry: (entry.get("date", ""), entry.get("env", "")))
    return merged_history, sorted(used_sources)


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore persisted XRAY stats history before report generation.")
    parser.add_argument("--output", default="stats_history.json", help="Path to the history file to write.")
    parser.add_argument("--repo", default="", help="GitHub repository in owner/name form.")
    parser.add_argument("--artifact-name", default="xray-stats-history", help="GitHub artifact name to inspect.")
    parser.add_argument("--pages-url", action="append", default=[], help="Published stats_history.json URL to try first.")
    args = parser.parse_args()

    histories: list[tuple[str, list]] = []
    if os.path.exists(args.output):
        try:
            with open(args.output, "r", encoding="utf-8") as existing_file:
                existing = json.load(existing_file)
            if isinstance(existing, list):
                histories.append(("local", existing))
        except Exception:
            pass

    for url in args.pages_url:
        history = try_fetch_history_url(url)
        if history is not None:
            histories.append((url, history))

    token = os.getenv("GITHUB_TOKEN", "")
    if args.repo and token:
        history = try_fetch_artifact_history(args.repo, token, args.artifact_name)
        if history is not None:
            histories.append(("artifact", history))

    merged_history, used_sources = merge_histories(histories)
    write_history_file(merged_history, args.output)

    sources_label = ", ".join(used_sources) if used_sources else "none"
    print(f"Restored {len(merged_history)} history entrie(s) from: {sources_label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
