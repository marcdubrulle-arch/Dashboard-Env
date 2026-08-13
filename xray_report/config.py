import os


def _load_local_env() -> None:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue

            value = value.strip()
            if len(value) >= 2 and ((value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'")):
                value = value[1:-1]
            os.environ[key] = value


_load_local_env()

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "https://portail.agir.orange.com")
JIRA_TOKEN = os.getenv("JIRA_TOKEN", "VOTRE_TOKEN_ICI")
DEFAULT_ENVIRONMENT = os.getenv("XRAY_ENV", "XITG")
DEFAULT_PROJECTS = ["OAGRCLI", "OAGDIGI"]

CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL", "https://espace.agir.orange.com")
CONFLUENCE_PAGE_ID = os.getenv("CONFLUENCE_PAGE_ID", "3168392364")
CONFLUENCE_SPACE = os.getenv("CONFLUENCE_SPACE", "OAGTMA")
CONFLUENCE_TOKEN = os.getenv("CONFLUENCE_TOKEN", "")

DYNATRACE_BASE_URL = os.getenv("DYNATRACE_BASE_URL", "").rstrip("/")
DYNATRACE_TOKEN = os.getenv("DYNATRACE_TOKEN", "")
DYNATRACE_TAG_DEFAULT = os.getenv("DYNATRACE_TAG_DEFAULT", "")

PROXY_USER = os.getenv("PROXY_USER", "")
PROXY_PASS = os.getenv("PROXY_PASS", "")
PROXY_HOST = os.getenv("PROXY_HOST", "")
JIRA_PROXY = os.getenv("JIRA_PROXY", "")
