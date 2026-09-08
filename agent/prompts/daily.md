Daily brief for {{DATE}}. Run id: {{RUN_ID}}.

Read these files first (paths are relative to the repo root):

- `config/profile.yml`, `config/goals.yml`, `config/sandbox_rules.yml`
- `state/derived/latest/portfolio.json` (accounts, positions, weights, gains, concentration, look-through, sectors, tax split)
- `state/derived/latest/diff.json` (changes since the previous snapshot)
- `state/derived/latest/alerts.json` (rule-based alerts)
- `state/derived/latest/catalysts.json` (earnings and news pulled this run)
- `state/derived/latest/sandbox.json` (mode, positions, scorecard, run counter)
- `state/derived/latest/consolidated.json` if it exists (entities and cash; absent until the ledger is live)
- `state/derived/latest/inbox.json` (notes from {{OWNER}} for you, recent changes, open tax items, active goals)
- The previous daily brief: `{{PREV_BRIEF}}` (may not exist)
- The last 20 lines of `state/decisions.jsonl` (may not exist)

Then write `reports/daily/{{DATE}}.md` following the brief contract in your system prompt. Keep the
daily brief under 500 words unless something material happened. Do not repeat the weekly deep-dive
content; point to it if relevant.

Sandbox: mode is in `sandbox.json`. In `paper` mode you may write at most
`max_orders_per_run` proposal files to `state/sandbox/proposals/{{DATE}}-<symbol>-<side>.json` with
fields `ref_id, date, symbol, side, dollar_amount, thesis, entry_reason, stop_loss, exit_plan,
horizon_days, paper: true`. Only propose when you have a specific, evidence-backed reason; "no
proposal" is a fine outcome and should be stated. In `live` mode, follow the same proposal step, then
use `review_equity_order` and `place_equity_order` only for proposals that pass the gate.

Notes and updates: handle every note in `inbox.json` per your system prompt. Write structured updates and
note replies to `state/updates/{{RUN_ID}}.json` when you have any.

Finish by appending decisions to `state/decisions.jsonl` and returning the structured result.
