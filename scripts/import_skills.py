"""Copies chosen skills from a skills library on GitHub into the assistant.

A skill is a page of instructions (a SKILL.md file) that a user switches on
for one chat by typing $ in the message box. The list of skills to copy is in
skills/selected.txt. Safe to run again: unchanged skills are left alone.

Skills written for Claude Code often rely on tools this assistant does not
have, and a long skill crowds out the conversation, so skills that are too
long are skipped with a reason.
"""

from __future__ import annotations

import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

from configure import API_KEY_FILE, EVERYONE_CAN_READ, ROOT, Api, ApiError

SELECTION_FILE = ROOT / "skills" / "selected.txt"
DEFAULT_LIBRARY_URL = "https://raw.githubusercontent.com/nigelguy007/claude-skills-library/HEAD/skills"
# A skill is added to every message of the chat it is switched on for. Past
# this length it leaves too little room for the conversation on a small model.
MAX_SKILL_WORDS = 900
FETCH_TIMEOUT_SECONDS = 30
FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def read_selection() -> list[str]:
    if not SELECTION_FILE.exists():
        raise SystemExit(f"{SELECTION_FILE} not found.")
    lines = (line.strip() for line in SELECTION_FILE.read_text().splitlines())
    return [line.strip("/") for line in lines if line and not line.startswith("#")]


def fetch_skill_text(library_url: str, skill_path: str) -> str:
    url = f"{library_url.rstrip('/')}/{skill_path}/SKILL.md"
    with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_skill(skill_path: str, text: str) -> dict[str, str]:
    """Splits a SKILL.md into its name, description and instructions."""
    fields: dict[str, str] = {}
    body = text
    match = FRONT_MATTER.match(text)
    if match:
        body = text[match.end():]
        for line in match.group(1).splitlines():
            key, separator, value = line.partition(":")
            if separator and key.strip() in ("name", "description"):
                fields[key.strip()] = value.strip().strip("\"'")
    folder = skill_path.rsplit("/", 1)[-1]
    return {
        "id": re.sub(r"[^a-z0-9_-]+", "-", folder.lower()).strip("-"),
        "name": fields.get("name") or folder,
        "description": fields.get("description", ""),
        # $ARGUMENTS is a Claude Code placeholder for what the user typed.
        "content": body.strip().replace("$ARGUMENTS", "what the user describes") + "\n",
    }


def save_skill(api: Api, skill: dict[str, str]) -> str:
    """Creates or updates one skill. Returns 'added', 'updated' or 'unchanged'."""
    form: dict[str, Any] = {**skill, "access_grants": EVERYONE_CAN_READ, "is_active": True}
    try:
        existing = api.request("GET", f"/api/v1/skills/id/{skill['id']}")
    except ApiError as error:
        if error.status not in (401, 404):
            raise
        api.request("POST", "/api/v1/skills/create", form)
        return "added"
    if (existing.get("content") or "").strip() == skill["content"].strip():
        return "unchanged"
    form["expected_version_id"] = existing.get("version_id")
    api.request("POST", f"/api/v1/skills/id/{skill['id']}/update", form)
    return "updated"


def import_one(api: Api, library_url: str, skill_path: str) -> str:
    try:
        text = fetch_skill_text(library_url, skill_path)
    except (urllib.error.URLError, OSError) as error:
        return f"skipped (could not download: {error})"
    words = len(text.split())
    if words > MAX_SKILL_WORDS:
        return f"skipped ({words} words; the limit is {MAX_SKILL_WORDS})"
    return save_skill(api, parse_skill(skill_path, text))


def main() -> None:
    if not API_KEY_FILE.exists():
        raise SystemExit("No API key yet. Run ./privatellm configure first.")
    api = Api(os.environ.get("WEBUI_URL", "http://127.0.0.1:8080"), API_KEY_FILE.read_text().strip())
    library_url = os.environ.get("SKILLS_LIBRARY_URL", DEFAULT_LIBRARY_URL)
    selection = read_selection()
    for skill_path in selection:
        print(f"{skill_path.rsplit('/', 1)[-1]}: {import_one(api, library_url, skill_path)}")
    print(f"\n{len(selection)} skill(s) processed. In a chat, type $ to switch one on.")


if __name__ == "__main__":
    try:
        main()
    except ApiError as error:
        sys.exit(f"The assistant refused a request: {error}")
    except KeyboardInterrupt:
        sys.exit(130)
