Monthly plan review for {{MONTH}}. Run id: {{RUN_ID}}.

Read everything the weekly brief reads, plus:

- `state/derived/latest/plan.json` (savings rate, contribution pacing, emergency fund coverage,
  debt schedule, deterministic retirement projection percentiles, goal funding status)
- `state/derived/latest/consolidated.json` and `entities.json` when present
- The previous monthly brief `{{PREV_BRIEF}}` and all weekly briefs from the month

Write `reports/monthly/{{MONTH}}.md`. Use the standard sections, then add:

9. `## Net worth by entity` consolidated and per entity, with the month's change and inter-entity
   flows shown separately.
10. `## Cash flow and savings rate` income, spending by category (top categories and the uncategorized
    share), observed vs configured core spend from `consolidated.json` `spending`, savings rate vs the profile.
11. `## Goals` each goal's funding status and whether it is on pace.
12. `## Retirement projection` the plan.json percentiles with a plain reading of what they mean and
    the two assumptions that matter most.
13. `## Debt vs invest` when debts exist, compare payoff against expected returns using plan.json.
14. `## Business` owner-draw pacing and tax set-aside estimate for each entity, flagged as estimates.
15. `## Plan for next month` at most five concrete moves.
16. `## Questions for {{OWNER}}` at most three questions whose answers would most improve this model
    (missing profile fields, unexplained flows, open items in the tax agenda or active goals). Skip anything
    the changes log or a `done` status shows is settled. They answer through notes; ask only what matters.

Keep the monthly under 1,500 words. Handle every note in `inbox.json`; write structured updates and note
replies to `state/updates/{{RUN_ID}}.json` when you have any. Append decisions to `state/decisions.jsonl`
and return the structured result.
