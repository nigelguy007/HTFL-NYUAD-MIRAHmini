"""
title: MIRAH consent gate
description: Asks each person to agree to the notice before their first question, records consent per purpose, and collects training examples only from people who opted in.
version: 1.0.0
"""

from __future__ import annotations

import os
import sys
import time

# ./privatellm start sets these, so this filter shares one store with the host commands.
sys.path.insert(0, os.environ.get("MIRAH_SCRIPTS_DIR", ""))
import configure  # noqa: E402
import mirah_store as store  # noqa: E402

DATA_DIR = os.environ.get("DATA_DIR", ".")
NOTICE_FILE = os.environ.get("MIRAH_CONSENT_NOTICE", "")
MISSING_NOTICE = "Version: 0\n\nThe consent notice file is missing. Ask the person who runs MIRAH to restore config/consent-notice.txt."

AGREE = "i agree"
AGREE_TRAINING = "i agree to training"
WITHDRAW_TRAINING = "withdraw training"
WITHDRAW_ALL = "withdraw consent"
SHOW = "my consent"
COMMANDS = (AGREE, AGREE_TRAINING, WITHDRAW_TRAINING, WITHDRAW_ALL, SHOW)
# Questions as typed, held between the question arriving and the answer leaving.
# By then the chat software has rewritten the question to include passages from
# the documents, which must not be copied into training examples.
MAX_HELD_QUESTIONS = 500


def load_notice() -> tuple[str, str]:
    """The notice people see (without its version line) and its version."""
    try:
        with open(NOTICE_FILE, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        text = MISSING_NOTICE
    version = store.notice_version(text)
    body = "\n".join(text.strip().splitlines()[1:]).strip()
    return body, version


def message_text(message: dict) -> str:
    content = message.get("content", "")
    if isinstance(content, list):
        return " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)


def last_message(messages: list[dict], role: str) -> str:
    for message in reversed(messages):
        if message.get("role") == role:
            return message_text(message)
    return ""


def as_command(text: str) -> str:
    return " ".join(text.lower().strip().strip(".!\"'").split())


def describe(connection, user_id: str, version: str) -> str:
    lines = []
    for purpose, label in ((store.USE, "Using MIRAH"), (store.TRAINING, "Use of your conversations for training")):
        agreed = store.has_consent(connection, user_id, purpose, version)
        lines.append(f"- {label}: {'agreed' if agreed else 'not agreed'}")
    return "\n".join(lines)


async def reads_restricted_libraries(user: dict) -> bool:
    """True for the admin, facilitators and Lab leads: their answers can quote restricted documents."""
    if user.get("role") != "user":
        return True
    from open_webui.models.groups import Groups

    groups = await Groups.get_groups_by_member_id(user["id"])
    return any(group.name in (configure.FACILITATORS, configure.LEADS) for group in groups)


def question_key(user_id: str, metadata: dict | None) -> str:
    return f"{user_id}:{(metadata or {}).get('message_id') or ''}"


class Filter:
    def __init__(self) -> None:
        self.held_questions: dict[str, str] = {}

    async def inlet(self, body: dict, __user__: dict | None = None, __metadata__: dict | None = None) -> dict:
        user_id = (__user__ or {}).get("id")
        if not user_id:
            return body
        notice, version = load_notice()
        question = last_message(body.get("messages", []), "user")
        connection = store.connect(DATA_DIR)
        try:
            reply = self.handle_command(connection, user_id, as_command(question), version)
            if reply is None and not store.has_consent(connection, user_id, store.USE, version):
                reply = notice
            opted_in = store.has_consent(connection, user_id, store.TRAINING, version)
        finally:
            connection.close()
        if reply is not None:
            # Stops the question before it reaches the model; the person sees this text.
            raise Exception(reply)
        # Examples come only from people at the open level, so that text from a
        # restricted library can never end up in a model everyone uses.
        if opted_in and not await reads_restricted_libraries(__user__):
            self.hold(question_key(user_id, __metadata__), question)
        return body

    def hold(self, key: str, question: str) -> None:
        while len(self.held_questions) >= MAX_HELD_QUESTIONS:
            self.held_questions.pop(next(iter(self.held_questions)))
        self.held_questions[key] = question

    def handle_command(self, connection, user_id: str, command: str, version: str) -> str | None:
        if command not in COMMANDS:
            return None
        today = time.strftime("%d %B %Y")
        if command == AGREE:
            store.grant(connection, user_id, store.USE, version)
            return f"Thank you. Your agreement was recorded on {today}. Ask MIRAH your question now."
        if command == SHOW:
            return "What you have agreed to:\n" + describe(connection, user_id, version)
        if command == WITHDRAW_ALL:
            store.withdraw(connection, user_id, store.TRAINING)
            store.withdraw(connection, user_id, store.USE)
            removed = store.delete_examples(connection, user_id, DATA_DIR)
            return f"Your agreement is withdrawn and {removed} training example(s) were deleted. Type I AGREE to use MIRAH again."
        if command == WITHDRAW_TRAINING:
            store.withdraw(connection, user_id, store.TRAINING)
            removed = store.delete_examples(connection, user_id, DATA_DIR)
            return f"Training use is switched off and {removed} example(s) collected from you were deleted."
        if not store.has_consent(connection, user_id, store.USE, version):
            return "Please type I AGREE first, then I AGREE TO TRAINING."
        store.grant(connection, user_id, store.TRAINING, version)
        return (
            f"Thank you. From {today}, your questions and MIRAH's answers may be used to improve it, "
            "after identifying details are removed and a person has reviewed them. Type WITHDRAW TRAINING to stop."
        )

    def outlet(self, body: dict, __user__: dict | None = None, __metadata__: dict | None = None) -> dict:
        user = __user__ or {}
        user_id = user.get("id")
        if not user_id:
            return body
        _, version = load_notice()
        # Only a question held at the way in is used: no held question, no example.
        question = self.held_questions.pop(question_key(user_id, __metadata__), "")
        answer = last_message(body.get("messages", []), "assistant")
        if not (question and answer):
            return body
        connection = store.connect(DATA_DIR)
        try:
            if store.has_consent(connection, user_id, store.TRAINING, version):
                own_names = tuple(part for part in (user.get("name", ""), user.get("email", "").split("@")[0]) if part)
                store.add_example(
                    connection,
                    user_id,
                    store.deidentify(question, own_names),
                    store.deidentify(answer, own_names),
                )
        finally:
            connection.close()
        return body
