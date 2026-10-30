<p align="center"><img src="docs/img/logo.png" width="120" alt="Nodus logo"></p>

<h1 align="center">Nodus</h1>

<p align="center"><b>An autonomous AI agent for engineering calculations, file work and research.<br>It runs on your own machine and works with free API tiers.</b></p>

<p align="center"><b>English</b> · <a href="README.tr.md">Türkçe</a></p>

<p align="center">
  <a href="https://github.com/mbmakes/Nodus/actions/workflows/tests.yml"><img src="https://github.com/mbmakes/Nodus/actions/workflows/tests.yml/badge.svg" alt="tests"></a>
  <a href="https://github.com/mbmakes/Nodus/releases"><img src="https://img.shields.io/github/v/release/mbmakes/Nodus?include_prereleases&label=release" alt="latest release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license"></a>
  <img src="https://img.shields.io/badge/python-3.12%20%7C%203.13-3776AB.svg" alt="Python 3.12 | 3.13">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg" alt="Windows | macOS | Linux">
</p>

> **Status: v1.11-beta.** Close to daily use, but not widely tested yet. See [Limits](#limits-and-beta-notes) for what to keep in mind.
> The interface and the agent's default replies are in **Turkish** for now; an English interface is on the [roadmap](#roadmap). The agent understands English tasks.

![Calculation sheet: step log, equations and tables](docs/img/hesap-foyu.png)

## What it does

You describe a task; Nodus plans it, picks the right tool, does the calculation and presents the result with units, equations and tables. Every risky step (running code, deleting files) **asks for your approval first**.

Example tasks:

- *"Water at 20 °C flows at 5 L/s through a smooth 50 mm pipe, 100 m long. What is the pressure drop?"*
- *"A 2 m cantilever beam with a 40×40 mm square steel section carries 500 N at its tip. Find the deflection and stress."*
- *"Give me the saturated steam table between 1 and 10 bar, with enthalpy and entropy."*
- Upload an Excel/PDF/Word/CSV file: *"Analyse the trend in this data."*
- Upload a technical drawing: *"Find the maximum deflection of the beam in the figure."*

## Highlights

| | |
|---|---|
| **Verified calculations** | Pipe pressure drop (Darcy-Weisbach + Colebrook-White), beam deflection and stress, saturated steam tables, pump/fan power, shaft torsion, bolt check, multi-layer wall heat transfer, heat exchanger (LMTD), Euler column buckling, orifice flow, bearing life (L10), psychrometrics, NPSH, thin-wall pressure vessels and fatigue (Goodman). The model never writes formulas from memory: it calls the unit-tested functions of the `eng_calc` tool. Out-of-range inputs (for example "water" that is actually steam at the given state) are flagged instead of silently computed. |
| **Multi-provider router** | Chooses between Gemini, Groq, OpenRouter, Cerebras and Mistral by task type, and falls back automatically when a quota runs out or a provider stops answering. |
| **Cross-checking** | For heavy tasks the answer is reviewed by a model from a different provider. If it objects, the calculation is redone once with the objection attached. |
| **Approval gate** | Code, shell commands, file deletion and persistent memory writes need your approval. The approval screen shows the code that will *actually* run, including referenced files. |
| **Stop button** | Stops a running task at any moment and kills the code or command process it started. |
| **Step log** | Every task's tool steps and timings are stored with the conversation. |
| **Reports** | Turns an answer into a Word (.docx) or PDF report in one click, figures embedded. |
| **File and image input** | Drag and drop, paste or button; PDF, Excel, Word, CSV, PNG/JPG. Voice input if you have a Groq key. |
| **Local and private** | The interface listens on `127.0.0.1` only. Conversations and notes stay on your disk. |
| **Light and dark theme** | A full-screen interface inspired by engineering blueprints; works on phones and tablets. |

![While a task runs: the stop button](docs/img/calisiyor-durdur.png)

## Installation

### One-line install (recommended)

You do not need to install anything first; Nodus fetches Python itself if needed.

**macOS / Linux**: open a terminal, paste, press Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/mbmakes/Nodus/master/install.sh | bash
```

On macOS this also creates `~/Applications/Nodus.app`: open it from Launchpad or Spotlight (⌘Space → Nodus) and drag it to the Dock. The app is built on your own Mac, so Gatekeeper does not complain. Running the same command again on an existing install adds the icon.

**Windows**: open PowerShell, paste, press Enter:

```powershell
irm https://raw.githubusercontent.com/mbmakes/Nodus/master/install.ps1 | iex
```

The command downloads the latest release into `~/Nodus` (Windows: `%USERPROFILE%\Nodus`). **If Python 3.12 is missing, it installs a portable copy inside that folder, without admin rights** (via [uv](https://github.com/astral-sh/uv); the SHA-256 of the download is verified), installs the libraries and starts Nodus. On first launch a **key dialog** appears: paste a free [Gemini key](https://aistudio.google.com/apikey), it is validated and saved, so you never have to edit `.env` by hand. Next time, `run_nodus.bat` (Windows) or `bash run_nodus.sh` (macOS/Linux) in that folder is enough. If you prefer to read the scripts first: [`install.sh`](install.sh), [`install.ps1`](install.ps1).

### Getting your free key (about 1 minute)

Nodus needs an AI provider key, and it has to be your own: each person's free quota belongs to their account. The first-run dialog walks you through it, and it needs no credit card:

1. Click **Open key page** in the dialog (or go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)) and sign in with a Google account.
2. Click **Create API key** and copy the long text it shows.
3. Paste it into the dialog (or press **Paste from clipboard**). Nodus recognises which provider the key belongs to, checks that it works and saves it on your computer only.

Want more free quota? Open **Settings → Add / change key** and add Groq, OpenRouter, Cerebras or Mistral keys the same way; Nodus spreads the load across them.

### Manual install

Requirements: **Python 3.12 or 3.13** (on Windows the launcher installs it for you) and at least one provider key (free tiers are enough). You can paste the key into the first-run dialog instead of writing it into `.env`.

**Windows**

```bash
git clone https://github.com/mbmakes/Nodus.git
cd Nodus
copy .env.example .env      # then put your keys into .env
run_nodus.bat
```

**macOS / Linux** *(macOS is verified by automated tests on GitHub's macOS runner; the window, microphone and screen permissions have not been tried by hand on a real Mac, see [Limits](#limits-and-beta-notes))*

```bash
git clone https://github.com/mbmakes/Nodus.git
cd Nodus
cp .env.example .env        # then put your keys into .env
bash run_nodus.sh
```

Python **3.12** is required (a Mac's own `python3` is usually too old and Homebrew's may be too new): `brew install python@3.12`. The launcher finds `python3.12` itself; to force another one use `PYTHON=python3.12 bash run_nodus.sh`. On first launch a `.venv` is created and the libraries are installed into it (a few minutes the first time). If macOS says the file cannot be verified after unzipping, use `bash run_nodus.sh`; to double-click `run_nodus.command` you may first need to right-click and choose "Open". Voice input needs the browser's microphone permission, and the screenshot tool may need macOS "Screen Recording" permission.

The launchers install missing libraries, start the server and open the interface as an app window in Edge/Chrome (`http://127.0.0.1:8765`), or in your default browser if neither is found. If the port is taken by another program, the next free one is used.

Keys (`.env`), at least one is required:

| Variable | Where to get it |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio |
| `GROQ_API_KEY` | console.groq.com (also needed for voice input) |
| `OPENROUTER_API_KEY` | openrouter.ai |
| `CEREBRAS_API_KEY` | cloud.cerebras.ai |
| `MISTRAL_API_KEY` | console.mistral.ai |

Optional environment variables: `NODUS_PORT` (default 8765), `NODUS_NO_WINDOW=1` (do not open a window), `NODUS_WORKSPACE` (workspace folder), `NODUS_MEMORY_DIR` (memory folder), `NODUS_SANDBOX=docker` (run code inside Docker), `NODUS_OLLAMA=1` (also use a local Ollama server), `NODUS_NO_UPDATE_CHECK=1`.

Command line: `python main.py "your task"` · Legacy Streamlit interface: `run_nodus_classic.bat` (installs Streamlit on first use).

## Updating

When Nodus starts it checks GitHub for the latest release (in the background, at most every half hour). If there is a newer one, a dialog shows the **version number and release notes**:

> *Nodus 1.1-beta is out. Update now?* **[Update now]** **[Later]**

"Update now" downloads and applies it in one click, then Nodus restarts itself and the page refreshes. To check by hand: **Settings → Version → Check for updates**.

- **Your data is kept:** `.env` (your keys), `memory/` (tasks, notes, rules), `workspace/`, `custom_tools/` are never touched.
- **Rollback copy:** the old versions of changed files go to `.update_backup/`; if a step fails, everything is restored automatically.
- **If you installed with git,** the update uses `git` (fast-forward only; with local changes it does nothing and warns you). With a zip install the release archive is downloaded and unpacked over the folder.
- **Privacy and safety:** the check sends one request to GitHub (GitHub sees your IP address, nothing else is sent). Only `github.com/mbmakes/Nodus` releases are accepted; the archive is validated before anything is written (unsafe paths are rejected). The archive has no digital signature; trust rests on GitHub's HTTPS and this repository.
- **To turn it off:** set `NODUS_NO_UPDATE_CHECK=1` in `.env` or the environment.
- No update starts while a task is running.

> v1.0-beta does not have this feature; moving from it to a newer version needs one manual step (`git pull` or a fresh zip). Later versions update from inside the app.

## How it works

```
Browser (web/)  ──SSE──►  server.py (Starlette)
                              │
                       orchestrator.py   ReAct loop, approval policy, cancel
                              │
              ┌───────────────┼────────────────┐
         agent_core.py    providers.py       tools.py
         system prompt    model router       tool registry,
         tool calls       quota / health     file access policy, sandbox
                                                  │
                                              engcalc.py  verified calculations
```

- **ReAct loop:** the model calls a tool, sees the result and continues, for at most 12 steps. If the same action repeats 3 times the loop is cut.
- **Tools:** `eng_calc`, `open_app`, `save_user_file`, `execute_code`, `solve_math`, `web_search`, `fetch_url`, `browse_url`, `read_document`, `read_file`/`write_file`/`apply_patch`, `export_report`, `update_plan`, `remember`/`recall` and more.
- **Memory:** persistent rules ("use SI units"), notes (SQLite) and conversation history live in the local `memory/` folder.

![Start screen and templates](docs/img/baslangic.png)

## Security model

- **File access:** the agent's file tools work anywhere on the computer (relative paths are relative to the workspace). **Critical places ask for approval**, even with "run without approval" switched on: system folders, config and key folders such as `.ssh`/`.aws`, secret files such as `.env`/`.pem`/`id_rsa`, overwriting an existing file, and (after web content has been read) any access outside the workspace. The file tools never read Nodus's own `.env` and cannot write into the Nodus folder. Code or a command you approve, however, can do both, so do not approve code without reading it. The web interface's file service still looks only inside the workspace.
- **Approval policy:** by default, running code or commands and deleting files ask first. If you switch on "Run code without approval" (the choice is remembered), Python code and shell commands run without asking; deleting files still asks. After content from the internet or a document has been read, approval is required even then (protection against prompt injection).
- **Local server:** only `127.0.0.1`/`localhost` Host headers, a custom header plus same-origin on state-changing requests, strict CSP. SVG/HTML is never served inline.
- **Sub-processes** run without your API keys, inside the workspace, with a timeout.

> ⚠️ **With the Docker sandbox off,** approved code runs on your machine with your user account's rights. Do not approve code without reading it. For strong isolation install Docker and add `NODUS_SANDBOX=docker` to `.env` (`sandbox/Dockerfile`).

Found a vulnerability? Please follow [SECURITY.md](SECURITY.md).

## Tests

```bash
python -m pytest tests -q -p no:cacheprovider      # 107 tests
```

They cover agent and tool behaviour, the security policy, the server endpoints (a real uvicorn with a fake model), stopping and process killing, reports, search and calculation accuracy against hand calculations. GitHub Actions runs them on Windows, macOS and Linux on every push, together with the launcher and installer smoke tests.

## Limits and beta notes

- Tried by hand and automatically on **Windows**. On **macOS** all tests and the launcher smoke test pass on GitHub Actions (`macos-latest`), but the window, microphone and screenshot permissions have not been tried on a real Mac. If you hit a problem, open an issue.
- Code and command execution is not isolated at the operating-system level unless Docker is set up.
- Model answers can be wrong. The ready calculations (`eng_calc`) and cross-checking reduce this but do not remove it. Verify results independently for anything critical.
- Free provider tiers can run out of quota; Nodus falls back to another provider, but replies may get slower.
- Voice input sends audio to Groq.
- Gas-phase pipe results assume incompressible flow and are only valid for small pressure drops; Nodus warns when that is violated.

## Roadmap

- English interface and replies by default
- More verified calculations (pipe networks, thick-wall vessels, welded joints)
- Docker sandbox on by default when Docker is available
- Interactive previews for charts inside answers
- Verifying macOS support on real hardware

## Contributing

Bug reports, ideas and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 mbmakes

Use it, change it and share it as you like. One small request: if it helped you, a thank-you (or a ⭐ on the repo) is plenty. Keeping the copyright line from the license is enough.
