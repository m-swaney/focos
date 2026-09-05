Daily brief for {{DATE}}. Run id: {{RUN_ID}}.

Use the data sections below: profile and goals, alerts, portfolio (accounts, positions, weights, gains,
concentration, look-through, sectors), diff (changes since the previous snapshot), consolidated (entities
and cash when the ledger is connected), plan, sandbox (mode, positions, scorecard), sandbox_rules,
catalysts (earnings and news), the previous daily brief, and recent decisions.

Write the daily brief following the brief contract in your system prompt. Keep it under 500 words unless
something material happened. Do not repeat weekly deep-dive content; point to it if relevant.

Sandbox: in `paper` mode you may include at most `max_orders_per_run` proposal specs in the JSON block,
each with a specific, evidence-backed thesis; "no proposal" is a fine outcome and should be stated.
