"""Host commands for running MIRAH responsibly.

    access <email> <open|facilitators|leads>     who may read which library
    contributor <email> <yes|no>                 who may submit documents
    library pending|show|approve|reject|remove   the curator's approval queue
    export-user <email>                          everything held about one person
    delete-user <email>                          remove one person and their data
    audit                                        who did what, for the last year
    training list|approve|reject|build|run       examples from people who opted in

Run through ./privatellm, on the computer that hosts MIRAH.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sqlite3
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import configure
import mirah_store as store
from configure import Api, ApiError

ROOT = configure.ROOT
DATA_DIR = Path(os.environ.get("DATA_DIR") or ROOT / "data")
EXPORT_DIR = ROOT / "exports"
TRAINING_DIR = DATA_DIR / "training"
DEFAULT_MIN_EXAMPLES = 500   # the plan's threshold for a first adapter
VALIDATION_EVERY = 10        # one example in ten is held back to check the result
HOST = "host"                # the actor recorded for commands run on this computer
NOTICE_FILE = ROOT / "config" / "consent-notice.txt"
PAGE_LIMIT = 1000            # safety stop when reading a library page by page
PREVIEW_CHARACTERS = 3000    # how much of a submission `library show` prints
LEVEL_GROUP = {"open": None, "facilitators": configure.FACILITATORS, "leads": configure.LEADS}


def fail(message: str) -> None:
    raise SystemExit(message)


def connect_api() -> Api:
    if not configure.API_KEY_FILE.exists():
        fail("Run ./privatellm configure first.")
    return Api(os.environ.get("WEBUI_URL", "http://127.0.0.1:8080"), configure.API_KEY_FILE.read_text().strip())


def chat_database() -> sqlite3.Connection:
    """The chat software's own database, opened read-only."""
    connection = sqlite3.connect(f"file:{DATA_DIR / 'webui.db'}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def find_user(email: str) -> sqlite3.Row:
    with chat_database() as database:
        user = database.execute(
            "SELECT id, name, email, role, created_at FROM user WHERE lower(email) = ?", (email.lower(),)
        ).fetchone()
    if user is None:
        fail(f"No account uses {email}.")
    return user


def knowledge_id(id_file: Path) -> str:
    if not id_file.exists():
        fail("Run ./privatellm configure once more: it creates the libraries this command needs.")
    return id_file.read_text().strip()


def as_items(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, dict):
        return response.get("items") or response.get("files") or []
    return response or []


# --- Access levels -----------------------------------------------------------------

def set_group(api: Api, group_ids: dict[str, str], group: str, user_id: str, member: bool) -> None:
    action = "add" if member else "remove"
    api.request("POST", f"/api/v1/groups/id/{group_ids[group]}/users/{action}", {"user_ids": [user_id]})


def command_access(arguments: argparse.Namespace, records: sqlite3.Connection) -> None:
    api, user = connect_api(), find_user(arguments.email)
    group_ids = configure.ensure_groups(api)
    wanted = LEVEL_GROUP[arguments.level]
    for group in (configure.FACILITATORS, configure.LEADS):
        set_group(api, group_ids, group, user["id"], member=(group == wanted))
    store.log(records, HOST, "access.set", f"user {user['id']} -> {arguments.level}")
    print(f"{arguments.email} now has the '{arguments.level}' access level.")


def command_contributor(arguments: argparse.Namespace, records: sqlite3.Connection) -> None:
    api, user = connect_api(), find_user(arguments.email)
    member = arguments.answer == "yes"
    set_group(api, configure.ensure_groups(api), configure.CONTRIBUTORS, user["id"], member)
    store.log(records, HOST, "contributor.set", f"user {user['id']} -> {arguments.answer}")
    print(f"{arguments.email} {'may now' if member else 'may no longer'} submit documents for approval.")


# --- Curator approval ----------------------------------------------------------------

def library_files(api: Api, library_id: str) -> list[dict[str, Any]]:
    """Every file in a library. The chat software hands them out a page at a time."""
    found: list[dict[str, Any]] = []
    for page in range(1, PAGE_LIMIT + 1):
        batch = as_items(api.request("GET", f"/api/v1/knowledge/{library_id}/files?page={page}"))
        known = {entry["id"] for entry in found}
        fresh = [entry for entry in batch if entry["id"] not in known]
        if not fresh:
            break
        found.extend(fresh)
    return found


def download(api: Api, path: str) -> bytes:
    request = urllib.request.Request(api.base_url + path, headers={"Authorization": f"Bearer {api.token}"})
    with configure.LOCAL_OPENER.open(request, timeout=configure.REQUEST_TIMEOUT_SECONDS) as response:
        return response.read()


def upload_into(api: Api, library_id: str, name: str, content: bytes) -> str:
    """Stores a file owned by the admin and adds it to a library. Returns its id."""
    boundary = uuid.uuid4().hex
    safe_name = name.replace('"', "'").replace("\r", " ").replace("\n", " ")
    metadata = json.dumps({"knowledge_id": library_id})
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n{metadata}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    headers = {"Authorization": f"Bearer {api.token}", "Content-Type": f"multipart/form-data; boundary={boundary}"}
    request = urllib.request.Request(api.base_url + "/api/v1/files/", data=body, headers=headers, method="POST")
    with configure.LOCAL_OPENER.open(request, timeout=configure.REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read())["id"]


def file_name(entry: dict[str, Any]) -> str:
    return entry.get("filename") or (entry.get("meta") or {}).get("name") or entry.get("id", "?")


def take_out(api: Api, library_id: str, file_id: str, delete: bool) -> None:
    flag = "true" if delete else "false"
    api.request("POST", f"/api/v1/knowledge/{library_id}/file/remove?delete_file={flag}", {"file_id": file_id})


def need_file(arguments: argparse.Namespace) -> str:
    if not arguments.file:
        fail("Give the document's id, as shown by: ./privatellm library pending")
    return arguments.file


def need_name(arguments: argparse.Namespace) -> str:
    if not arguments.by:
        fail("Say who is deciding, for the record: --by 'Your Name'")
    return arguments.by


def command_library(arguments: argparse.Namespace, records: sqlite3.Connection) -> None:
    api = connect_api()
    submissions = knowledge_id(configure.SUBMISSIONS_ID_FILE)
    if arguments.action == "pending":
        waiting = library_files(api, submissions)
        if not waiting:
            print("Nothing is waiting for approval.")
        for entry in waiting:
            print(f"{entry['id']}  {file_name(entry)}")
        return
    file_id = need_file(arguments)
    if arguments.action == "show":
        text = api.request("GET", f"/api/v1/files/{file_id}/data/content").get("content") or ""
        print(text[:PREVIEW_CHARACTERS] or "(No readable text was found in this document.)")
        if len(text) > PREVIEW_CHARACTERS:
            print(f"\n... {len(text) - PREVIEW_CHARACTERS} more characters not shown.")
        return
    if arguments.action == "remove":
        for level, (id_file, name, _, _) in configure.LEVELS.items():
            library = knowledge_id(id_file)
            if any(entry["id"] == file_id for entry in library_files(api, library)):
                take_out(api, library, file_id, delete=True)
                store.log(records, need_name(arguments), "library.removed", f"file {file_id} from {level}")
                print(f"Removed from '{name}'. MIRAH no longer answers from it.")
                return
        fail("That document is not in any library.")
    waiting = [entry for entry in library_files(api, submissions) if entry["id"] == file_id]
    if not waiting:
        fail("That document is not waiting for approval. See: ./privatellm library pending")
    curator = need_name(arguments)
    if arguments.action == "reject":
        take_out(api, submissions, file_id, delete=True)
        store.log(records, curator, "library.rejected", f"file {file_id}")
        print("Rejected and deleted.")
        return
    id_file, name, _, _ = configure.LEVELS[arguments.level]
    # The approved copy belongs to the admin, so the person who submitted it
    # cannot change what was approved. Their own copy is deleted.
    content = download(api, f"/api/v1/files/{file_id}/content")
    approved_id = upload_into(api, knowledge_id(id_file), file_name(waiting[0]), content)
    take_out(api, submissions, file_id, delete=True)
    submitter = waiting[0].get("user_id", "unknown")
    store.log(records, curator, "library.approved", f"file {approved_id} into {arguments.level}, submitted by user {submitter}")
    print(f"Approved into '{name}' as {approved_id}. MIRAH can answer from it within a few seconds.")


# --- Export and deletion -------------------------------------------------------------

def rows(connection: sqlite3.Connection, query: str, user_id: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query, (user_id,)).fetchall()]


