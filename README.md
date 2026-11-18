# MIRAH mini

A small, working version of MIRAH for Hack the Future Lab, NYU Abu Dhabi. The
full plan it is growing towards is in [docs/expectations](docs/expectations),
and [docs/ROADMAP.md](docs/ROADMAP.md) shows how far this version has got.

A ChatGPT-style assistant that runs on one Apple Silicon Mac and answers from
your own documents. Nothing is sent to an outside service: the model, the
document index and the chat history all stay on that Mac. Up to about five
people use it from their browsers over your office network.

It is built from existing open-source parts rather than new code:

| Part | Job |
| --- | --- |
| [Ollama](https://ollama.com) | Runs the language model on the Mac's GPU |
| [Open WebUI](https://openwebui.com) | The chat website, logins, document index |
| [oikb](https://docs.openwebui.com/ecosystem/knowledge-base-sync) | Copies documents in from folders, cloud drives and websites |

This folder adds the setup, the privacy settings and the wiring between them.

## What to expect

- **Quality is below ChatGPT or Claude.** Models that fit on a Mac are weaker at
  reasoning and at long documents. Looking up facts in your documents works
  well; analysis across many documents does not.
- **Spreadsheets are searched, not calculated.** "What did Acme order?" works.
  "What is the total of column C?" does not: the model only sees a few rows.
- **Speed depends on memory.** A few people get answers at the same moment:
  2 on a 16 GB machine, 4 from 32 GB, 8 from 96 GB (`PARALLEL_CHATS` in
  `settings.env`). They share the machine, so each answer is slower while
  others are running. Anyone beyond that number waits in a queue.

| Memory | Model chosen | Maker | Expectation |
| --- | --- | --- | --- |
| under 16 GB | `llama3.2:3b` | Meta | Weak. Not recommended. |
| 16 to 23 GB | `gemma4:12b` | Google | Usable for document lookups |
| 24 to 63 GB | `gpt-oss:20b` | OpenAI | Good |
| 64 to 95 GB | `llama3.3:70b` | Meta | The plan's fallback model |
| 96 GB or more | `gpt-oss:120b` | OpenAI | The plan's main model |

No Chinese-origin model is used at any size, for the chat model or the search
model (`embeddinggemma`, Google), because the NYUAD plan rules them out unless
its Security team permits them.

## Set up

On the Mac that will host it. Nothing needs installing first, and everything
goes inside this folder, so put the folder on the drive you want it to live on
(an external drive must be formatted APFS and stay plugged in):

```bash
./setup.sh               # installs everything, downloads the model (5 to 25 GB)
./privatellm start       # starts the assistant
./privatellm configure   # creates your admin login, the knowledge base and the Assistant
```

`./privatellm status` prints the address. Open it, log in, and chat with
**Assistant**.

Until `configure` has created your admin login, the site is reachable from the
host Mac only. That stops someone else on the network claiming the admin
account first.

## Add your documents

The Assistant answers from two knowledge bases:

- **Company Knowledge** is for documents you upload by hand: Workspace,
  Knowledge, Company Knowledge, **+**, Upload files. Nothing else changes it.
- **Synced Sources** is filled by `./privatellm sync` from folders, cloud
  drives, websites or a GitHub repository. Sync keeps it an exact copy of those
  sources and deletes anything else in it, so never upload there by hand.

To set up sync:

```bash
cp sync/sources.example.yaml sync/sources.yaml
```

Edit `sync/sources.yaml`: keep the sources you use, delete the rest. Passwords
and tokens go in `sync/credentials.env` as `NAME=value` lines (the names are
listed in the example file). Then:

```bash
./privatellm sync
```

Run it again whenever the sources change. Only new and changed files are
copied. Indexing continues in the background for a while after a large first
sync.

`sync/sources.htfl.yaml` is a ready-made list for Hack the Future Lab: the
public Lab website and the Oracle project documents on GitHub.

Synced files are downloaded to this Mac and indexed here. Nothing is uploaded.

## Add skills

A skill is a page of instructions for one kind of task, such as running a
pre-mortem or drafting a decision memo. `skills/selected.txt` lists the ones to
copy in from the skills library on GitHub:

```bash
./privatellm skills
```

In a chat, type `$` and pick a skill to switch it on for that conversation. It
is not applied to other chats.

To add more, put the skill's folder path in `skills/selected.txt` and run the
command again. To copy in every skill from one GitHub repository instead:

```bash
./privatellm skills --repo https://github.com/<owner>/<repository>
```

It finds every `SKILL.md` in it, keeps two skills with the same folder name
apart, skips the over-long ones and prints a count at the end. A private
repository needs the Mac to be signed in to GitHub for `git clone`. Two limits:

- Only skills that are plain instructions do anything here. Most skills in the
  library were written for Claude Code and tell it to run commands, search the
  web or use connected apps, none of which this assistant can do.
- A skill is sent with every message of the chat it is switched on for, so it
  uses up room the conversation needs. Skills over 900 words are skipped.

## Add people

1. They open the address from `./privatellm status` and sign up. For data
   protection they should not use their real name or email: they invent a
   username and use `username@mirah.local` as the email. The sign-in page tells
   them this. It is a request, not a block: nothing stops someone typing a real
   name. Keep no list linking usernames to people unless you need one.
2. You approve them: your avatar, **Admin Panel**, **Users**, change `pending` to `user`.

The address only works on your office network. For access from elsewhere, put
the Mac and their devices on a private VPN such as Tailscale. Do not open the
port to the internet: logins travel unencrypted.

## Access levels

There is one MIRAH for everyone, but it answers from different libraries
depending on who is asking.

| Level | Reads | Set with |
| --- | --- | --- |
| `open` (everyone approved) | Company Knowledge, Synced Sources | `./privatellm access name@mirah.local open` |
| `facilitators` | the above, plus the Facilitator Library | `./privatellm access name@mirah.local facilitators` |
| `leads` | all of the above, plus the Lab Lead Library | `./privatellm access name@mirah.local leads` |

A person below a library's level gets no text from it: it is left out of the
search for them, not hidden afterwards. As admin you upload into the two
restricted libraries the same way as into Company Knowledge.

The admin account reads everything. Level changes apply to the next question.

## Approving documents

Nothing a contributor uploads reaches MIRAH until a curator approves it.

1. Let someone submit: `./privatellm contributor name@mirah.local yes`. They
   then see **Workspace**, **Knowledge**, **Submissions**, and upload there.
2. See what is waiting: `./privatellm library pending`. Each line starts with
   the document's id. Read one before deciding: `./privatellm library show <id>`.
3. Decide, giving your name for the record:
   - `./privatellm library approve <id> --level open --by "Your Name"` (or
     `--level facilitators`, `--level leads`). MIRAH can answer from it within
     seconds. The approved copy belongs to the admin and gets a new id, which
     the command prints; the submitter's own copy is deleted, so they cannot
     change what you approved.
   - `./privatellm library reject <id> --by "Your Name"` deletes it.
4. Take an approved document out again:
   `./privatellm library remove <id> --by "Your Name"`. MIRAH stops answering
   from it at once.

Limits: approval is a command on the host computer, not a button in the
browser. Contributors can see each other's waiting submissions, and can attach
one to their own chat before it is approved. Documents you
upload yourself as admin, and everything `./privatellm sync` brings in, skip
the queue: you are the curator for those.

## Consent

Nobody gets an answer, the admin included, until they have typed **I AGREE**
to the notice in `config/consent-notice.txt`. Edit that file to say what is
true for your Lab. Its first line is its version: change `Version: 1` to
`Version: 2` and everyone is asked again.

Consent is recorded per purpose. Using MIRAH is one; training is a separate,
optional one. People type these in the chat at any time:

| They type | What happens |
| --- | --- |
| `I AGREE` | They can use MIRAH |
| `I AGREE TO TRAINING` | Their later questions and answers may become training examples |
| `WITHDRAW TRAINING` | That stops, and their collected examples are deleted |
| `WITHDRAW CONSENT` | Both end; they are asked again before the next answer |
| `MY CONSENT` | Shows what they have agreed to |

## Export and deletion

- **Their own conversations:** each person can export or delete these
  themselves under Settings, Data Controls.
- **Everything held about one person:** `./privatellm export-user name@mirah.local`
  writes their account, conversations, uploads, consent history and training
  examples to a file in `exports/`. Hand it over, then delete the file.
- **Remove one person:** `./privatellm delete-user name@mirah.local` asks you to
  type DELETE, then removes their account, conversations, uploaded files (from
  the search index too), sign-in keys and sessions, notes and anything else
  filed under them, consent records and training examples, and clears the
  built training set.

What deletion does not reach: documents they submitted that a curator approved
(the command lists them, and `library remove` takes them out), sign-in lines in
`logs/` and `data/audit.log`, backups you made yourself, export files you
kept, and a model already trained on their examples.

## Audit trail

`./privatellm audit` lists consent given and withdrawn, access changes,
approvals and rejections with the curator's name, exports, deletions and
training runs. It records account ids, never names or email addresses, and
entries older than a year are deleted.

Sign-ins and changes made in the admin screens are in `data/audit.log`, written
by the chat software (who did what, not the content of conversations). That
file is trimmed by size, not by age.

## Adapter training

The plan calls for training a small add-on (an adapter) on what people type,
only from people who opted in, with identifying details removed and each
example reviewed. This setup does everything up to the training run itself.

1. People opt in by typing `I AGREE TO TRAINING`. From then on each question
   and answer is stored with emails, links, long numbers, handles and their own
   username replaced. Nothing is collected from anyone else, and nothing from
   the admin, facilitators or Lab leads even if they opt in: their answers can
   quote restricted documents, and a trained model serves everyone.
2. Review every example: `./privatellm training list --status pending`, then
   `./privatellm training approve 3 4 7 --by "Your Name"` or `reject`. The
   automatic clean-up cannot spot a name inside a sentence, and an answer can
   quote a restricted document: rejecting those is the reviewer's job.
3. `./privatellm training build` writes the approved examples to
   `data/training/train.jsonl` and `valid.jsonl`. Consent is checked again at
   this point: an approved example is left out if its author has withdrawn, or
   has not yet agreed to a newer version of the notice.
4. `./privatellm training run --by "Approver Name"` refuses unless there are at
   least 500 approved examples (`TRAINING_MIN_EXAMPLES` in `settings.env`) and a
   trainer is set, then runs the trainer and records who approved the run.

**The trainer is not included and no training run has been tested.** Set
`TRAIN_COMMAND` in `settings.env` to the program that trains an adapter for
your model; it is given the folder in `MIRAH_TRAINING_DIR`. That step needs a
machine with far more memory than a 16 GB Mac, a trainer that matches the
chosen model, and a way to load the result into Ollama. The plan also requires
Legal, privacy and (for research) IRB approval before any run; the `--by` name
records who gave it, it does not replace it.

## Updating an existing install

After `git pull`, run `./privatellm restart` and then `./privatellm configure`.
The second command adds the access groups, the extra libraries and the consent
notice. Everyone, you included, is asked to agree before their next answer.

## Forgotten passwords

There is no "forgot password" link, because the assistant cannot send email.

- **Someone else forgot theirs:** as admin, go to your avatar, Admin Panel,
  Users, click the person, and set a new password.
- **You forgot yours, or it stopped working:** on the host Mac run
  `./privatellm reset-password`. It lists the accounts, asks which one, and sets
  a new password. The assistant can stay running.

## Everyday commands

| Command | What it does |
| --- | --- |
| `./privatellm start` / `stop` / `restart` | Run or stop the assistant |
| `./privatellm status` | Is it running, and at what address |
| `./privatellm doctor` | Which models are installed and loaded, and how much memory is free |
| `./privatellm pull` | Download the chat and search models named in `settings.env` |
| `./privatellm sync` | Refresh documents |
| `./privatellm logs` | Watch the logs |
| `./privatellm access` / `contributor` / `library` / `export-user` / `delete-user` / `audit` / `training` | See the sections above |

The assistant stops when the Mac restarts or sleeps. Run `./privatellm start`
again, and set the Mac not to sleep (System Settings, Energy).

`start` loads both models into memory before the chat opens, so the first
question does not wait for the model to be read from the drive. It warns if a
model is missing (the chat would say "Model not found") or if memory is short.

## If answers are slow or the Mac freezes

Ollama is set to use as little memory as it can: flash attention and an 8-bit
conversation cache (`OLLAMA_FLASH_ATTENTION`, `OLLAMA_KV_CACHE_TYPE` in
`settings.env` override them). Run `./privatellm doctor` while a question is
being answered. If the model's PROCESSOR column shows part CPU, it does not fit
in the memory the Mac's graphics chip can use, and answers are several times
slower. Then, one step at a time, followed by `./privatellm restart`:

1. Quit Chrome and other large apps; keep only the MIRAH tab open.
2. `PARALLEL_CHATS=1`: one answer at a time, others wait their turn.
3. `CONTEXT_LENGTH=4096`: answers draw on fewer document excerpts.
4. A smaller `CHAT_MODEL`, then `./privatellm pull` and `./privatellm configure`.

## Changing things

- **Where things are stored:** all inside this folder. `apps/` and `bin/` hold
  the software, `models/` the model, `data/` your documents and chats. To keep
  only the model somewhere else, set `MODELS_DIR` in `settings.env`. To remove
  the assistant completely, stop it and delete this folder. Ollama also leaves
  a small `~/.ollama` folder on the Mac (an identity key, a few KB).
- **Model, port, context size:** `settings.env`, then `./privatellm restart`.
  After changing `CHAT_MODEL`, run `./privatellm pull` and
  `./privatellm configure`.
- **Privacy and search settings:** `config/openwebui.env`. These override the
  admin screens on every start, so a setting changed in the browser reverts on
  restart. That is deliberate: the privacy switches cannot be turned off by
  accident.
- **Logo, colours and name:** the `branding` folder. It also holds the
  sign-in and chat background photos and the wordmark typeface, in
  `branding/static/brand`; swap `gateway.webp` (sign-in) or `coast.webp` (chat)
  for your own pictures, keeping the file names. Replace the image files in
  `branding/static` with your own (same file names and sizes), edit the colours
  in `branding/static/custom.css` and the name in `branding/brand.env` (which also hides the
  "(Open WebUI)" the software adds after a custom name), then
  `./privatellm restart`. To go back to the standard look, rename or delete the
  `branding` folder and restart. The chat software's licence allows replacing
  its logo and colours only while 50 or fewer people use this install in any
  30 days.
- **How the Assistant behaves:** the instructions in `scripts/configure.py`
  (`SYSTEM_PROMPT`), then `./privatellm configure`.

## What keeps it private

- The model only listens on the Mac itself; other computers reach the chat
  website, never the model.
- Ollama's cloud models are disabled.
- Open WebUI's outside connections are off: OpenAI and other hosted models, web
  search, community sharing, update checks, cloud drive pickers.
- Document indexing uses a local model.
- The chat software's other routes to the model (a pass-through to Ollama and
  a few helper endpoints) are refused for everyone. They would skip the consent
  notice, MIRAH's instructions and its libraries.
- The "memories" feature is off, so there is no second store of personal notes.

These settings stop the software from calling out. They are not a firewall. If
you need proof for an audit, also block outbound traffic from the Mac.

Admins cannot open other people's chats from the website
(`ENABLE_ADMIN_CHAT_ACCESS=false`). Anyone with access to the host computer's
files can still read the database in `data/`, so this protects against
curiosity, not against the person who runs the machine. Tell your users.

## Tested and not tested

`tests/test_e2e.sh` runs the whole flow against a stand-in for the model:
start, configure, sync, a question finding the right document, the document
text reaching the model, a colleague signing up and being approved, each
privacy switch reporting off, the consent gate, each access level, the approval
queue, training-example collection and review, export, deletion and the audit
trail. `tests/test_store.py` checks the consent and audit records. Both pass on
Linux with Open WebUI 0.13.3 and oikb 0.6.0.

Not tested: anything on a real Mac, a real model's answers, an adapter
training run, and the cloud drive connectors (they need your accounts). Expect
to adjust something on first run.
