
"""Conky configuration: JSON storage + schema validation + Lua rendering.

The user-editable source of truth for conky display settings lives in
~/.config/quran-player/conky_config.json. Both the daemon (via socket
commands) and the GUI edit that file; the daemon validates it against
CONKY_SCHEMA and renders the Lua-syntax conky_quran that conky actually
reads on every start.
"""

import json
import os

from config_manager import config


class ConkyConfigError(ValueError):
    """Raised when conky config validation fails."""


# Defaults. Kept as plain Python so the JSON file is optional.
DEFAULT_CONKY_CONFIG = {
    "font": "Amiri:size=38",
    "update_interval": 0.5,
    "own_window_type": "override",
    "own_window_hints": "undecorated,below,sticky,skip_taskbar,skip_pager",
    "own_window_transparent": True,
    "own_window_argb_value": 200,
    "double_buffer": True,
    "minimum_width": 1165,
    "maximum_width": 1165,
    "default_color": "white",
    "alignment": "top_middle",
    "gap_x": 25,
    "gap_y": 140,
    "text_buffer_size": 2048,
    "max_lines": 6,
}

# Validation schema. Each entry describes type and constraints. Cross-field
# checks (min_width <= max_width) live in validate().
CONKY_SCHEMA = {
    "font":                   {"type": "str",    "nonempty": True},
    "update_interval":        {"type": "num",    "min": 0.1, "max": 60},
    "own_window_type":        {"type": "choice", "choices": [
        "normal", "desktop", "dock", "panel", "override"]},
    "own_window_hints":       {"type": "str"},
    "own_window_transparent": {"type": "bool"},
    "own_window_argb_value":  {"type": "int",    "min": 0, "max": 255},
    "double_buffer":          {"type": "bool"},
    "minimum_width":          {"type": "int",    "min": 100, "max": 16384},
    "maximum_width":          {"type": "int",    "min": 100, "max": 16384},
    "default_color":          {"type": "str",    "nonempty": True},
    "alignment":              {"type": "choice", "choices": [
        "top_left", "top_middle", "top_right",
        "middle_left", "middle_middle", "middle_right",
        "bottom_left", "bottom_middle", "bottom_right"]},
    "gap_x":                  {"type": "int",    "min": -16384, "max": 16384},
    "gap_y":                  {"type": "int",    "min": -16384, "max": 16384},
    "text_buffer_size":       {"type": "int",    "min": 256, "max": 65536},
    "max_lines":              {"type": "int",    "min": 1, "max": 12},
}


