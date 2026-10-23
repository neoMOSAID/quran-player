
"""Module-level helpers that operate on the daemon's pid/lock/socket files."""

import os
import portalocker
from config_manager import config


def is_daemon_running():
    if not os.path.exists(config.LOCK_FILE):
        return False
    try:
        with open(config.LOCK_FILE, 'a') as f:
            try:
                portalocker.lock(f, portalocker.LOCK_EX | portalocker.LOCK_NB)
                portalocker.unlock(f)
                return False
            except (IOError, OSError, portalocker.LockException):
                return True
    except Exception:
        return False


def cleanup_orphaned_files():
    if not is_daemon_running():
        for f in [config.PID_FILE, config.SOCKET_FILE]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception as e:
                    print(f"Cleanup warning: {str(e)}")
                    