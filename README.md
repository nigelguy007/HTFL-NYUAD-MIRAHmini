# Private assistant

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
- **Speed depends on memory.** One person at a time gets a fast answer; several
  at once queue up.

| Mac memory | Model chosen | Expectation |
| --- | --- | --- |
| under 16 GB | `qwen3.5:4b` | Weak. Not recommended. |
| 16 to 31 GB | `qwen3.5:9b` | Usable for document lookups |
| 32 to 47 GB | `qwen3.5:27b` | Good |
| 48 GB or more | `qwen3.5:35b` | Best this setup offers |

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
command again. Two limits:

- Only skills that are plain instructions do anything here. Most skills in the
  library were written for Claude Code and tell it to run commands, search the
  web or use connected apps, none of which this assistant can do.
- A skill is sent with every message of the chat it is switched on for, so it
  uses up room the conversation needs. Skills over 900 words are skipped.

## Add people

1. They open the address from `./privatellm status` and sign up.
2. You approve them: your avatar, **Admin Panel**, **Users**, change `pending` to `user`.

The address only works on your office network. For access from elsewhere, put
the Mac and their devices on a private VPN such as Tailscale. Do not open the
port to the internet: logins travel unencrypted.

## Everyday commands

| Command | What it does |
| --- | --- |
| `./privatellm start` / `stop` / `restart` | Run or stop the assistant |
| `./privatellm status` | Is it running, and at what address |
| `./privatellm sync` | Refresh documents |
| `./privatellm logs` | Watch the logs |

The assistant stops when the Mac restarts or sleeps. Run `./privatellm start`
again, and set the Mac not to sleep (System Settings, Energy).

## Changing things

- **Where things are stored:** all inside this folder. `apps/` and `bin/` hold
  the software, `models/` the model, `data/` your documents and chats. To keep
  only the model somewhere else, set `MODELS_DIR` in `settings.env`. To remove
  the assistant completely, stop it and delete this folder. Ollama also leaves
  a small `~/.ollama` folder on the Mac (an identity key, a few KB).
- **Model, port, context size:** `settings.env`, then `./privatellm restart`.
  After changing `CHAT_MODEL`, run `ollama pull <model>` and
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

These settings stop the software from calling out. They are not a firewall. If
you need proof for an audit, also block outbound traffic from the Mac.

Admins can read other people's chats. Tell your users.

## Tested and not tested

`tests/test_e2e.sh` runs the whole flow against a stand-in for the model:
start, configure, sync, a question finding the right document, the document
text reaching the model, a colleague signing up and being approved, and each
privacy switch reporting off. It passes on Linux with Open WebUI 0.13.3 and
oikb 0.6.0.

Not tested: anything on a real Mac, a real model's answers, and the cloud drive
connectors (they need your accounts). Expect to adjust something on first run.
