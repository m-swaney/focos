"""Shared fixtures. `home` gives every test an isolated data dir so nothing touches the developer's own
config, pointer file, or state."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _no_real_notifications(monkeypatch: pytest.MonkeyPatch):
    """No test may pop a toast on the developer's desktop or push to their phone. Tests that care about what
    would have been sent read `notify.SENT`."""
    from focos import notify

    sent: list[dict] = []
    monkeypatch.setattr(notify, "_toast", lambda title, body: sent.append({"title": title, "body": body}) or "ok")
    monkeypatch.setattr(notify, "_ntfy", lambda *a, **k: "ok")
    monkeypatch.delenv(notify.TOPIC_ENV, raising=False)
    monkeypatch.setattr(notify, "SENT", sent, raising=False)
    yield sent


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from focos import paths, settings

    fake_user_home = tmp_path / "user"
    fake_user_home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(fake_user_home))
    monkeypatch.setenv("HOME", str(fake_user_home))
    monkeypatch.delenv("FOCOS_REPO_ROOT", raising=False)
    for k in [k for k in os.environ if k.startswith("FOCOS_") and "__" in k]:
        monkeypatch.delenv(k, raising=False)
    # never let the developer's own secrets (loaded from their .env at import) reach a test
    for k in ("SIMPLEFIN_ACCESS_URL", "MERCURY_TOKEN",
              "RAPIDAPI_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "FOCOS_DASH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    h = tmp_path / "home"
    monkeypatch.setenv("FOCOS_HOME", str(h))
    paths.rebind(h)
    settings.reset()
    yield h
    paths.rebind()
    settings.reset()


@pytest.fixture
def initialized_home(home: Path) -> Path:
    from focos import settings
    from focos.config.init import init_home

    init_home(home)
    settings.reset()
    return home
