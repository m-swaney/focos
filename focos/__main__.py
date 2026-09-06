import sys

if sys.stdout is None or sys.stderr is None:  # pythonw / Task Scheduler without a console
    from .windowless import attach

    attach(sys.argv)

from .cli import app  # noqa: E402

app()
