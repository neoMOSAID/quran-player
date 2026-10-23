
"""Logging mixin: LOG_LEVELS table + log_action + log rotation."""

import inspect
import os
import threading
from datetime import datetime

from config_manager import config


LOG_LEVELS = {
    "CRITICAL": 50, "ERROR": 40, "WARNING": 30,
    "INFO": 20, "DEBUG": 10, "DISABLED": 0,
}

CRITICAL_FLAGS = {"CRITICAL", "ERROR"}


class LoggingMixin:
    def log_action(self, flag, msg):
        log_level_str = config.get("daemon", "LOG_LEVEL", "INFO").upper()
        log_level = LOG_LEVELS.get(log_level_str, 20)
        message_priority = LOG_LEVELS.get(flag, 20)
        if message_priority < log_level and flag not in CRITICAL_FLAGS:
            return

        method = inspect.currentframe().f_back.f_code.co_name
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        pid = os.getpid()
        log_entry = f"{timestamp}|{pid}|{method}|{flag}|{msg}\n"

        log_path = config.CLIENT_LOG_FILE if method == "handle_client" and flag == "ERROR" else config.LOG_FILE
        self.rotate_log_if_needed(log_path)

        try:
            with open(log_path, "a") as log:
                log.write(log_entry)
        except IOError as e:
            print(f"Failed to write to log: {str(e)}", file=__import__("sys").stderr)

    def rotate_log_if_needed(self, logfile):
        max_size = config.getint('daemon', 'MAX_LOG_SIZE', 1000000)
        with self.log_lock:
            try:
                if os.path.exists(logfile) and os.path.getsize(logfile) >= max_size:
                    rotated_log = f"{logfile}.1"
                    if os.path.exists(rotated_log):
                        os.remove(rotated_log)
                    os.rename(logfile, rotated_log)
                    with open(logfile, "w") as new_log:
                        new_log.write(f"{datetime.now().isoformat()}|SYSTEM|LOG|Rotated log file\n")
            except Exception as e:
                print(f"Log rotation failed: {str(e)}", file=__import__("sys").stderr)

                