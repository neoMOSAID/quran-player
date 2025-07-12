


# config_manager.py
import os
import sys
import configparser
from pathlib import Path

class ConfigManager:
    def __init__(self):
        self._init_paths()
        self.config = self._load_config()
        self._ensure_directories()
        self._ensure_files()
        self.CLIENT_LOG_FILE = os.path.join(self.CONTROL_DIR, "daemon-client.log")  # Fixed typo

        
    def _init_paths(self):
        """Initialize all important paths"""
        # Determine OS-specific paths
        if sys.platform.startswith("win"):
            base_dir = os.environ.get("APPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Roaming"))
            self.USER_CONFIG_DIR = os.path.join(base_dir, "quran-player")
        elif sys.platform == "darwin":
            self.USER_CONFIG_DIR = os.path.expanduser("~/Library/Application Support/quran-player")
        else:
            self.USER_CONFIG_DIR = os.path.expanduser("~/.config/quran-player")
        
        # Script directory
        self.SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
        
        # Daemon control files
        self.CONTROL_DIR = os.path.join(self.SCRIPT_DIR, "control")
        self.LOG_FILE = os.path.join(self.CONTROL_DIR, "daemon.log")
        self.CLIENT_LOG_FILE = os.path.join(self.CONTROL_DIR, "daemon-client.log")
        
        if sys.platform == 'win32':
            self.SOCKET_FILE = r'\\.\pipe\quran-daemon'
        else:
            self.SOCKET_FILE = os.path.join(self.CONTROL_DIR, "daemon.sock")
            
        self.PID_FILE = os.path.join(self.CONTROL_DIR, "daemon.pid")
        self.LOCK_FILE = os.path.join(self.CONTROL_DIR, "daemon.lock")
        self.DEFAULT_CONFIG_FILE = os.path.join(self.SCRIPT_DIR, "default_config.ini")
        
        # User files
        self.USER_CONFIG_FILE = os.path.join(self.USER_CONFIG_DIR, "config.ini")
        
        if sys.platform == "win32":
            self.STATE_FILE = os.path.join(os.environ["APPDATA"], "quran-player", "playback_state.ini")
        else:
            self.STATE_FILE = os.path.join(self.USER_CONFIG_DIR, "playback_state.ini")
            
        # Audio files
        self.AUDIO_SOURCE_DIR = os.path.join(self.SCRIPT_DIR, "audio")
        self.SAMPLE_DIR = os.path.join(self.USER_CONFIG_DIR, "sample")
        
        # Required files
        self.REQUIRED_FILES = [
            "001000.mp3", "001001.mp3", "001002.mp3", "001003.mp3", "001004.mp3", "001005.mp3", 
            "001006.mp3", "001007.mp3", "002000.mp3", "002001.mp3", "002002.mp3", "002003.mp3", 
            "002004.mp3", "002005.mp3", "002006.mp3", "002007.mp3", "002008.mp3", "002009.mp3", 
            "002010.mp3"
        ]
        
    def _ensure_directories(self):
        """Create required directories if they don't exist"""
        for directory in [self.USER_CONFIG_DIR, self.CONTROL_DIR, self.SAMPLE_DIR]:
            os.makedirs(directory, exist_ok=True)
            
    def _ensure_files(self):
        """Copy required files to their destinations if missing"""
        # Copy audio files
        for filename in self.REQUIRED_FILES:
            dest = os.path.join(self.SAMPLE_DIR, filename)
            src = os.path.join(self.AUDIO_SOURCE_DIR, filename)
            if not os.path.exists(dest) and os.path.exists(src):
                shutil.copy2(src, dest)
        
        # Copy Arabic font
        font_dest = os.path.join(self.USER_CONFIG_DIR, "arabic-font.ttf")
        font_src = os.path.join(self.SCRIPT_DIR, "arabic-font.ttf")
        if not os.path.exists(font_dest) and os.path.exists(font_src):
            shutil.copy2(font_src, font_dest)
    
    def _load_config(self):
        """Load configuration from defaults and user config"""
        config = configparser.ConfigParser()
        
        # Load default configuration
        config.read_dict(self._get_default_config())
        
        # Load user config if available
        if os.path.exists(self.USER_CONFIG_FILE):
            config.read(self.USER_CONFIG_FILE)
            
        return config
    
    def _get_default_config(self):
        """Return default configuration values"""
        return {
            "daemon": {
                "MAX_LOG_SIZE": "1000000",
                "LOG_LEVEL": "INFO",
                "FILES_DIRECTORY": self.SAMPLE_DIR,
            },
            "image": {
                "ENABLE": "yes",
                "DEFAULT_RESOLUTION": "1240x170",
                "FONT_FILE": os.path.join(self.USER_CONFIG_DIR, "arabic-font.ttf"),
                "FONT_SIZE": "48",
                "IMAGE_WIDTH": "1240",
                "WRAP_WIDTH": "170",
                "VERTICAL_PADDING": "20",
                "BG_COLOR": "0,0,0,0",
                "TEXT_COLOR": "255,255,255,255",
                "HIGHLIGHT_COLOR": "255,0,0,255",
            }
        }
    
    def get(self, section, key, default=None):
        """Get a configuration value with fallback to default"""
        try:
            return self.config.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default
    
    def getboolean(self, section, key, default=False):
        """Get a boolean configuration value"""
        try:
            return self.config.getboolean(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return default
    
    def getint(self, section, key, default=0):
        """Get an integer configuration value"""
        try:
            return self.config.getint(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return default
    
    def generate_default_config(self):
        """Write default configuration to user config file"""
        with open(self.USER_CONFIG_FILE, "w") as configfile:
            self.config.write(configfile)
        return True

    def set(self, section, key, value):
        """Set a configuration value and save to file"""
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, value)
        self.save_config()

    def save_config(self):
        """Save configuration to user config file"""
        with open(self.USER_CONFIG_FILE, "w") as configfile:
            self.config.write(configfile)

# Singleton instance for easy access
config = ConfigManager()