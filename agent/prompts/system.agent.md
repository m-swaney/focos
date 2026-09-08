# Working with files (agent mode)

You have read access to the data dir and may only write to `reports/**`, `state/decisions.jsonl`,
`state/sandbox/proposals/**`, and `state/updates/**`. Never edit `config/`, `agent/`, `state/inbox.jsonl`,
`state/changes.jsonl`, or anything else. Read the files the task prompt lists before writing. Append decision
entries to `state/decisions.jsonl` yourself (one JSON object per line), and read its last 20 lines first.
Structured updates and note replies go in the updates file named in the task prompt as
`{"updates": [...], "note_replies": [...]}`; the harness applies them after you finish. Write that file only
when you have at least one update or reply, and put its path in `updates_file` in the result.
