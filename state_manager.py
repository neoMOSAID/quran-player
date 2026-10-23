
"""State mixin: playback persistence + verse navigation."""

import configparser
import os
import tempfile

from quran_data import SURAH_AYAT, is_valid_verse


class StateMixin:
    def load_playback_state(self):
        state = configparser.ConfigParser()
        if not os.path.exists(self.state_file):
            return
        state.read(self.state_file)

        try:
            surah = state.getint('state', 'surah', fallback=1)
            ayah = state.getint('state', 'ayah', fallback=0)
            if self.is_valid_verse(surah, ayah):
                self.current_verse = (surah, ayah)
            else:
                self.current_verse = (1, 0)
        except (ValueError, TypeError) as e:
            self.log_action("ERROR", f"Corrupted state file: {e}. Using defaults")
            self.current_verse = (1, 0)

        try:
            repeat_on = state.getboolean('state', 'repeat', fallback=False)
        except (ValueError, TypeError):
            repeat_on = False
        if not repeat_on:
            return

        try:
            r_start = state.getint('state', 'repeat_start', fallback=-1)
            r_end = state.getint('state', 'repeat_end', fallback=-1)
        except (ValueError, TypeError) as e:
            self.log_action("WARNING", f"Corrupted repeat range: {e}. Repeat disabled")
            return

        surah, ayah = self.current_verse
        max_ayah = self.surah_ayat[surah]
        if not (0 <= r_start <= r_end <= max_ayah):
            self.log_action(
                "WARNING",
                f"Ignoring persisted repeat range {r_start}-{r_end} for "
                f"surah {surah} (valid: 0-{max_ayah})"
            )
            return

        self.repeat_range = (r_start, r_end)
        if not (r_start <= ayah <= r_end):
            self.current_verse = (surah, r_start)
            self.log_action(
                "WARNING",
                f"Restored ayah {ayah} was outside repeat range "
                f"{r_start}-{r_end}; resetting to ayah {r_start}"
            )
        self.log_action(
            "INFO", f"Restored repeat range {r_start}-{r_end} for surah {surah}"
        )

    def save_playback_state(self):
        surah, ayah = self.current_verse
        state = configparser.ConfigParser()
        row = {'surah': str(surah), 'ayah': str(ayah)}
        if self.repeat_range:
            row['repeat'] = 'yes'
            row['repeat_start'] = str(self.repeat_range[0])
            row['repeat_end'] = str(self.repeat_range[1])
        else:
            row['repeat'] = 'no'
        state['state'] = row
        state_dir = os.path.dirname(self.state_file) or '.'
        with tempfile.NamedTemporaryFile('w', delete=False, dir=state_dir) as tf:
            state.write(tf)
            temp_name = tf.name
        try:
            os.replace(temp_name, self.state_file)
        except OSError as e:
            self.log_action("ERROR", f"State save failed: {str(e)}")
            try:
                os.unlink(temp_name)
            except Exception:
                pass

    def is_valid_verse(self, surah, ayah):
        return is_valid_verse(surah, ayah)

    def get_next_verse(self):
        surah, ayah = self.current_verse
        if self.repeat_range:
            start, end = self.repeat_range
            next_ayah = ayah + 1
            if next_ayah > end:
                next_ayah = start
                if start == 0 and not self.audio_player.get_audio_path(surah, 0):
                    next_ayah = 1
            return (surah, next_ayah)
        next_ayah = ayah + 1
        max_ayah = self.surah_ayat[surah]
        if next_ayah > max_ayah:
            next_surah = surah + 1
            if next_surah > 114:
                next_surah = 1
            return (next_surah, 0)
        return (surah, next_ayah)

    def get_prev_verse(self):
        surah, ayah = self.current_verse
        if ayah == 0:
            prev_surah = surah - 1
            if prev_surah < 1:
                prev_surah = 114
            prev_ayah = self.surah_ayat[prev_surah]
            return (prev_surah, prev_ayah)
        return (surah, ayah - 1)


        