def tables_about_people(database: sqlite3.Connection) -> list[str]:
    """Every table in the chat software's database that files rows under a person."""
    names = [row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    return [name for name in names if any(column[1] == "user_id" for column in database.execute(f'PRAGMA table_info("{name}")'))]


def command_export(arguments: argparse.Namespace, records: sqlite3.Connection) -> None:
    user = find_user(arguments.email)
    with chat_database() as database:
        held = {table: rows(database, f'SELECT * FROM "{table}" WHERE user_id = ?', user["id"]) for table in tables_about_people(database)}
    chats = held.pop("chat", [])
    for chat in chats:
        if isinstance(chat.get("chat"), str):
            chat["chat"] = json.loads(chat["chat"])
    export = {
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "account": dict(user),
        "conversations": chats,
        "other_records": {table: found for table, found in held.items() if found},
        "consent": rows(records, "SELECT purpose, version, granted_at, withdrawn_at FROM consent WHERE user_id = ?", user["id"]),
        "training_examples": rows(records, "SELECT question, answer, status, created_at FROM example WHERE user_id = ?", user["id"]),
    }
    EXPORT_DIR.mkdir(mode=0o700, exist_ok=True)
    target = EXPORT_DIR / f"{user['id']}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(export, handle, indent=2, ensure_ascii=False, default=str)
    store.log(records, HOST, "user.exported", f"user {user['id']}")
    print(f"Wrote {len(chats)} conversation(s) and the rest of the record to {target}")
    print("Hand it to the person, then delete the file.")


def command_delete(arguments: argparse.Namespace, records: sqlite3.Connection) -> None:
    user = find_user(arguments.email)
    if user["role"] == "admin":
        fail("That is the admin account. It cannot be deleted from here.")
    if not arguments.yes:
        typed = input(f"Delete {arguments.email}, their conversations, uploads, consent records and training examples? Type DELETE: ")
        if typed.strip() != "DELETE":
            fail("Nothing was deleted.")
    api = connect_api()
    store.log(records, HOST, "user.delete.started", f"user {user['id']}")
    with chat_database() as database:
        file_ids = [row["id"] for row in database.execute("SELECT id FROM file WHERE user_id = ?", (user["id"],))]
        library_ids = [row["id"] for row in database.execute("SELECT id FROM knowledge WHERE user_id = ?", (user["id"],))]
    # Through the chat software first, so the search index is cleaned too.
    for library_id in library_ids:
        api.request("DELETE", f"/api/v1/knowledge/{library_id}/delete")
    for file_id in file_ids:
        api.request("DELETE", f"/api/v1/files/{file_id}")
    api.request("DELETE", f"/api/v1/users/{user['id']}")
    leftovers = purge_leftovers(user["id"])
    removed = store.delete_user(records, user["id"], DATA_DIR)
    store.log(records, HOST, "user.deleted", f"user {user['id']}")
    print(
        f"Deleted {arguments.email}: their conversations, {len(file_ids)} uploaded file(s), {leftovers} other record(s), "
        f"{removed['consent_records']} consent record(s) and {removed['training_examples']} training example(s)."
    )
    contributed = [
        entry["detail"].split()[1]
        for entry in store.audit_entries(records, limit=100000)
        if entry["action"] == "library.approved" and entry["detail"].endswith(f"submitted by user {user['id']}")
    ]
    if contributed:
        print(f"Documents they submitted that a curator approved are still in the library: {', '.join(contributed)}")
        print("Remove any of them with: ./privatellm library remove <id> --by 'Your Name'")
    print(f"Sign-in lines in {ROOT / 'logs'} and {DATA_DIR / 'audit.log'} still name the account. Delete those files if that matters.")


def purge_leftovers(user_id: str) -> int:
    """Deletes rows the chat software leaves behind when it removes a person (keys, sessions, notes...)."""
    removed = 0
    database = sqlite3.connect(DATA_DIR / "webui.db", timeout=30)
    try:
        with database:
            for table in tables_about_people(database):
                removed += database.execute(f'DELETE FROM "{table}" WHERE user_id = ?', (user_id,)).rowcount
    finally:
        database.close()
    return removed


# --- Audit trail ----------------------------------------------------------------------

def command_audit(arguments: argparse.Namespace, records: sqlite3.Connection) -> None:
    for entry in reversed(store.audit_entries(records, arguments.limit)):
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(entry["at"]))
        print(f"{when}  {entry['actor']}  {entry['action']}  {entry['detail']}")
    print(f"\nEntries older than {store.AUDIT_RETENTION_DAYS} days are deleted. Sign-ins and admin changes")
    print(f"made in the browser are in {DATA_DIR / 'audit.log'}.")


