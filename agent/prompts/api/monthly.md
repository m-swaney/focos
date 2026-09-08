Monthly plan review for {{MONTH}}. Run id: {{RUN_ID}}.

Use everything the weekly brief uses, plus the plan section (savings rate, contribution pacing, emergency
fund coverage, debt schedule, retirement projection percentiles, goal funding status), consolidated and
entities, and the previous monthly brief.

Write the monthly brief with the standard sections, then add:

9. `## Net worth by entity` consolidated and per entity, with the month's change and inter-entity flows
   shown separately.
10. `## Cash flow and savings rate` income, spending by category (top categories and the uncategorized
    share), observed vs configured core spend from the consolidated `spending` block, savings rate vs the profile.
11. `## Goals` each goal's funding status and whether it is on pace.
12. `## Retirement projection` the plan percentiles with a plain reading of what they mean and the two
    assumptions that matter most.
13. `## Debt vs invest` when debts exist, compare payoff against expected returns using the plan data.
14. `## Business` owner-draw pacing and tax set-aside estimate for each business entity, flagged as estimates
    (one line "No business entities." when there are none).
15. `## Plan for next month` at most five concrete moves.
16. `## Questions for {{OWNER}}` at most three questions whose answers would most improve this model
    (missing profile fields, unexplained flows, open items in the tax agenda or active goals). Skip anything
    the changes log or a `done` status shows is settled.

Keep the monthly under 1,500 words.
