"""Checks for scripts/mirah_store.py. Run: python3 tests/test_store.py"""

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import mirah_store as store  # noqa: E402

failures = 0


def check(label: str, passed: bool) -> None:
    global failures
    print(("ok   " if passed else "FAIL ") + label)
    failures += 0 if passed else 1


with tempfile.TemporaryDirectory() as folder:
    records = store.connect(folder)

    check("no consent before agreeing", not store.has_consent(records, "u1", store.USE, "1"))
    store.grant(records, "u1", store.USE, "1")
    store.grant(records, "u1", store.USE, "1")
    check("agreeing is recorded once", len(store.consent_history(records, "u1")) == 1)
    check("consent to use is not consent to training", not store.has_consent(records, "u1", store.TRAINING, "1"))
    check("an older version does not count for a new notice", not store.has_consent(records, "u1", store.USE, "2"))
    check("consent is per person", not store.has_consent(records, "u2", store.USE, "1"))
    check("withdrawing ends it", store.withdraw(records, "u1", store.USE) and not store.has_consent(records, "u1", store.USE, "1"))
    check("withdrawing twice changes nothing", not store.withdraw(records, "u1", store.USE))
    check("history keeps the withdrawn record", store.consent_history(records, "u1")[0]["withdrawn_at"] is not None)

    check("version is read from the first line", store.notice_version("Version: 7\n\nText") == "7")
    check("a notice without a version is version 1", store.notice_version("Just text") == "1")

    scrubbed = store.deidentify("Mail amal@nyu.edu or call +971 50 123 4567, see https://x.org/a and @amal_k. Amal said so.", ("Amal",))
    check("email is removed", "[EMAIL]" in scrubbed and "nyu.edu" not in scrubbed)
    check("phone number is removed", "[NUMBER]" in scrubbed and "123 4567" not in scrubbed)
    check("link is removed", "[LINK]" in scrubbed and "x.org" not in scrubbed)
    check("handle is removed", "[HANDLE]" in scrubbed)
    check("a given name is removed", "Amal" not in scrubbed and "[NAME] said so" in scrubbed)
    check("each part of a name is removed", store.deidentify("Ask Layla or Dr Haddad.", ("Layla Haddad",)) == "Ask [NAME] or Dr [NAME].")
    check("short numbers and years stay", store.deidentify("In 2026 we ran 12 sessions.") == "In 2026 we ran 12 sessions.")

    store.add_example(records, "u1", "q1", "a1")
    store.add_example(records, "u2", "q2", "a2")
    check("examples start pending", [row["status"] for row in store.examples(records)] == [store.PENDING, store.PENDING])
    check("a review is recorded", store.review_example(records, 1, store.APPROVED, "Rev") and store.examples(records, store.APPROVED)[0]["reviewed_by"] == "Rev")
    check("reviewing a missing example reports it", not store.review_example(records, 99, store.APPROVED, "Rev"))
    store.grant(records, "u2", store.USE, "1")
    store.grant(records, "u2", store.TRAINING, "1")
    store.review_example(records, 2, store.APPROVED, "Rev")
    check("an approved example without live consent is not trainable", [row["id"] for row in store.trainable_examples(records, "1")] == [2])
    check("a newer notice makes old consent not count", store.trainable_examples(records, "2") == [])
    store.withdraw(records, "u2", store.TRAINING)
    check("withdrawal makes an approved example untrainable", store.trainable_examples(records, "1") == [])
    training = Path(folder) / "training"
    training.mkdir()
    (training / "train.jsonl").write_text("stale")
    removed = store.delete_user(records, "u1", folder)
    check("deleting a person removes their examples and consent", removed == {"consent_records": 1, "training_examples": 1})
    check("other people's examples stay", len(store.examples(records)) == 1)
    check("the built training set is cleared", not (training / "train.jsonl").exists())

    now = time.time()
    records.execute("INSERT INTO audit (at, actor, action) VALUES (?, 'x', 'old')", (int(now - 366 * store.SECONDS_PER_DAY),))
    records.execute("INSERT INTO audit (at, actor, action) VALUES (?, 'x', 'recent')", (int(now - 364 * store.SECONDS_PER_DAY),))
    records.commit()
    store.prune_audit(records, now)
    actions = [row["action"] for row in store.audit_entries(records, 1000)]
    check("audit entries older than a year are deleted", "old" not in actions)
    check("audit entries within a year are kept", "recent" in actions)
    check("deleting a person leaves the audit trail", "consent.granted.use" in actions)
    records.close()

print("\nAll checks passed." if failures == 0 else f"\n{failures} check(s) failed.")
sys.exit(failures)
