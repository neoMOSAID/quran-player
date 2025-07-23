# audio_player.py
import os
import sys
import time
import pygame
import threading
import logging

class AudioPlayer:

    def __init__(self, config, log_callback):
        self.config = config
        self.log_callback = log_callback
        self.lock = threading.Lock()
        self.state = "stopped"  # stopped, playing, paused
        self.current_audio_path = None
        self.initialized = False
        
        # Initialize pygame audio
        os.environ['SDL_AUDIODRIVER'] = self.get_audio_driver()
        self.init_audio()
        

    def get_audio_driver(self):
        """Determine appropriate audio driver for platform"""
        if sys.platform == "darwin":
            return "coreaudio"
        if sys.platform.startswith("linux"):
            return "pulseaudio"
        return "dummy"  # Fallback

    def ensure_initialized(self):
        """Initialize audio only if not already initialized"""
        if self.initialized:
            return True
            
        if not self.init_audio():
            self.log_callback("CRITICAL", "Audio initialization failed")
            return False
            
        self.initialized = True
        return True

    def init_audio(self, max_retries=3, retry_delay=1):
        """Initialize audio system with retry logic"""
        # Initialize only the mixer, not the full pygame
        for attempt in range(max_retries):
            try:
                # Initialize only the audio mixer
                pygame.mixer.init(
                    frequency=44100,
                    size=-16,
                    channels=2,
                    buffer=1024,
                    allowedchanges=0
                )
                self.log_callback("INFO", "Audio initialized successfully")
                return True
            except pygame.error as e:
                self.log_callback("ERROR", f"Audio init failed: {str(e)}")
                time.sleep(retry_delay)
        
        self.log_callback("ERROR", "Failed to initialize audio after retries")
        return False

    def is_initialized(self):
        """Check if audio system is ready"""
        return pygame.mixer.get_init() is not None

    def get_audio_path(self, surah, ayah):
        """Get path to audio file using current config"""
        audio_file = f"{surah:03}{ayah:03}.mp3"
        # Always get fresh path from config
        path = os.path.join(self.config.get('daemon', 'FILES_DIRECTORY'), audio_file)
        return path if os.path.exists(path) else None

    def play(self, audio_path):
        """Start or resume playback"""
        with self.lock:
            if not self.ensure_initialized():
                return False
                    
            try:
                if self.state == "paused":
                    pygame.mixer.music.unpause()
                    self.state = "playing"
                else:
                    # Always load new audio when stopped or starting fresh
                    pygame.mixer.music.load(audio_path)
                    pygame.mixer.music.play()
                    self.state = "playing"
                    self.current_audio_path = audio_path
                return True
            except pygame.error as e:
                self.log_callback("ERROR", f"Playback failed: {str(e)}")
                return False

    def pause(self):
        """Pause current playback"""
        with self.lock:
            if self.state == "playing":
                try:
                    pygame.mixer.music.pause()
                    self.state = "paused"
                    return True
                except pygame.error as e:
                    self.log_callback("ERROR", f"Pause failed: {str(e)}")
            return False

    def stop(self):
        """Stop playback and reset state"""
        with self.lock:
            try:
                if self.is_initialized() and self.state != "stopped":
                    pygame.mixer.music.stop()
                self.state = "stopped"
                self.current_audio_path = None
                return True
            except Exception as e:
                self.log_callback("ERROR", f"Stop failed: {str(e)}")
                return False

    def toggle_pause(self):
        """Toggle between play and pause states"""
        if self.state == "paused":
            return self.play(self.current_audio_path)
        return self.pause()

    def cleanup(self):
        """Release audio resources"""
        try:
            self.stop()
            if pygame.mixer.get_init():
                pygame.mixer.quit()
        except Exception as e:
            self.log_callback("ERROR", f"Cleanup error: {str(e)}")