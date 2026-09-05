# focos

**Family Office Chief of Staff.** A private financial assistant that runs on your own computer: it reads your
bank, card, loan, and brokerage data, runs deterministic analytics, and asks an AI of your choice to write you a
short brief every day, a deep dive every week, and a plan review every month. Nothing is hosted; your data
never leaves your machine except the summary figures sent to the AI provider you pick.

```
holdings snapshot ─┐
bank/card/loan     ├─ Python pipeline ─ derived JSON ─ AI brief (Anthropic / OpenAI / Gemini / Ollama)
ledger (SimpleFIN) ┘                        │
                                       dashboard  http://localhost:3100
```

## Install

Windows (PowerShell, no admin):

```powershell
irm https://raw.githubusercontent.com/m-swaney/focos/main/installers/install.ps1 | iex
```

macOS:

```sh
curl -fsSL https://raw.githubusercontent.com/m-swaney/focos/main/installers/install.sh | sh
```

The installer puts the app under `~/.focos/app-<version>` with its own Python and Node runtimes, creates your
data folder at `~/focos-home`, registers the dashboard to start at login, and opens the setup wizard at
`http://localhost:3100/setup`. Setup takes about ten minutes:

1. **AI**: paste one API key (Anthropic, OpenAI, or Gemini) or point at a local Ollama.
2. **Banks**: create a SimpleFIN Bridge account (about $1.50/month), connect your institutions, paste the setup token.
3. **Accounts**: confirm which accounts belong to the household or to a business, and which brokerage accounts to analyze.
4. **Holdings**: use the feed's holdings, enter a short table, or skip.
5. **Profile**: a five-minute interview with your AI fills in income, spending, debts, retirement, and goals. You confirm every proposal.
6. **Schedule**: pick the times. Windows Task Scheduler or macOS launchd runs it while you are logged in.
7. **First run**: watch it produce the first brief.

## What you get

- `reports/daily/<date>.md`, `reports/weekly/<week>.md`, `reports/monthly/<month>.md`: the briefs, in plain markdown.
- A dashboard: Today, Wealth (net worth by entity, cash flow), Portfolio (weights, risk, drift, tax lots), Plan
  (savings rate, emergency fund, contributions, retirement projection, goals), Briefs, Health.
- `state/derived/latest/*.json`: every number the AI is allowed to quote, computed deterministically in Python.
- A local git history of your data folder, committed after every run (no remote unless you add one).

## Your data folder

```
~/focos-home/
  config/     focos.yml profile.yml goals.yml accounts.yml entities.yml transfer_rules.yml ...  (yours to edit)
  .env        API keys and the SimpleFIN access URL  (never committed)
  state/      ledger.sqlite, snapshots, derived JSON, run status, logs
  reports/    the briefs
```

Full account numbers are never stored outside `state/raw/` (which is git-ignored); everything else uses last-4
masks. Run `focos doctor` any time, or open the Health page; `focos doctor --export` writes a redacted
diagnostics zip you can share when asking for help.

## Everyday commands

```
focos run --mode daily          # one full cycle now
focos ledger refresh            # pull the bank feed
focos holdings capture          # refresh holdings
focos ai test                   # check the AI key
focos schedule status           # what is scheduled
focos doctor                    # health checks with fixes
focos update                    # install the newest release
```

`focos --home <dir> ...` targets a different data folder.

## Advanced

- **Agent mode** (`ai.mode: agent` in `config/focos.yml`): if Claude Code is installed, the brief writer reads the
  data files itself and can connect Robinhood's MCP server for live holdings, plus an optional, code-gated
  trading sandbox (`config/sandbox_rules.yml`, off by default). See `agent/prompts/`.
- **Mercury**: business accounts that do not sync through SimpleFIN can be read straight from Mercury with a
  read-only API token (Setup > Banks, or `focos ledger mercury --token ...`).
- **Config schema**: `focos config validate` checks every file; `focos config schema` exports JSON Schema.

## Developing

```
git clone https://github.com/m-swaney/focos && cd focos
uv venv .venv --python 3.13 && uv pip install --python .venv -e ".[dev,all]"
.venv/Scripts/python -m pytest          # or .venv/bin/python on macOS
cd dashboard && npm ci && npm run dev   # http://localhost:3100
```

`scripts/private_scan.py` scans the tree for secrets and personal data; CI runs it on every push. Please keep
real account names, institutions, and amounts out of tests and fixtures.

## Safety model

- The pipeline is read-only. In agent mode the only tool that can move money is the sandbox order tool, which
  is gated by `focos.sandbox.gate` (account, size, weight, cash floor, frequency, proposal, approval) and off
  unless you enable it.
- The AI never sees account numbers or raw transactions; it gets derived figures and the profile you confirmed.
- Every number in a brief must come from `state/derived/latest`; the prompts forbid computing new figures.

## License

MIT
