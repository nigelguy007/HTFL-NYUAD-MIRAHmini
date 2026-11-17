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
SYNC_KNOWLEDGE_ID_FILE = RUN_DIR / "sync-knowledge-id"
API_KEY_FILE = RUN_DIR / "api-key"

# Two knowledge bases, because a sync makes its target an exact mirror of the
# sources and deletes everything else in it. Hand-uploaded documents live in
# the first; ./privatellm sync only ever touches the second.
KNOWLEDGE_NAME = "Company Knowledge"
KNOWLEDGE_DESCRIPTION = "Documents uploaded by hand. Never changed by sync."
SYNC_KNOWLEDGE_NAME = "Synced Sources"
SYNC_KNOWLEDGE_DESCRIPTION = "Filled by ./privatellm sync. Do not upload here: sync deletes anything not in the sources."
ASSISTANT_ID = "assistant"
# The name people see in the chat. Set ASSISTANT_NAME in branding/brand.env.
ASSISTANT_NAME = os.environ.get("ASSISTANT_NAME") or "Assistant"
REQUEST_TIMEOUT_SECONDS = 60
# The server is on this machine: never route these calls through a system proxy.
LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
EVERYONE_CAN_READ = [{"principal_type": "user", "principal_id": "*", "permission": "read"}]

# Access levels. Everyone approved reads the open libraries; the two libraries
# below are only searched for members of the named groups. The admin puts
# people in groups with ./privatellm access.
FACILITATORS, LEADS, CONTRIBUTORS = "Facilitators", "Lab leads", "Contributors"
GROUPS: dict[str, tuple[str, dict[str, Any] | None]] = {
    FACILITATORS: ("May read the Facilitator Library.", None),
    LEADS: ("May read the Facilitator Library and the Lab Lead Library.", None),
    # Contributors need the Knowledge page to upload into Submissions.
    CONTRIBUTORS: ("May submit documents for a curator to approve.", {"workspace": {"knowledge": True}}),
}
# level -> (id file, name, description, groups that may read it; None means everyone)
LEVELS: dict[str, tuple[Path, str, str, tuple[str, ...] | None]] = {
    "open": (KNOWLEDGE_ID_FILE, KNOWLEDGE_NAME, KNOWLEDGE_DESCRIPTION, None),
    "facilitators": (
        RUN_DIR / "facilitators-knowledge-id",
        "Facilitator Library",
        "Only facilitators and Lab leads get answers from these documents.",
        (FACILITATORS, LEADS),
    ),
    "leads": (
        RUN_DIR / "leads-knowledge-id",
        "Lab Lead Library",
        "Only Lab leads get answers from these documents.",
        (LEADS,),
    ),
}
# Documents waiting for a curator. MIRAH never answers from this one.
SUBMISSIONS_ID_FILE = RUN_DIR / "submissions-knowledge-id"
SUBMISSIONS_NAME = "Submissions"
SUBMISSIONS_DESCRIPTION = "Upload here. A curator approves each document before MIRAH can use it."
GATE_ID = "mirah_gate"
GATE_FILE = ROOT / "functions" / "mirah_gate.py"

SYSTEM_PROMPT = """You are the private assistant for this team. You run entirely on the team's own computer.

When the message includes context taken from the team's documents:
- Answer from that context, and say which document each fact came from.
- If the context does not contain the answer, say so plainly. Do not guess and do not fill gaps from general knowledge.
- Quote figures, dates and names exactly as they appear.

For totals, counts or averages across a spreadsheet, say that you only see part of the rows and cannot calculate reliably.

For general questions that are not about the team's documents, answer normally and say the answer is from general knowledge.

Rules you must always keep:
- Label anything speculative, such as a possible future, as speculation.
- Never profile, diagnose or rank people, and never guess at anyone's health, beliefs, background or other sensitive traits.
- You cannot publish, send or act on anyone's behalf. Say so if asked.
- You support facilitators and the Lab lead. You do not replace their interpretation."""

# The Lab's three stages (docs/expectations/SCOPE.md, section 2), each offered
# as its own version of the assistant: id suffix, name suffix, extra instructions.
STAGES = [
    ("inspire", "Inspire",
     "This is the INSPIRE stage. Surface relevant provocations, methods and perspectives from the documents, "
     "with their sources. Offer contrasting viewpoints rather than one answer."),
    ("imagine", "Imagine",
     "This is the IMAGINE stage. Ask reflective and critical questions before giving answers. Link ideas across "
     "sessions and contributors, name recurring patterns and tensions, and sketch alternative futures, "
     "always labelled as speculation."),
    ("activate", "Activate",
     "This is the ACTIVATE stage. Turn the idea the person chooses into one structured next step: an action, "
     "a prototype outline, a recommendation, a collaboration or a question to investigate, grounded in the documents."),
]


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
            with LOCAL_OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
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
        if signin_error.status not in (400, 401):
            raise
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


def ensure_groups(api: Api) -> dict[str, str]:
    """Creates the access groups that are missing. Returns each group's id by name."""
    listed = api.request("GET", "/api/v1/groups/")
    existing = {group["name"]: group["id"] for group in (listed.get("items", []) if isinstance(listed, dict) else listed)}
    for name, (description, permissions) in GROUPS.items():
        if name in existing:
            continue
        form = {"name": name, "description": description, "permissions": permissions}
        existing[name] = api.request("POST", "/api/v1/groups/create", form)["id"]
        print(f"Created the group '{name}'.")
    return existing


def group_grants(group_ids: dict[str, str], names: tuple[str, ...], permissions: tuple[str, ...] = ("read",)) -> list[dict[str, str]]:
    return [
        {"principal_type": "group", "principal_id": group_ids[name], "permission": permission}
        for name in names
        for permission in permissions
    ]


