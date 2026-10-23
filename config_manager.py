
# config_manager.py
import os
import shutil
import configparser


class ConfigManager:
    def __init__(self):
        self._init_paths()
        self.config = self._load_config()
        self._ensure_directories()
        self._ensure_files()
        # Self-heal: if _load_config dropped anything stale (e.g. the
        # pre-2.0 [image] section), rewrite the file so the GUI and any
        # external reader see the cleaned version without waiting for
        # the next config.set() to overwrite it.
        if getattr(self, '_dropped_stale', False):
            self.save_config()

    def _load_config(self):
        config = configparser.ConfigParser()
        defaults = self._get_default_config()
        config.read_dict(defaults)

        self._dropped_stale = False
        if not os.path.exists(self.USER_CONFIG_FILE):
            return config

        user = configparser.ConfigParser()
        try:
            user.read(self.USER_CONFIG_FILE)
        except configparser.Error:
            # Corrupt file — fall back to defaults and rewrite.
            self._dropped_stale = True
            return config

        # Only copy sections/keys that still exist in the app's schema.
        # Unknown sections (e.g. the removed [image] block from pre-2.0)
        # and unknown keys within known sections are silently dropped,
        # so every save_config() produces a clean file.
        for section in user.sections():
            if not config.has_section(section):
                self._dropped_stale = True
                continue
            for key, value in user.items(section):
                if not config.has_option(section, key):
                    self._dropped_stale = True
                    continue
                config.set(section, key, value)
        return config

    def _init_paths(self):
        self.USER_CONFIG_DIR = os.path.expanduser("~/.config/quran-player")
        self.SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

        # Daemon control
        self.CONTROL_DIR = os.path.join(self.SCRIPT_DIR, "control")
        self.LOG_FILE = os.path.join(self.CONTROL_DIR, "daemon.log")
        self.CLIENT_LOG_FILE = os.path.join(self.CONTROL_DIR, "daemon-client.log")
        self.SOCKET_FILE = os.path.join(self.CONTROL_DIR, "daemon.sock")
        self.PID_FILE = os.path.join(self.CONTROL_DIR, "daemon.pid")
        self.LOCK_FILE = os.path.join(self.CONTROL_DIR, "daemon.lock")

        self.DEFAULT_CONFIG_FILE = os.path.join(self.SCRIPT_DIR, "default_config.ini")
        self.USER_CONFIG_FILE = os.path.join(self.USER_CONFIG_DIR, "config.ini")
        self.STATE_FILE = os.path.join(self.USER_CONFIG_DIR, "playback_state.ini")

        # Audio
        self.AUDIO_SOURCE_DIR = os.path.join(self.SCRIPT_DIR, "audio")
        self.SAMPLE_DIR = os.path.join(self.USER_CONFIG_DIR, "sample")

        # Conky widget (installed alongside the app)
        self.CONKY_DIR = os.path.join(self.SCRIPT_DIR, "conky")
        self.CONKY_CONFIG = os.path.join(self.CONKY_DIR, "conky_quran")

        self.REQUIRED_FILES = [
            "001000.mp3", "001001.mp3", "001002.mp3", "001003.mp3", "001004.mp3", "001005.mp3",
            "001006.mp3", "001007.mp3", "002000.mp3", "002001.mp3", "002002.mp3", "002003.mp3",
            "002004.mp3", "002005.mp3", "002006.mp3", "002007.mp3", "002008.mp3", "002009.mp3",
            "002010.mp3",
        ]

    def _ensure_directories(self):
        for directory in [self.USER_CONFIG_DIR, self.CONTROL_DIR, self.SAMPLE_DIR]:
            os.makedirs(directory, exist_ok=True)

    def _ensure_files(self):
        for filename in self.REQUIRED_FILES:
            dest = os.path.join(self.SAMPLE_DIR, filename)
            src = os.path.join(self.AUDIO_SOURCE_DIR, filename)
            if not os.path.exists(dest) and os.path.exists(src):
                shutil.copy2(src, dest)

    def _get_default_config(self):
        parser = configparser.ConfigParser()
        if os.path.exists(self.DEFAULT_CONFIG_FILE):
            parser.read(self.DEFAULT_CONFIG_FILE)

        defaults = {
            s: {k.lower(): v for k, v in parser.items(s)}
            for s in parser.sections()
        }
        defaults.setdefault("daemon", {})
        defaults.setdefault("conky", {})

        d = defaults["daemon"]
        d.setdefault("max_log_size", "1000000")
        d.setdefault("log_level", "INFO")
        if not d.get("files_directory"):
            d["files_directory"] = self.SAMPLE_DIR

        c = defaults["conky"]
        c.setdefault("enable", "yes")
        c.setdefault("executable", "")

        return defaults

    def get(self, section, key, default=None):
        try:
            return self.config.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default

    def reload(self):
        """Re-read config.ini from disk, dropping any stale sections."""
        self.config = self._load_config()
        if getattr(self, '_dropped_stale', False):
            self.save_config()
        return True

    def getboolean(self, section, key, default=False):
        try:
            return self.config.getboolean(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return default

    def getint(self, section, key, default=0):
        try:
            return self.config.getint(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return default

    def generate_default_config(self):
        """Write a fresh default config.ini, discarding current settings."""
        fresh = configparser.ConfigParser()
        fresh.read_dict(self._get_default_config())
        with open(self.USER_CONFIG_FILE, "w") as configfile:
            fresh.write(configfile)
        return True

    def set(self, section, key, value):
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, value)
        self.save_config()

    def save_config(self):
        with open(self.USER_CONFIG_FILE, "w") as configfile:
            self.config.write(configfile)


config = ConfigManager()

