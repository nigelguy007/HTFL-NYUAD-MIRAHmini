"""First-time configuration of the running assistant.

Creates the admin login (or signs in to it), a shared knowledge base, an
"Assistant" model that answers from that knowledge base, and an API key that
./privatellm sync uses to load documents. Safe to run again.
"""

from __future__ import annotations

import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = ROOT / "run"
KNOWLEDGE_ID_FILE = RUN_DIR / "knowledge-id"
API_KEY_FILE = RUN_DIR / "api-key"

KNOWLEDGE_NAME = "Company Knowledge"
ASSISTANT_ID = "assistant"
ASSISTANT_NAME = "Assistant"
REQUEST_TIMEOUT_SECONDS = 60
EVERYONE_CAN_READ = [{"principal_type": "user", "principal_id": "*", "permission": "read"}]

SYSTEM_PROMPT = """You are the private assistant for this team. You run entirely on the team's own computer.

When the message includes context taken from the team's documents:
- Answer from that context, and say which document each fact came from.
- If the context does not contain the answer, say so plainly. Do not guess and do not fill gaps from general knowledge.
- Quote figures, dates and names exactly as they appear.

For totals, counts or averages across a spreadsheet, say that you only see part of the rows and cannot calculate reliably.

For general questions that are not about the team's documents, answer normally and say the answer is from general knowledge."""


class ApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


class Api:
    def __init__(self, base_url: str, token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            raise ApiError(error.code, error.read().decode(errors="replace")) from error
        except urllib.error.URLError as error:
            raise SystemExit(f"Cannot reach {self.base_url}. Is it running? Try ./privatellm start ({error.reason})")


def read_credentials() -> tuple[str, str, str]:
    """Admin name, email and password, from the environment or typed in."""
    name = os.environ.get("ADMIN_NAME") or input("Your name: ").strip()
    email = os.environ.get("ADMIN_EMAIL") or input("Admin email (used to log in): ").strip()
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
    if not (name and email and password):
        raise SystemExit("Name, email and password are all required.")
    return name, email.lower(), password


def sign_in_or_create_admin(api: Api, name: str, email: str, password: str) -> str:
    """Returns a session token. The first account created becomes the admin."""
    try:
        result = api.request("POST", "/api/v1/auths/signin", {"email": email, "password": password})
        print(f"Signed in as {email}.")
    except ApiError as signin_error:
        try:
            result = api.request("POST", "/api/v1/auths/signup", {"name": name, "email": email, "password": password})
        except ApiError as signup_error:
            raise SystemExit(
                f"Could not sign in ({signin_error.detail}) or create the account ({signup_error.detail})."
            ) from signup_error
        print(f"Created account {email}.")
    if result.get("role") != "admin":
        raise SystemExit(f"{email} is not an admin. Run this with the admin account.")
    return result["token"]


def ensure_knowledge_base(api: Api) -> dict[str, Any]:
    if KNOWLEDGE_ID_FILE.exists():
        try:
            existing = api.request("GET", f"/api/v1/knowledge/{KNOWLEDGE_ID_FILE.read_text().strip()}")
            print(f"Knowledge base '{existing['name']}' already exists.")
            return existing
        except ApiError as error:
            if error.status not in (401, 404):
                raise
    created = api.request(
        "POST",
        "/api/v1/knowledge/create",
        {
            "name": KNOWLEDGE_NAME,
            "description": "Documents the whole team can ask about.",
            "access_grants": EVERYONE_CAN_READ,
        },
    )
    KNOWLEDGE_ID_FILE.write_text(created["id"] + "\n")
    print(f"Created knowledge base '{KNOWLEDGE_NAME}'.")
    return created


def save_model(api: Api, form: dict[str, Any]) -> bool:
    """Creates the model entry, or updates it if it exists. Returns True if created."""
    try:
        api.request("POST", "/api/v1/models/create", form)
        return True
    except ApiError as error:
        if error.status not in (400, 401, 409):
            raise
        api.request("POST", "/api/v1/models/model/update", form)
        return False


def share_base_model(api: Api, chat_model: str) -> None:
    """Lets non-admin users reach the underlying model through the Assistant.

    Open WebUI refuses a shared model whose base model is not itself shared.
    The base model is hidden from the picker so people only see 'Assistant'.
    """
    save_model(
        api,
        {
            "id": chat_model,
            "name": chat_model,
            "base_model_id": None,
            "meta": {"description": "Underlying model. Use 'Assistant' instead.", "hidden": True},
            "params": {},
            "access_grants": EVERYONE_CAN_READ,
            "is_active": True,
        },
    )


def ensure_assistant(api: Api, knowledge: dict[str, Any], chat_model: str) -> None:
    share_base_model(api, chat_model)
    form = {
        "id": ASSISTANT_ID,
        "name": ASSISTANT_NAME,
        "base_model_id": chat_model,
        "meta": {
            "description": "Answers from the team's documents. Runs on this computer only.",
            "knowledge": [
                {
                    "id": knowledge["id"],
                    "name": knowledge["name"],
                    "description": knowledge.get("description", ""),
                    "type": "collection",
                }
            ],
        },
        "params": {"system": SYSTEM_PROMPT, "function_calling": "legacy"},
        "access_grants": EVERYONE_CAN_READ,
        "is_active": True,
    }
    if save_model(api, form):
        print(f"Created the '{ASSISTANT_NAME}' model on top of {chat_model}.")
    else:
        print(f"Updated the '{ASSISTANT_NAME}' model (now on {chat_model}).")


def ensure_api_key(api: Api) -> None:
    if API_KEY_FILE.exists():
        print("Sync API key already saved.")
        return
    key = api.request("POST", "/api/v1/auths/api_key")["api_key"]
    API_KEY_FILE.touch(mode=0o600)
    API_KEY_FILE.write_text(key + "\n")
    print("Saved an API key for ./privatellm sync.")


def main() -> None:
    base_url = os.environ.get("WEBUI_URL", "http://127.0.0.1:8080")
    chat_model = os.environ.get("CHAT_MODEL")
    if not chat_model:
        raise SystemExit("CHAT_MODEL is not set. Run this through ./privatellm configure.")
    RUN_DIR.mkdir(exist_ok=True)

    name, email, password = read_credentials()
    api = Api(base_url)
    api.token = sign_in_or_create_admin(api, name, email, password)
    knowledge = ensure_knowledge_base(api)
    ensure_assistant(api, knowledge, chat_model)
    ensure_api_key(api)

    print("\nDone. Open the address shown by ./privatellm status, log in, and pick 'Assistant'.")
    print("To load documents: copy sync/sources.example.yaml to sync/sources.yaml, edit it, run ./privatellm sync.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