class ConkyConfigManager:
    def __init__(self):
        self.user_file = os.path.join(
            config.USER_CONFIG_DIR, "conky_config.json"
        )
        self.runtime_lua = config.CONKY_CONFIG

    # ------------------------------------------------------------------ load/save
    def load(self):
        """Load current conky config. Falls back to defaults on any error."""
        if not os.path.exists(self.user_file):
            return dict(DEFAULT_CONKY_CONFIG)
        try:
            with open(self.user_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return dict(DEFAULT_CONKY_CONFIG)
        merged = dict(DEFAULT_CONKY_CONFIG)
        if isinstance(data, dict):
            merged.update({k: v for k, v in data.items() if k in CONKY_SCHEMA})
        return merged

    def save(self, new_config):
        """Validate, persist as JSON, then render Lua. Returns normalized config.

        Raises ConkyConfigError if validation fails. Nothing is written in
        that case, so a bad save can't corrupt the runtime Lua.
        """
        normalized = self.validate(new_config)
        with open(self.user_file, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2)
            f.write("\n")
        self.render_lua(normalized)
        return normalized

    def reset(self):
        """Restore defaults (writes JSON + renders Lua). Returns defaults dict."""
        defaults = dict(DEFAULT_CONKY_CONFIG)
        with open(self.user_file, "w", encoding="utf-8") as f:
            json.dump(defaults, f, indent=2)
            f.write("\n")
        self.render_lua(defaults)
        return defaults

    # ------------------------------------------------------------------ validation
    def validate(self, candidate):
        """Validate candidate dict. Raises ConkyConfigError with all errors joined."""
        if not isinstance(candidate, dict):
            raise ConkyConfigError("Config must be a JSON object")

        errors = []
        normalized = {}

        for key, spec in CONKY_SCHEMA.items():
            if key not in candidate:
                normalized[key] = DEFAULT_CONKY_CONFIG[key]
                continue
            try:
                normalized[key] = self._validate_field(key, candidate[key], spec)
            except ConkyConfigError as e:
                errors.append(str(e))

        if errors:
            raise ConkyConfigError("\n".join(errors))

        if normalized["minimum_width"] > normalized["maximum_width"]:
            raise ConkyConfigError(
                f"minimum_width ({normalized['minimum_width']}) cannot exceed "
                f"maximum_width ({normalized['maximum_width']})"
            )

        return normalized

    def _validate_field(self, key, value, spec):
        typ = spec["type"]

        if typ == "bool":
            if not isinstance(value, bool):
                raise ConkyConfigError(f"{key}: expected boolean, got {type(value).__name__}")
            return value

        if typ == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ConkyConfigError(f"{key}: expected integer, got {type(value).__name__}")
            if "min" in spec and value < spec["min"]:
                raise ConkyConfigError(f"{key}: must be >= {spec['min']}, got {value}")
            if "max" in spec and value > spec["max"]:
                raise ConkyConfigError(f"{key}: must be <= {spec['max']}, got {value}")
            return value

        if typ == "num":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ConkyConfigError(f"{key}: expected number, got {type(value).__name__}")
            if "min" in spec and value < spec["min"]:
                raise ConkyConfigError(f"{key}: must be >= {spec['min']}, got {value}")
            if "max" in spec and value > spec["max"]:
                raise ConkyConfigError(f"{key}: must be <= {spec['max']}, got {value}")
            return value

        if typ == "str":
            if not isinstance(value, str):
                raise ConkyConfigError(f"{key}: expected string, got {type(value).__name__}")
            if spec.get("nonempty") and not value.strip():
                raise ConkyConfigError(f"{key}: cannot be empty")
            return value

        if typ == "choice":
            if not isinstance(value, str):
                raise ConkyConfigError(f"{key}: expected string, got {type(value).__name__}")
            if value not in spec["choices"]:
                raise ConkyConfigError(f"{key}: '{value}' not in {spec['choices']}")
            return value

        raise ConkyConfigError(f"{key}: unknown schema type {typ}")

    # ------------------------------------------------------------------ rendering
    def render_lua(self, cfg=None):
        """Render runtime conky_quran Lua from the JSON config."""
        if cfg is None:
            cfg = self.load()

        def lua_str(v):
            return "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"

        def lua_bool(v):
            return "true" if v else "false"

        lua = f"""conky.config = {{
    use_xft = true,
    font = {lua_str(cfg['font'])},
    update_interval = {cfg['update_interval']},
    own_window = true,
    own_window_type = {lua_str(cfg['own_window_type'])},
    own_window_hints = {lua_str(cfg['own_window_hints'])},
    own_window_transparent = {lua_bool(cfg['own_window_transparent'])},
    own_window_argb_visual = true,
    own_window_argb_value = {cfg['own_window_argb_value']},
    double_buffer = {lua_bool(cfg['double_buffer'])},
    minimum_width = {cfg['minimum_width']},
    maximum_width = {cfg['maximum_width']},
    default_color = {lua_str(cfg['default_color'])},
    alignment = {lua_str(cfg['alignment'])},
    gap_x = {cfg['gap_x']},
    gap_y = {cfg['gap_y']},
    override_utf8_locale = true,
    text_buffer_size = {cfg['text_buffer_size']},
}}

conky.text = [[
${{execpi 0.5 $HOME/.quran-player/conky/display_verse.sh}}
]]
"""
        os.makedirs(os.path.dirname(self.runtime_lua), exist_ok=True)
        try:
            with open(self.runtime_lua, "w", encoding="utf-8") as f:
                f.write(lua)
        except OSError as e:
            raise ConkyConfigError(f"Failed to write runtime Lua config: {e}")

    def render_json(self):
        return json.dumps(self.load(), indent=2) + "\n"

    def render_defaults_json(self):
        return json.dumps(DEFAULT_CONKY_CONFIG, indent=2) + "\n"


conky_config = ConkyConfigManager()
