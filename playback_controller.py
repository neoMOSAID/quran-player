
"""Playback mixin: play/pause/next/prev, load/goto/repeat, dir change."""

import os
import shutil
import subprocess

import quran_search
from config_manager import config


class PlaybackMixin:

    def handle_dir(self, path):
        if not os.path.isdir(path):
            self.error_msg = f"Invalid directory: {path}"
            self.log_action("ERROR", self.error_msg)
            return False
        config.set('daemon', 'FILES_DIRECTORY', path)
        self.audio_base = path
        if self.audio_player.state in ("playing", "paused") and self.current_verse:
            self.log_action("INFO", f"Reloading audio from new directory: {path}")
            current_verse = self.current_verse
            self.audio_player.stop()
            return self.play_verse(current_verse)
        return True

    def handle_playback_end(self):
        if self.audio_player.state != "playing":
            return True
        with self.state_lock:
            next_verse = self.get_next_verse()
            if next_verse:
                self.current_verse = next_verse
                self.save_playback_state()
        if next_verse:
            return self.play_verse(next_verse)
        return False

    def handle_playback_events(self):
        if self.audio_player.state == "playing":
            busy = self.audio_player.is_busy()
            if busy is None:
                self.log_action("WARNING", "Audio system error, reinitializing")
                self.audio_player.init_audio()
            elif not busy:
                # handle_playback_end may fail if the next verse has no audio;
                # play_verse() already logs, but make it visible at WARNING.
                self.error_msg = ""   # discard any stale client error
                if not self.handle_playback_end():
                    self.log_action(
                        "WARNING",
                        f"Auto-advance stopped at {self.current_verse[0]}:{self.current_verse[1]}"
                    )

    def play_verse(self, verse):
        surah, ayah = verse
        audio_path = self.audio_player.get_audio_path(surah, ayah)
        if not audio_path:
            self.error_msg = (
                f"Audio file not found: {surah:03}{ayah:03}.mp3 in "
                f"{self.audio_base} (use 'quran-daemon dir <path>' to change)"
            )
            self.log_action("ERROR", f"Audio file not found: {surah:03}{ayah:03}.mp3")
            return False

        if ayah:
            quran_text = quran_search.get_verse_text(surah, ayah)
        else:
            quran_text = "بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ"

        self._write_verse_file(quran_text)
        if not self.audio_player.play(audio_path):
            self.error_msg = "Playback failed (audio system error; see log)"
            return False
        return True

    def handle_play(self):
        if self.audio_player.state == "paused":
            if not self.audio_player.play(self.audio_player.current_audio_path):
                self.error_msg = "Failed to resume playback (audio system error)"
                return False
            return True
        return self.play_verse(self.current_verse)

    def handle_pause(self):
        if self.audio_player.state != "playing":
            self.error_msg = f"Nothing is playing (state: {self.audio_player.state})"
            return False
        if not self.audio_player.pause():
            self.error_msg = "Pause failed (audio system error)"
            return False
        return True

    def handle_resume(self):
        return self.handle_play()

    def handle_toggle(self):
        if self.audio_player.state == "stopped":
            return self.play_verse(self.current_verse)
        if not self.audio_player.toggle_pause():
            self.error_msg = "Toggle failed (audio system error)"
            return False
        return True

    def handle_next(self):
        next_verse = self.get_next_verse()
        if next_verse:
            self.current_verse = next_verse
            self.save_playback_state()
            return self.play_verse(next_verse)
        return False

    def handle_prev(self):
        prev_verse = self.get_prev_verse()
        if prev_verse:
            self.current_verse = prev_verse
            self.save_playback_state()
            return self.play_verse(prev_verse)
        return False

    def handle_goto(self, ayah_str):
        try:
            ayah = int(ayah_str)
        except ValueError:
            self.error_msg = "Invalid ayah number"
            self.log_action("ERROR", self.error_msg)
            return False

        current_surah, _ = self.current_verse
        max_ayat = self.surah_ayat[current_surah]
        if ayah < 0 or ayah > max_ayat:
            self.error_msg = f"Invalid ayah {ayah} for Surah {current_surah} (0-{max_ayat})"
            self.log_action("ERROR", self.error_msg)
            return False
        if ayah == 0 and not self.audio_player.get_audio_path(current_surah, 0):
            self.error_msg = f"Surah {current_surah} has no bismillah audio"
            return False
        if self.repeat_range:
            start, end = self.repeat_range
            if ayah < start or ayah > end:
                self.error_msg = f"Ayah {ayah} not in repeat range ({start}-{end})"
                self.log_action("ERROR", self.error_msg)
                return False
        if not self.audio_player.get_audio_path(current_surah, ayah):
            self.error_msg = f"Audio file not found: {current_surah:03}{ayah:03}.mp3"
            self.log_action("ERROR", self.error_msg)
            return False

        self.current_verse = (current_surah, ayah)
        self.save_playback_state()
        if self.audio_player.state in ("playing", "paused"):
            self.audio_player.stop()
            return self.play_verse(self.current_verse)
        return True

    def handle_load(self, args):
        try:
            parts = args.split(':')
            if len(parts) == 1:
                surah = int(parts[0])
                if not (1 <= surah <= 114):
                    raise ValueError("Invalid surah number")
                ayah = 0 if surah != 9 else 1
                if ayah == 0 and not self.audio_player.get_audio_path(surah, 0):
                    ayah = 1
                self.current_verse = (surah, ayah)
            elif len(parts) == 2:
                surah, ayah = map(int, parts)
                if not self.is_valid_verse(surah, ayah):
                    raise ValueError(
                        f"Invalid verse: surah={surah} ayah={ayah} "
                        f"(surah must be 1-114; ayah must be 0-{self.surah_ayat[surah] if 1 <= surah <= 114 else '?'})"
                    )
                self.current_verse = (surah, ayah)
            else:
                raise ValueError(f"Expected 'surah' or 'surah:ayah', got '{args}'")
            self.repeat_range = None
            self.save_playback_state()
            return self.play_verse(self.current_verse)
        except ValueError as e:
            self.error_msg = f"Invalid load argument: {e}"
            self.log_action("ERROR", self.error_msg)
            return False

    def handle_ns(self):
        current_surah, _ = self.current_verse
        next_surah = (current_surah % 114) + 1
        starting_ayah = 0
        if next_surah == 9:
            starting_ayah = 1
        elif not self.audio_player.get_audio_path(next_surah, 0):
            starting_ayah = 1
        return self._load_surah(next_surah, starting_ayah)

    def handle_ps(self):
        current_surah, _ = self.current_verse
        prev_surah = current_surah - 1
        if prev_surah < 1:
            prev_surah = 114
        starting_ayah = 0
        if prev_surah == 9:
            starting_ayah = 1
        elif not self.audio_player.get_audio_path(prev_surah, 0):
            starting_ayah = 1
        return self._load_surah(prev_surah, starting_ayah)

    def _load_surah(self, surah, starting_ayah):
        # ns/ps are surah navigation; clear repeat like `load` does.
        self.repeat_range = None
        self.current_verse = (surah, starting_ayah)
        self.save_playback_state()
        return self.play_verse(self.current_verse)

    def handle_repeat_off(self):
        with self.state_lock:
            if self.repeat_range is not None:
                self.repeat_range = None
                self.save_playback_state()
                self.log_action("INFO", "Repeat mode turned off")
            return True

    def handle_repeat(self, args):
        if args.lower() == "off":
            return self.handle_repeat_off()

        parts = args.split(':')
        try:
            if len(parts) == 1:
                surah = int(parts[0])
                if not (1 <= surah <= 114):
                    raise ValueError("Invalid surah number")
                if surah != 9:
                    start = 0 if self.audio_player.get_audio_path(surah, 0) else 1
                else:
                    start = 1
                end = self.surah_ayat[surah]
                current_surah = surah
            elif len(parts) == 2:
                current_surah, _ = self.current_verse
                start = int(parts[0])
                end = int(parts[1])
            elif len(parts) == 3:
                surah = int(parts[0])
                start = int(parts[1])
                end = int(parts[2])
                if not (1 <= surah <= 114):
                    raise ValueError("Invalid surah number")
                current_surah = surah
            else:
                raise ValueError("Invalid number of arguments")
        except ValueError as e:
            self.error_msg = f"Invalid repeat argument: {e}"
            self.log_action("ERROR", self.error_msg)
            return False

        if self.audio_player.state in ("playing", "paused"):
            self.audio_player.stop()

        max_ayat = self.surah_ayat[current_surah]
        if start == 0:
            if current_surah == 9:
                self.error_msg = "Surah 9 has no bismillah"
                self.log_action("ERROR", self.error_msg)
                start = 1
            if end < 0:
                end = 0
        else:
            if start < 1 or end > max_ayat:
                self.error_msg = f"Invalid range {start}-{end} for Surah {current_surah} (1-{max_ayat})"
                self.log_action("ERROR", self.error_msg)
                return False

        if start > end:
            self.error_msg = f"Start verse {start} > end verse {end}"
            self.log_action("ERROR", self.error_msg)
            return False

        for ayah in range(start, end + 1):
            if not self.audio_player.get_audio_path(current_surah, ayah):
                self.error_msg = f"Missing audio file {current_surah}:{ayah}"
                self.log_action("ERROR", self.error_msg)
                return False

        self.repeat_range = (start, end)
        self.current_verse = (current_surah, start)
        self.save_playback_state()
        return self.play_verse(self.current_verse)

    def verify_audio_config(self):
        if shutil.which("pactl") is None:
            self.log_action("WARNING", "pactl not found — skipping audio server check")
            return True
        try:
            result = subprocess.run(['pactl', 'info'], capture_output=True, text=True, timeout=2)
            if result.returncode != 0:
                self.log_action("ERROR", "PulseAudio/PipeWire not running!")
                return False
            for line in result.stdout.splitlines():
                if line.lower().startswith("server name:"):
                    self.log_action("INFO", f"Audio server: {line.split(':', 1)[1].strip()}")
                    break
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            self.log_action("WARNING", "Could not verify audio server — continuing")
            return True

