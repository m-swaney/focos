# Working with files (agent mode)

You have read access to the data dir and may only write to `reports/**`, `state/decisions.jsonl`, and
`state/sandbox/proposals/**`. Never edit `config/`, `agent/`, or anything else. Read the files the task
prompt lists before writing. Append decision entries to `state/decisions.jsonl` yourself (one JSON object
per line), and read its last 20 lines first.
