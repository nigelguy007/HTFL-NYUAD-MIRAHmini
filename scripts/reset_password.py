"""Sets a new password for one account, directly in the assistant's database.

The chat software has no "forgot password" link because it cannot send email.
Anyone who can run this on the host Mac already has full access to the data,
so this is the recovery route: it lists the accounts, asks which one, and
stores a new password. Run it through ./privatellm reset-password.
"""

from __future__ import annotations

import getpass
import os
import sqlite3
import sys
from pathlib import Path

import bcrypt

MIN_PASSWORD_LENGTH = 8
BCRYPT_MAX_BYTES = 72


def list_accounts(database: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """Returns (email, name, role) for every account, admins first."""
    rows = database.execute(
        "SELECT auth.email, user.name, user.role FROM auth JOIN user ON user.id = auth.id "
        "ORDER BY user.role != 'admin', auth.email"
    )
    return [(email, name, role) for email, name, role in rows]


def choose_email(accounts: list[tuple[str, str, str]]) -> str:
    print("Accounts on this assistant:")
    for email, name, role in accounts:
        print(f"  {email}   ({name}, {role})")
    wanted = (os.environ.get("RESET_EMAIL") or input("\nEmail of the account to reset: ")).strip().lower()
    known = {email.lower(): email for email, _, _ in accounts}
    if wanted not in known:
        raise SystemExit(f"No account uses '{wanted}'. Check the list above for the exact address.")
    return known[wanted]


def read_new_password() -> str:
    password = os.environ.get("RESET_PASSWORD")
    if password is None:
        password = getpass.getpass("New password (typing stays hidden): ")
        if getpass.getpass("Type it again: ") != password:
            raise SystemExit("The two passwords did not match. Nothing was changed.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"Use at least {MIN_PASSWORD_LENGTH} characters. Nothing was changed.")
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise SystemExit(f"Use at most {BCRYPT_MAX_BYTES} characters. Nothing was changed.")
    return password


def main() -> None:
    database_file = Path(sys.argv[1])
    if not database_file.exists():
        raise SystemExit(f"{database_file} not found. Has the assistant been started at least once?")
    with sqlite3.connect(database_file) as database:
        accounts = list_accounts(database)
        if not accounts:
            raise SystemExit("There are no accounts yet. Run ./privatellm configure to create the first one.")
        email = choose_email(accounts)
        password_hash = bcrypt.hashpw(read_new_password().encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        database.execute("UPDATE auth SET password = ? WHERE email = ?", (password_hash, email))
    role = next(role for known_email, _, role in accounts if known_email == email)
    print(f"\nPassword changed for {email}. Sign in with the new one.")
    if role == "pending":
        print("This account is still waiting for an admin to approve it, so it cannot chat yet.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
