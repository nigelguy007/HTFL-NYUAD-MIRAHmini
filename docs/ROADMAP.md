# MIRAH mini: where it stands against the full plan

MIRAH mini is a small, working assistant that runs on one computer. The full
MIRAH / Oracle plan is in [expectations/SCOPE.md](expectations/SCOPE.md) and
[expectations/ARCHITECTURE.md](expectations/ARCHITECTURE.md), copied from the
`HTFL-NYUAD` repository. This page lists each expectation, what mini does today,
and what is missing, so it can be grown one row at a time.

Status: **Done**, **Partly**, or **Not yet**.

## What the assistant must do (SCOPE §2)

| Expectation | MIRAH mini today | Status |
| --- | --- | --- |
| Answer questions across Lab material | Searches two knowledge bases on every question | Done |
| Cite the source of every factual claim | Instructed to name the document; sources are listed under each answer | Partly: not enforced, the model can still slip |
| Say when the answer is outside the approved library | Instructed to say so plainly | Partly: instruction only |
| Retrieve ideas, themes and recommendations | Works for what is written in the documents | Partly |
| Connect sessions, contributors and artefacts | No: answers from a handful of passages at a time | Not yet |
| Surface recurring patterns and tensions | No: needs reading across the whole library | Not yet |
| Reflective and critical questioning | The `grilling`, `pre-mortem` and similar skills, switched on per chat | Partly: skills, not a guided mode |
| INSPIRE, IMAGINE, ACTIVATE guided journey | None: mini is a plain chat | Not yet |
| LLM modes (facilitation, critical inquiry, ...) | Skills cover some of this | Partly |

## What it must not do (SCOPE §2)

| Expectation | MIRAH mini today | Status |
| --- | --- | --- |
| No autonomous external actions | It has no tools to act with; web search is off | Done |
| No adding its own output to the trusted library | The library only changes when a person uploads or syncs | Done |
| No revealing material above a user's access level | Every approved user can read both knowledge bases | Not yet: no access levels |
| No profiling, diagnosing or ranking people | Not instructed either way | Not yet |

## Content (SCOPE §3)

| Expectation | MIRAH mini today | Status |
| --- | --- | --- |
| Lab methodology, provocations, themes | Whatever is uploaded or synced; no sensitivity labels | Partly |
| Curator approval before content is searchable | No approval step: uploads are searchable at once | Not yet |
| Participant artefacts, reflections, recordings | Must not be loaded into mini | Out of scope for mini |

## Architecture (ARCHITECTURE)

| Expectation | MIRAH mini today | Status |
| --- | --- | --- |
| Model runs on NYUAD servers | Runs on whichever computer it is installed on | Not yet |
| Main model gpt-oss-120b, fallback Llama 3.3 70B | Chosen automatically when the machine has 96 GB / 64 GB of memory; smaller machines get gpt-oss-20b, Gemma 4 or Llama 3.2 | Done, within the machine's limits |
| No Chinese-origin models unless Security permits | None are used; a test fails if one is chosen | Done |
| App and GPU servers have no internet | Outside connections are switched off in settings, not blocked by a firewall | Partly |
| External services off until contracts and Legal approval | OpenAI, web search and the rest are off | Done |
| 20 people at once; first words in under 4 s, full answer in under 18 s | One person at a time; about 15 to 25 s per document answer on a 16 GB Mac | Not yet |
| NYU single sign-on with MFA | Email and password, admin approves each account | Not yet |
| PostgreSQL + pgvector, object storage, backups | One SQLite file and a local index; no backups | Not yet |
| Library learning (approved items searchable) | Sync and upload add items; removal deletes them | Partly: no approval |
| Adapter training on consented input | None | Not yet |
| Consent, export, deletion, audit log, DPIA | None | Not yet |

## Suggested order for growing it

1. Run it on a machine with 64 GB or more, so it uses the plan's own models.
2. Add a firewall rule blocking outbound traffic, to turn "switched off" into "blocked".
3. Add an approval step before uploaded content becomes searchable.
4. Add access levels, so not every user can read every document.
5. Replace email and password with NYU single sign-on.
6. Build the INSPIRE, IMAGINE, ACTIVATE journey on top.

Steps 3 to 6 each need changes that the chat software used here may not
support. When one of them does not fit, that is the point to move to the
custom application in the `HTFL-NYUAD` prototype branches.
