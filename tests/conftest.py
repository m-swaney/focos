"""Shared fixtures. `home` gives every test an isolated data dir so nothing touches the developer's own
config, pointer file, or state."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


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
    for k in ("SURE_API_KEY_RW", "SURE_API_KEY_RO", "SURE_API_URL", "SIMPLEFIN_ACCESS_URL", "MERCURY_TOKEN",
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
