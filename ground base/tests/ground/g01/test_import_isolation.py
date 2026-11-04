"""Ordinary imports must not load hardware SDKs or open sockets."""

from __future__ import annotations

import subprocess
import sys

from patrol.ground.kernel.paths import repo_root


def test_kernel_import_does_not_open_a_socket_or_load_sdks() -> None:
    script = """
import socket
import sys

class Guard(socket.socket):
    def __init__(self, *args, **kwargs):
        raise RuntimeError("socket opened during import")

socket.socket = Guard
import patrol.ground.kernel
import patrol.ground.sim
banned = {"djitellopy", "unitree_webrtc_connect", "go2_webrtc_connect", "xai_sdk", "xai"}
loaded = banned & set(sys.modules)
if loaded:
    raise SystemExit("loaded " + ",".join(sorted(loaded)))
print("ok")
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        cwd=repo_root(),
    )
    assert completed.returncode == 0, completed.stderr
    assert "ok" in completed.stdout
