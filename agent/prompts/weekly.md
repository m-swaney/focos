Weekly deep dive for the week ending {{DATE}}. Run id: {{RUN_ID}}.

Read everything the daily brief reads (same file list), plus:

- `state/derived/latest/risk.json` (CAGR, volatility, Sharpe, drawdown, beta, correlation summary)
- `state/derived/latest/optimizer.json` (current vs min-vol vs max-Sharpe what-ifs)
- `state/derived/latest/tax_lots.json` (lots by term, lots crossing to long-term within 30 days, harvestable losses)
- `state/derived/latest/drift.json` (allocation vs targets in profile.yml, when targets exist)
- The last 5 daily briefs in `reports/daily/` and the previous weekly brief `{{PREV_BRIEF}}`
- `state/derived/latest/scan.json` if present (opportunity scan results)

Write `reports/weekly/{{WEEK}}.md`. Use the standard sections, then add:

9. `## Allocation and drift` weights vs targets, look-through concentration, what a rebalance would
   cost in taxes (use tax_lots.json; do not compute tax yourself, report gain amounts by term).
10. `## Risk` the risk.json numbers in a table with a two-sentence interpretation.
11. `## Tax` lots crossing to long-term soon, harvestable losses, wash-sale cautions for names bought
    in the last 30 days.
12. `## Opportunities` at most five ideas with evidence, each tagged research / rebalance / sandbox.
    You may use `get_equity_fundamentals`, `get_equity_news`, and `get_equity_quotes` to check facts.
13. `## Sandbox review` score the week against SPY using scorecard data, review each open proposal
    against its thesis, and propose rule changes for {{OWNER}} to consider (you cannot change rules).
14. `## Decisions for {{OWNER}}` the three most valuable decisions to make this week.

Keep the weekly under 1,200 words. Append decisions to `state/decisions.jsonl` and return the
structured result.
