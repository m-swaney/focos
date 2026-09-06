"""Orphaned dashboard children must not survive a stop and keep holding the port."""
from __future__ import annotations

import json
import subprocess
import sys
import time

from focos import paths
from focos.service import supervisor


def test_reap_kills_a_recorded_child(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS", tmp_path / "logs")
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        (tmp_path / "logs").mkdir(parents=True)
        supervisor._children_file().write_text(json.dumps([{"pid": proc.pid, "exe": sys.executable}]), encoding="utf-8")
        assert supervisor.reap_orphans() == [proc.pid]
        for _ in range(50):
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        assert proc.poll() is not None, "the orphan was not killed"
        assert not supervisor._children_file().exists()
    finally:
        if proc.poll() is None:
            proc.kill()


def test_reap_leaves_a_recycled_pid_alone(tmp_path, monkeypatch):
    """A pid that now belongs to a different program must never be killed."""
    monkeypatch.setattr(paths, "LOGS", tmp_path / "logs")
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        (tmp_path / "logs").mkdir(parents=True)
        supervisor._children_file().write_text(
            json.dumps([{"pid": proc.pid, "exe": "some-other-program.exe"}]), encoding="utf-8")
        assert supervisor.reap_orphans() == []
        assert proc.poll() is None, "an unrelated process was killed"
    finally:
        proc.kill()


def test_reap_without_a_record_is_a_no_op(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LOGS", tmp_path / "logs")
    assert supervisor.reap_orphans() == []
