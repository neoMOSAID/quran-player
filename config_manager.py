
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
            val = self.config.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default
        # An empty value in the file means "use the documented default".
        if val == "" and default is not None:
            return default
        return val
        
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
        """Reset config.ini to defaults (preserves schema comments + header)."""
        fresh = configparser.ConfigParser()
        fresh.read_dict(self._get_default_config())
        self.config = fresh
        with open(self.USER_CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(self.render_template())
        return True

    def set(self, section, key, value):
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, value)
        self.save_config()

    def save_config(self):
        with open(self.USER_CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(self.render_template())

    def render_template(self):
        """Render default_config.ini with current values substituted.

        Keys whose current effective value differs from the default are shown
        uncommented, with the active value. Keys at their default are commented
        out, so the user sees the full schema without clutter.
        """
        if not os.path.exists(self.DEFAULT_CONFIG_FILE):
            from io import StringIO
            buf = StringIO()
            self.config.write(buf)
            return buf.getvalue()

        default_effective = self._get_default_config()
        with open(self.DEFAULT_CONFIG_FILE, 'r', encoding='utf-8') as f:
            template = f.read()

        out = []
        section = None
        for line in template.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(';') or stripped.startswith('#'):
                out.append(line)
                continue
            if stripped.startswith('[') and stripped.endswith(']'):
                section = stripped[1:-1].strip()
                out.append(line)
                continue
            if '=' in line and section is not None:
                key, _, tmpl_default = line.partition('=')
                key = key.strip()
                indent = line[:len(line) - len(line.lstrip())]
                schema_default = default_effective.get(section, {}).get(
                    key.lower(), tmpl_default.strip()
                )
                current = self.config.get(section, key, fallback=schema_default)
                if str(current) == str(schema_default):
                    out.append(f"{indent}# {key} = {tmpl_default.strip()}")
                else:
                    out.append(f"{indent}{key} = {current}")
                continue
            out.append(line)

        header = (
            "; delete the \"#\" at the start of the line to enable\n"
            "; the config value\n"
            "\n"
        )
        return header + '\n'.join(out) + '\n'

    def render_defaults(self):
        """Render default_config.ini with every key spelled out at its
        effective default value. Used by the GUI 'Restore Defaults' button.

        Unlike render_template() (which comments out keys at their default),
        this shows all keys with active values so the user sees a complete
        config to edit.
        """
        defaults = self._get_default_config()
        out = []
        if os.path.exists(self.DEFAULT_CONFIG_FILE):
            with open(self.DEFAULT_CONFIG_FILE, "r", encoding="utf-8") as f:
                template_lines = f.read().splitlines()
            section = None
            for line in template_lines:
                stripped = line.strip()
                if not stripped or stripped.startswith(";") or stripped.startswith("#"):
                    out.append(line)
                    continue
                if stripped.startswith("[") and stripped.endswith("]"):
                    section = stripped[1:-1].strip()
                    out.append(line)
                    continue
                if "=" in line and section is not None:
                    key = line.split("=", 1)[0].strip()
                    indent = line[:len(line) - len(line.lstrip())]
                    value = defaults.get(section, {}).get(key.lower(), "")
                    out.append(f"{indent}{key} = {value}")
                    continue
                out.append(line)
        else:
            for section, keys in defaults.items():
                out.append(f"[{section}]")
                for k, v in keys.items():
                    out.append(f"{k} = {v}")
                out.append("")
        return "\n".join(out) + "\n"

    def validate_ini(self, text):
        """Validate INI text. Returns (ok, error_message).

        Checks: parseable INI, only known sections/keys, semantic values
        for log_level / max_log_size / conky.enable.
        """
        try:
            user = configparser.ConfigParser()
            user.read_string(text)
        except configparser.Error as e:
            return False, f"Syntax error: {e}"

        defaults = self._get_default_config()
        errors = []
        for section in user.sections():
            if section not in defaults:
                errors.append(f"Unknown section: [{section}]")
                continue
            for key in user.options(section):
                if key not in defaults[section]:
                    errors.append(f"Unknown key: [{section}] {key}")

        if user.has_option("daemon", "log_level"):
            lvl = user.get("daemon", "log_level").upper()
            valid = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "DISABLED"}
            if lvl not in valid:
                errors.append(
                    f"[daemon] log_level must be one of {sorted(valid)}, got '{lvl}'"
                )

        if user.has_option("daemon", "max_log_size"):
            try:
                sz = user.getint("daemon", "max_log_size")
                if sz < 1024:
                    errors.append(f"[daemon] max_log_size must be >= 1024, got {sz}")
            except ValueError:
                errors.append("[daemon] max_log_size must be an integer")

        if user.has_option("conky", "enable"):
            try:
                user.getboolean("conky", "enable")
            except ValueError:
                errors.append("[conky] enable must be yes/no/true/false/1/0")

        if errors:
            return False, "\n".join(errors)
        return True, ""

config = ConfigManager()

