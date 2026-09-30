# focos: notes for coding agents

This repository is the whole application. A household's config, state, and reports live in a separate data
folder (resolved by `FOCOS_HOME`, then `~/.focos/home.txt`); nothing personal belongs in this repo, and
`scripts/private_scan.py` (run by CI) enforces that. Use made-up names, institutions, and amounts in tests.

## Shape

- One process, `focos serve`: the dashboard (Next.js standalone, `dashboard/`), the local API
  (`focos/api/`), intraday re-pricing, and the heartbeat (`focos/heartbeat.py`) that runs every scheduled job
  from the table in `focos/scheduler/base.py:run_jobs()` as its own subprocess, with catch-up after sleep.
- The OS runs exactly one task (`scheduler.app_job()`): start at login, watchdog every minute. Installing it
  (`focos schedule install`, also run by every update) removes the per-job tasks older versions used.
- Updates: `focos update` installs a release next to the current one and repoints `~/.focos/app.txt`; the
  running app sees the pointer change and exits with code 75 once its current job ends, and the OS starts it
  again on the new version.
- A run is Stage A (holdings snapshot via the broker MCP), Stage B (deterministic pipeline), Stage C (brief).
  `--mode trade` is the intraday trading pass; its exits are decided in code (`focos/sandbox/exits.py`) and
  every order goes through the PreToolUse gate (`focos/sandbox/gate.py`, rules in `focos/sandbox/rules.py`).
- What needs the owner is one list built in code (`focos/needs_you.py`); notifications go through
  `focos/notify.py`.

## Working here

- `.venv\Scripts\python -m pytest -q` (or `.venv/bin/python`). Python is `python`/`py` on Windows, never `python3`.
- A checkout's heartbeat is off (`heartbeat.enabled()`), so `focos serve` from here never runs jobs against a
  real data folder. Do not run `focos run ...` against someone's real data from a checkout: a run writes state
  and may commit and push it.
- Never place, cancel, or exercise orders outside the sandbox rules; the PreToolUse gate is authoritative.
- Never write full account numbers anywhere except a data folder's `state/raw/`.
- Numbers in briefs come from `state/derived/latest/*.json`; prompts forbid computing new figures in prose.

## Releasing

Bump `version` in `pyproject.toml`, commit, push, then push the tag `v<version>`. The release workflow runs the
tests and the private-data scan, builds the dashboard and the bundle, and publishes the release.
