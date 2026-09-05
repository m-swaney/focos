--
-- PostgreSQL database dump (trimmed fixture; no real data)
--

SET statement_timeout = 0;

COPY public.families (id, name) FROM stdin;
fam-1	Test Family
\.

COPY public.accounts (id, account_providers_count, accountable_id, accountable_type, balance, cash_balance, created_at, currency, disabled_at, enable_category_matcher, exclude_from_reports, family_id, import_id, institution_domain, institution_name, locked_attributes, name, notes, owner_id, plaid_account_id, simplefin_account_id, status, subtype, updated_at) FROM stdin;
acc-chk	1	dep-1	Depository	1500.0	1500.0	2024-09-04 00:00:00	USD	\N	f	f	fam-1	\N	examplebank.com	Example Bank	{}	Everyday Checking	\N	\N	\N	ACT-CHK-1	active	checking	2026-09-01 00:00:00
acc-card	1	cc-1	CreditCard	410.55	\N	2024-09-04 00:00:00	USD	\N	f	f	fam-1	\N	\N	Example Card	{}	Rewards Card	\N	\N	\N	ACT-CARD-1	active	\N	2026-09-01 00:00:00
acc-loan	0	loan-1	Loan	12000.0	\N	2024-09-04 00:00:00	USD	\N	f	f	fam-1	\N	\N	\N	{}	Student Loan	\N	\N	\N	\N	active	student	2026-09-01 00:00:00
acc-prop	0	prop-1	Property	350000.0	\N	2024-09-04 00:00:00	USD	\N	f	f	fam-1	\N	\N	\N	{}	Primary residence	\N	\N	\N	\N	active	\N	2026-09-01 00:00:00
acc-biz	1	dep-2	Depository	9000.0	9000.0	2024-09-04 00:00:00	USD	\N	f	f	fam-1	\N	mercury.com	Mercury	{}	Business Checking	\N	\N	\N	\N	active	checking	2026-09-01 00:00:00
\.

COPY public.balances (id, account_id, balance, cash_adjustments, cash_balance, cash_inflows, cash_outflows, created_at, currency, date, flows_factor, net_market_flows, non_cash_adjustments, non_cash_inflows, non_cash_outflows, start_cash_balance, start_non_cash_balance, updated_at) FROM stdin;
b-1	acc-chk	1200.0	0	1200.0	0	0	2026-01-01 00:00:00	USD	2026-01-01	1	0	0	0	0	0	0	2026-01-01 00:00:00
b-2	acc-chk	1500.0	0	1500.0	0	0	2026-01-02 00:00:00	USD	2026-01-02	1	0	0	0	0	0	0	2026-01-02 00:00:00
b-3	acc-card	410.55	0	\N	0	0	2026-01-02 00:00:00	USD	2026-01-02	1	0	0	0	0	0	0	2026-01-02 00:00:00
b-4	acc-loan	12000.0	0	\N	0	0	2026-01-02 00:00:00	USD	2026-01-02	1	0	0	0	0	0	0	2026-01-02 00:00:00
b-5	acc-prop	350000.0	0	\N	0	0	2026-01-02 00:00:00	USD	2026-01-02	1	0	0	0	0	0	0	2026-01-02 00:00:00
b-6	acc-biz	9000.0	0	9000.0	0	0	2026-01-02 00:00:00	USD	2026-01-02	1	0	0	0	0	0	0	2026-01-02 00:00:00
b-7	acc-chk	1000.0	0	1000.0	0	0	2025-06-01 00:00:00	USD	2025-06-01	1	0	0	0	0	0	0	2025-06-01 00:00:00
\.

COPY public.entries (id, account_id, amount, created_at, currency, date, entryable_id, entryable_type, excluded, external_id, import_id, import_locked, locked_attributes, name, notes, parent_entry_id, plaid_id, reconciled_at, reconciled_by_statement_id, source, updated_at, user_modified) FROM stdin;
e-1	acc-chk	52.1	2026-01-02 00:00:00	USD	2026-01-02	t-1	Transaction	f	ext-1	\N	f	{}	Grocery Mart	\N	\N	\N	\N	\N	simplefin	2026-01-02 00:00:00	f
e-2	acc-chk	-3000.0	2026-01-03 00:00:00	USD	2026-01-03	t-2	Transaction	f	ext-2	\N	f	{}	Payroll	Tab\tsafe	\N	\N	\N	\N	simplefin	2026-01-03 00:00:00	f
e-3	acc-chk	500.0	2026-01-04 00:00:00	USD	2026-01-04	t-3	Transaction	f	ext-3	\N	f	{}	Transfer to Business	\N	\N	\N	\N	\N	simplefin	2026-01-04 00:00:00	f
e-4	acc-biz	-500.0	2026-01-04 00:00:00	USD	2026-01-04	t-4	Transaction	f	ext-4	\N	f	{}	Transfer from Personal	\N	\N	\N	\N	\N	mercury	2026-01-04 00:00:00	f
e-5	acc-chk	9.99	2026-01-05 00:00:00	USD	2026-01-05	t-5	Transaction	t	ext-5	\N	f	{}	Excluded thing	\N	\N	\N	\N	\N	simplefin	2026-01-05 00:00:00	f
e-6	acc-prop	350000.0	2026-01-02 00:00:00	USD	2026-01-02	v-1	Valuation	f	\N	\N	f	{}	Valuation	\N	\N	\N	\N	\N	manual	2026-01-02 00:00:00	f
e-7	acc-chk	20.0	2025-06-01 00:00:00	USD	2025-06-01	t-7	Transaction	f	ext-7	\N	f	{}	Old coffee	\N	\N	\N	\N	\N	simplefin	2025-06-01 00:00:00	f
\.

COPY public.transactions (id, category_id, created_at, external_id, extra, investment_activity_label, kind, locked_attributes, merchant_id, transfer_id, updated_at) FROM stdin;
t-1	\N	2026-01-02 00:00:00	\N	{}	\N	standard	{}	\N	\N	2026-01-02 00:00:00
t-2	\N	2026-01-03 00:00:00	\N	{}	\N	standard	{}	\N	\N	2026-01-03 00:00:00
t-3	\N	2026-01-04 00:00:00	\N	{}	\N	funds_movement	{}	\N	tr-1	2026-01-04 00:00:00
t-4	\N	2026-01-04 00:00:00	\N	{}	\N	funds_movement	{}	\N	tr-1	2026-01-04 00:00:00
t-5	\N	2026-01-05 00:00:00	\N	{}	\N	standard	{}	\N	\N	2026-01-05 00:00:00
t-7	\N	2025-06-01 00:00:00	\N	{}	\N	standard	{}	\N	\N	2025-06-01 00:00:00
\.

COPY public.transfers (id, amount, created_at, inflow_transaction_id, notes, outflow_transaction_id, status, updated_at) FROM stdin;
tr-1	500.0	2026-01-04 00:00:00	t-4	\N	t-3	pending	2026-01-04 00:00:00
\.

--
-- PostgreSQL database dump complete
--
