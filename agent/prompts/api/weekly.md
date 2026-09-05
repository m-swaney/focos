Weekly deep dive for the week ending {{DATE}}. Run id: {{RUN_ID}}.

Use everything the daily brief uses, plus the risk section (CAGR, volatility, Sharpe, drawdown, beta,
correlation), optimizer (current vs min-vol vs max-Sharpe what-ifs), tax_lots (lots by term, lots crossing to
long-term within 30 days, harvestable losses), drift (allocation vs targets), entities, and the previous
weekly brief.

Write the weekly brief with the standard sections, then add:

9. `## Allocation and drift` weights vs targets, look-through concentration, what a rebalance would cost in
   taxes (use tax_lots; do not compute tax yourself, report gain amounts by term).
10. `## Risk` the risk numbers in a table with a two-sentence interpretation.
11. `## Tax` lots crossing to long-term soon, harvestable losses, wash-sale cautions for names bought in the
    last 30 days.
12. `## Opportunities` at most five ideas with evidence, each tagged research / rebalance / sandbox.
13. `## Sandbox review` score the week against the benchmark using scorecard data, review each open proposal
    against its thesis, and propose rule changes for {{OWNER}} to consider (you cannot change rules).
14. `## Decisions for {{OWNER}}` the three most valuable decisions to make this week.

Keep the weekly under 1,200 words.