def ensure_knowledge_base(
    api: Api, id_file: Path, name: str, description: str, grants: list[dict[str, str]] | None = None
) -> dict[str, Any]:
    """Returns the knowledge base whose id is saved in id_file, creating it if needed."""
    grants = EVERYONE_CAN_READ if grants is None else grants
    if id_file.exists():
        try:
            existing = api.request("GET", f"/api/v1/knowledge/{id_file.read_text().strip()}")
            print(f"Knowledge base '{existing['name']}' already exists.")
            return existing
        except ApiError as error:
            if error.status != 404:
                raise
    created = api.request(
        "POST",
        "/api/v1/knowledge/create",
        {"name": name, "description": description, "access_grants": grants},
    )
    id_file.write_text(created["id"] + "\n")
    print(f"Created knowledge base '{name}'.")
    return created


def save_model(api: Api, form: dict[str, Any]) -> bool:
    """Creates the model entry, or updates it if it exists. Returns True if created."""
    try:
        api.request("POST", "/api/v1/models/create", form)
        return True
    except ApiError as error:
        # Open WebUI 0.13 reports a taken model id as 401, so go by the message.
        if "already registered" not in error.detail:
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


def thinking_params() -> dict[str, Any]:
    """How much the model reasons silently before it answers (MODEL_THINK).

    Reasoning can double the wait and adds little when the answer is in the
    documents, so it is off where the model allows. "none" sends nothing, for
    models with no such step; gpt-oss cannot switch it off, only lower it.
    """
    setting = (os.environ.get("MODEL_THINK") or "false").strip().lower()
    if setting == "none":
        return {}
    return {"think": False if setting == "false" else setting}


def ensure_assistant(
    api: Api,
    knowledge_bases: list[dict[str, Any]],
    chat_model: str,
    model_id: str = ASSISTANT_ID,
    name: str = ASSISTANT_NAME,
    extra_prompt: str = "",
) -> None:
    share_base_model(api, chat_model)
    form = {
        "id": model_id,
        "name": name,
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
                for knowledge in knowledge_bases
            ],
        },
        "params": {"system": SYSTEM_PROMPT + extra_prompt, "function_calling": "legacy", **thinking_params()},
        "access_grants": EVERYONE_CAN_READ,
        "is_active": True,
    }
    if save_model(api, form):
        print(f"Created the '{name}' model on top of {chat_model}.")
    else:
        print(f"Updated the '{name}' model (now on {chat_model}).")


def ensure_gate(api: Api) -> None:
    """Installs the consent filter and switches it on for every model."""
    form = {
        "id": GATE_ID,
        "name": "MIRAH consent gate",
        "content": GATE_FILE.read_text(encoding="utf-8"),
        "meta": {"description": "Asks for consent before the first question and records it."},
    }
    try:
        api.request("POST", "/api/v1/functions/create", form)
        print("Installed the consent gate.")
    except ApiError as error:
        if error.status != 400:
            raise
        api.request("POST", f"/api/v1/functions/id/{GATE_ID}/update", form)
        print("Updated the consent gate.")
    state = api.request("GET", f"/api/v1/functions/id/{GATE_ID}")
    if not state.get("is_active"):
        api.request("POST", f"/api/v1/functions/id/{GATE_ID}/toggle")
    if not state.get("is_global"):
        api.request("POST", f"/api/v1/functions/id/{GATE_ID}/toggle/global")


def ensure_api_key(api: Api) -> None:
    if API_KEY_FILE.exists() and API_KEY_FILE.stat().st_size > 0:
        print("Sync API key already saved.")
        return
    key = api.request("POST", "/api/v1/auths/api_key")["api_key"]
    descriptor = os.open(API_KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(key + "\n")
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
    group_ids = ensure_groups(api)
    # One MIRAH for everyone: the chat software leaves out, per person, any
    # attached library that person has no right to read.
    libraries = [
        ensure_knowledge_base(
            api, id_file, level_name, description, None if readers is None else group_grants(group_ids, readers)
        )
        for id_file, level_name, description, readers in LEVELS.values()
    ]
    libraries.append(
        ensure_knowledge_base(api, SYNC_KNOWLEDGE_ID_FILE, SYNC_KNOWLEDGE_NAME, SYNC_KNOWLEDGE_DESCRIPTION)
    )
    ensure_knowledge_base(
        api,
        SUBMISSIONS_ID_FILE,
        SUBMISSIONS_NAME,
        SUBMISSIONS_DESCRIPTION,
        group_grants(group_ids, (CONTRIBUTORS,), ("read", "write")),
    )
    ensure_gate(api)
    ensure_assistant(api, libraries, chat_model)
    for suffix, label, instructions in STAGES:
        ensure_assistant(
            api,
            libraries,
            chat_model,
            model_id=f"{ASSISTANT_ID}-{suffix}",
            name=f"{ASSISTANT_NAME} · {label}",
            extra_prompt="\n\n" + instructions,
        )
    ensure_api_key(api)

    print(f"\nDone. Open the address shown by ./privatellm status, log in, and pick '{ASSISTANT_NAME}'.")
    print(f"Upload documents by hand into '{KNOWLEDGE_NAME}'.")
    print(f"To pull from folders, websites or drives into '{SYNC_KNOWLEDGE_NAME}':")
    print("  copy sync/sources.example.yaml to sync/sources.yaml, edit it, run ./privatellm sync.")


if __name__ == "__main__":
    try:
        main()
    except ApiError as error:
        sys.exit(f"The assistant refused a request: {error}")
    except KeyboardInterrupt:
        sys.exit(130)
