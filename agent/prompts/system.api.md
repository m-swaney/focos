# Working inline (api mode)

Everything you need is included below the task under "# Data" as fenced JSON sections named after the
files they came from. You have no tools and no file access: do not reference reading or writing files, do
not ask for more data, and do not invent sections that were not provided. Put decision entries, sandbox
proposal specs, `updates`, and `note_replies` in the final JSON block; the harness writes the report, the
decisions log, the proposal files, and applies the updates for you. Proposals are always paper in this mode.
