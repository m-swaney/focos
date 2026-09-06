"""pythonw (Task Scheduler on Windows) gives focos no stdout/stderr; attach() must route both to a log file."""
import sys

from focos import paths, windowless


def test_attach_routes_missing_streams_to_home_log(home, monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    path = windowless.attach(["focos", "--home", str(home), "serve", "--with-dashboard"])
    assert path == home.resolve() / "state" / "logs" / "serve-windowless.log" and path.exists()
    assert sys.stdout is sys.stderr and sys.stdout is not None
    print("hello from a windowless run")
    sys.stdout.flush()
    assert "hello from a windowless run" in path.read_text(encoding="utf-8")
    assert paths.HOME == home.resolve()


def test_attach_is_a_noop_with_a_console(home):
    assert windowless.attach(["focos", "run", "--mode", "daily"]) is None


def test_command_and_home_parsing():
    assert windowless._command_from_argv(["focos", "--home", "X", "run", "--mode", "daily"]) == "run"
    assert windowless._command_from_argv(["focos", "--home=X", "serve"]) == "serve"
    assert windowless._home_from_argv(["focos", "--home=X", "serve"]) == "X"
    assert windowless._command_from_argv(["focos"]) == "focos"