# --- Training examples ----------------------------------------------------------------

def shorten(text: str, limit: int = 70) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_training_set(records: sqlite3.Connection) -> int:
    """Writes the approved examples as chat-format JSON lines. Returns how many."""
    # Consent is checked again here: an approved example is left out once its
    # author withdraws, or has not yet agreed to a newer notice.
    approved = store.trainable_examples(records, store.notice_version(NOTICE_FILE.read_text(encoding="utf-8")))
    TRAINING_DIR.mkdir(mode=0o700, exist_ok=True)
    held_back = [row for index, row in enumerate(approved) if index % VALIDATION_EVERY == VALIDATION_EVERY - 1]
    if not held_back and len(approved) > 1:
        held_back = approved[-1:]
    kept = [row for row in approved if row not in held_back]
    for name, chosen in zip(store.TRAINING_FILES, (kept, held_back)):
        with open(TRAINING_DIR / name, "w", encoding="utf-8") as handle:
            for row in chosen:
                messages = [{"role": "user", "content": row["question"]}, {"role": "assistant", "content": row["answer"]}]
                handle.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
    return len(approved)


def run_training(arguments: argparse.Namespace, records: sqlite3.Connection) -> None:
    approver = need_name(arguments)
    minimum = int(os.environ.get("TRAINING_MIN_EXAMPLES") or DEFAULT_MIN_EXAMPLES)
    command = os.environ.get("TRAIN_COMMAND", "").strip()
    count = build_training_set(records)
    if count < minimum:
        fail(f"Only {count} approved example(s). Training needs at least {minimum} (TRAINING_MIN_EXAMPLES).")
    if not command:
        fail("TRAIN_COMMAND is not set in settings.env, so there is no trainer to run. See the README, 'Adapter training'.")
    store.log(records, approver, "training.started", f"{count} examples")
    print(f"Training on {count} approved example(s) in {TRAINING_DIR}, approved by {approver}...")
    result = subprocess.run(shlex.split(command), cwd=ROOT, env={**os.environ, "MIRAH_TRAINING_DIR": str(TRAINING_DIR)})
    store.log(records, approver, "training.finished", f"exit code {result.returncode}")
    if result.returncode != 0:
        fail(f"The trainer stopped with exit code {result.returncode}.")
    print("The trainer finished.")


