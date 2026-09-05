"""Ledger layer: entity mapping, transfer netting, consolidated net worth and cash flow.

Internal normalized transaction shape used throughout this package:
{
  "id": str, "date": "YYYY-MM-DD", "account_id": str, "account_name": str,
  "amount": float,            # signed: positive = inflow/income, negative = outflow/expense
  "name": str, "merchant": str | None, "category": str | None, "tags": [str],
  "transfer_id": str | None, "other_account_id": str | None,
  "external_id": str | None, "source": str | None,
}
"""
