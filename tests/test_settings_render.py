import json
from pathlib import Path

from focos import paths
from focos.agent_runtime import settings_render
from focos.sandbox.brokers.robinhood import PLACE, REVIEW, RobinhoodAdapter


def test_render_writes_hooks_with_this_interpreter(initialized_home: Path):
    files = settings_render.render(RobinhoodAdapter(), python="C:/venv/Scripts/python.exe")
    doc = json.loads(files["settings"].read_text(encoding="utf-8"))
    assert files["settings"] == paths.HOME_AGENT / "settings.headless.json"
    pre = doc["hooks"]["PreToolUse"][0]
    assert pre["matcher"] == f"{PLACE}|{REVIEW}"
    cmd = pre["hooks"][0]["command"]
    assert cmd.startswith('"C:/venv/Scripts/python.exe" -m focos.sandbox.gate --home "')
    assert paths.HOME.as_posix() in cmd
    post = doc["hooks"]["PostToolUse"][0]
    assert post["matcher"] == PLACE and "focos.sandbox.journal" in post["hooks"][0]["command"]
    assert "Bash" in doc["permissions"]["deny"] and PLACE not in doc["permissions"]["deny"]
    mcp = json.loads(files["mcp"].read_text(encoding="utf-8"))
    assert "robinhood-trading" in mcp["mcpServers"]
    assert files["system_prompt"] == paths.AGENT / "prompts" / "system.md"


def test_default_python_is_current_interpreter(initialized_home: Path):
    files = settings_render.render(RobinhoodAdapter())
    cmd = json.loads(files["settings"].read_text())["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "python" in cmd.lower() and "\\" not in cmd.split(" -m ")[0]
