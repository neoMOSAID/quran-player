
# audio_player.py
import os
import sys
import time
import threading

_PYGAME_AVAILABLE = False
_MIXER_AVAILABLE = False
_PYGAME_IMPORT_ERROR = None

try:
    import pygame  # noqa: F401
    _PYGAME_AVAILABLE = True
    try:
        import pygame.mixer  # noqa: F401
        _MIXER_AVAILABLE = True
    except (ImportError, NotImplementedError) as e:
        _PYGAME_IMPORT_ERROR = str(e)
except ImportError as e:
    _PYGAME_IMPORT_ERROR = str(e)


class AudioPlayer:

    def __init__(self, config, log_callback):
        self.config = config
        self.log_callback = log_callback
        self.lock = threading.Lock()
        self.state = "stopped"
        self.current_audio_path = None
        self._paused_at = 0.0
        self._idle_shutdown_seconds = 30.0

        # Respect the caller's SDL_AUDIODRIVER if set; otherwise default to
        # ALSA, which is 3x cheaper than the PulseAudio shim on PipeWire
        # systems (measured: 1.0% vs 3.2% idle). Users who know they want
        # pulseaudio (or pipewire on SDL 2.30+) can override via the env var.
        if _PYGAME_AVAILABLE:
            os.environ.setdefault('SDL_AUDIODRIVER', 'alsa')

        self.initialized = self.init_audio()

    def ensure_initialized(self):
        if self.initialized:
            return True
        if not self.init_audio():
            return False
        self.initialized = True
        return True

    def init_audio(self, max_retries=3, retry_delay=1):
        if not _PYGAME_AVAILABLE:
            self.log_callback(
                "CRITICAL",
                f"pygame is not importable in this venv ({_PYGAME_IMPORT_ERROR}). "
                "Run `python install.py --clean` from the source repo."
            )
            return False

        if not _MIXER_AVAILABLE:
            self.log_callback(
                "CRITICAL",
                f"pygame.mixer is unavailable ({_PYGAME_IMPORT_ERROR}). "
                "Fix: `<venv>/bin/pip install --force-reinstall pygame-ce`"
            )
            return False

        for attempt in range(max_retries):
            try:
                pygame.mixer.init(
                    frequency=44100, size=-16, channels=2,
                    buffer=1024,
                )
                self.log_callback("INFO", "Audio initialized successfully")
                return True
            except (pygame.error, NotImplementedError) as e:
                self.log_callback("ERROR", f"Audio init failed: {e}")
                time.sleep(retry_delay)

        self.log_callback("ERROR", "Failed to initialize audio after retries")
        return False

    def is_initialized(self):
        if not _MIXER_AVAILABLE:
            return False
        return pygame.mixer.get_init() is not None

    def is_busy(self):
        """True while audio is playing, False if stopped, None on mixer error."""
        if not self.is_initialized():
            return False
        try:
            return pygame.mixer.music.get_busy()
        except (pygame.error, NotImplementedError) as e:
            self.log_callback("WARNING", f"Audio busy check failed: {e}")
            return None

    def get_audio_path(self, surah, ayah):
        audio_file = f"{surah:03}{ayah:03}.mp3"
        path = os.path.join(self.config.get('daemon', 'FILES_DIRECTORY'), audio_file)
        return path if os.path.exists(path) else None

    def play(self, audio_path):
        with self.lock:
            if not self.ensure_initialized():
                return False
            try:
                if self.state == "paused":
                    pygame.mixer.music.unpause()
                    self.state = "playing"
                else:
                    pygame.mixer.music.load(audio_path)
                    pygame.mixer.music.play()
                    self.state = "playing"
                    self.current_audio_path = audio_path
                self._paused_at = 0.0
                return True
            except (pygame.error, NotImplementedError) as e:
                self.log_callback("ERROR", f"Playback failed: {e}")
                return False

    def pause(self):
        with self.lock:
            if self.state == "playing":
                try:
                    pygame.mixer.music.pause()
                    self.state = "paused"
                    self._paused_at = time.time()
                    return True
                except (pygame.error, NotImplementedError) as e:
                    self.log_callback("ERROR", f"Pause failed: {e}")
            return False 

    def maybe_shutdown_if_idle(self):
        """Tear down the mixer if the daemon has been paused for _idle_shutdown_seconds.

        Called from the daemon main loop. Releases PulseAudio / PipeWire / ALSA
        device handles so the process goes back to ~0% CPU while paused.
        The next play() call re-initializes the mixer transparently.
        """
        with self.lock:
            if self.state != "paused" or not self._paused_at:
                return
            if time.time() - self._paused_at <= self._idle_shutdown_seconds:
                return
            try:
                pygame.mixer.music.stop()
                if _MIXER_AVAILABLE and pygame.mixer.get_init():
                    pygame.mixer.quit()
            except Exception as e:
                self.log_callback("ERROR", f"Idle shutdown failed: {e}")
            self.state = "stopped"
            self.current_audio_path = None
            self.initialized = False
            self._paused_at = 0.0
            self.log_callback(
                "INFO",
                f"Audio device released after {self._idle_shutdown_seconds:.0f}s paused",
            )

    def stop(self):
        with self.lock:
            try:
                if self.is_initialized() and self.state != "stopped":
                    pygame.mixer.music.stop()
                self.state = "stopped"
                self.current_audio_path = None
                return True
            except Exception as e:
                self.log_callback("ERROR", f"Stop failed: {e}")
                return False

    def toggle_pause(self):
        if self.state == "paused":
            return self.play(self.current_audio_path)
        return self.pause()

    def cleanup(self):
        try:
            self.stop()
            if _MIXER_AVAILABLE and pygame.mixer.get_init():
                pygame.mixer.quit()
        except Exception as e:
            self.log_callback("ERROR", f"Cleanup error: {e}")

            