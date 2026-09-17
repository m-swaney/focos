Read the current state of the Agentic account only, using the broker's read tools. This is a live pre-trade
read during market hours, not the daily snapshot: be quick and do not look at any other account.

1. `get_accounts` — find the account whose agentic trading is allowed. That is the only account in scope.
2. `get_portfolio` / `get_accounts` — its cash, buying power, and total value.
3. `get_equity_positions` — its equity positions, with quantity and shares available for sells.
4. `get_equity_quotes` — the current price for every symbol it holds.
5. `get_equity_orders` — any of its orders still open or queued today.

Return ONLY this JSON object. No prose, no markdown fences, no commentary:

```
{
  "account_number": "full account number of the Agentic account",
  "portfolio": {"total_value": number, "cash": number, "buying_power": number},
  "positions": [
    {"symbol": "AAPL", "quantity": number, "sellable": number, "price": number, "avg_cost": number}
  ],
  "quotes": [{"symbol": "AAPL", "last": number}],
  "open_orders": [{"symbol": "AAPL", "side": "buy", "quantity": number, "state": "queued"}]
}
```

Rules: every number is a plain JSON number, not a string and not formatted with `$` or commas. Empty arrays
where there is nothing to report — never null. If a quote is unavailable for a held symbol, omit it from
`quotes` rather than guessing; sizing will fall back to the last snapshot.
