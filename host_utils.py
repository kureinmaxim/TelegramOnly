# -*- coding: utf-8 -*-
"""
Утилиты для выполнения команд на хосте из Docker-контейнера.

Когда бот работает внутри Docker с ``pid: host``, хостовые команды
(systemctl, journalctl и т.д.) запускаются через ``nsenter`` в PID 1.
Вне Docker команды запускаются напрямую.
"""

import os
import subprocess
from typing import List


def is_docker() -> bool:
    """Detect if running inside a Docker container."""
    return os.path.exists("/.dockerenv") or bool(os.environ.get("DOCKER_CONTAINER"))


def host_run(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command on the host via nsenter if inside Docker.

    Requires ``pid: host`` in compose.yaml and ``user: "0:0"``.
    Falls back to direct subprocess.run() when not in Docker.
    """
    if is_docker():
        cmd = [
            "nsenter", "--target", "1",
            "--mount", "--uts", "--ipc", "--net", "--pid",
            "--",
        ] + cmd
    return subprocess.run(cmd, **kwargs)