def command_training(arguments: argparse.Namespace, records: sqlite3.Connection) -> None:
    if arguments.action == "list":
        listed = store.examples(records, arguments.status)
        for row in listed:
            print(f"{row['id']:>5}  {row['status']:<8}  Q: {shorten(row['question'])}\n{'':>17}A: {shorten(row['answer'])}")
        print(f"{len(listed)} example(s).")
    elif arguments.action in ("approve", "reject"):
        reviewer = need_name(arguments)
        status = store.APPROVED if arguments.action == "approve" else store.REJECTED
        for example_id in arguments.ids:
            changed = store.review_example(records, int(example_id), status, reviewer)
            print(f"Example {example_id}: {status if changed else 'not found'}")
        store.clear_training_files(DATA_DIR)
    elif arguments.action == "build":
        print(f"Wrote {build_training_set(records)} approved example(s) to {TRAINING_DIR}")
    else:
        run_training(arguments, records)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="./privatellm", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    access = commands.add_parser("access")
    access.add_argument("email")
    access.add_argument("level", choices=sorted(LEVEL_GROUP))
    contributor = commands.add_parser("contributor")
    contributor.add_argument("email")
    contributor.add_argument("answer", choices=("yes", "no"))
    library = commands.add_parser("library")
    library.add_argument("action", choices=("pending", "show", "approve", "reject", "remove"))
    library.add_argument("file", nargs="?")
    library.add_argument("--level", choices=sorted(configure.LEVELS), default="open")
    library.add_argument("--by")
    for name in ("export-user", "delete-user"):
        person = commands.add_parser(name)
        person.add_argument("email")
        if name == "delete-user":
            person.add_argument("--yes", action="store_true")
    audit = commands.add_parser("audit")
    audit.add_argument("--limit", type=int, default=200)
    training = commands.add_parser("training")
    training.add_argument("action", choices=("list", "approve", "reject", "build", "run"))
    training.add_argument("ids", nargs="*")
    training.add_argument("--status", choices=(store.PENDING, store.APPROVED, store.REJECTED))
    training.add_argument("--by")
    return parser


HANDLERS = {
    "access": command_access,
    "contributor": command_contributor,
    "library": command_library,
    "export-user": command_export,
    "delete-user": command_delete,
    "audit": command_audit,
    "training": command_training,
}


def main() -> None:
    arguments = build_parser().parse_args()
    records = store.connect(DATA_DIR)
    try:
        store.prune_audit(records)
        HANDLERS[arguments.command](arguments, records)
    finally:
        records.close()


if __name__ == "__main__":
    try:
        main()
    except ApiError as error:
        sys.exit(f"The assistant refused a request: {error}")
    except KeyboardInterrupt:
        sys.exit(130)
