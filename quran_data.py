
"""Static Quran metadata shared across modules."""

# Surah -> number of ayahs. Index 0 is unused (there is no surah 0).
SURAH_AYAT = [
    0,
    7,   286, 200, 176, 120, 165, 206, 75,  129, 109,
    123, 111, 43,  52,  99,  128, 111, 110, 98,  135,
    112, 78,  118, 64,  77,  227, 93,  88,  69,  60,
    34,  30,  73,  54,  45,  83,  182, 88,  75,  85,
    54,  53,  89,  59,  37,  35,  38,  29,  18,  45,
    60,  49,  62,  55,  78,  96,  29,  22,  24,  13,
    14,  11,  11,  18,  12,  12,  30,  52,  52,  44,
    28,  28,  20,  56,  40,  31,  50,  40,  46,  42,
    29,  19,  36,  25,  22,  17,  19,  26,  30,  20,
    15,  21,  11,  8,   8,   19,  5,   8,   8,   11,
    11,  8,   3,   9,   5,   4,   7,   3,   6,   3,
    5,   4,   5,   6,
]

assert len(SURAH_AYAT) == 115, (
    f"SURAH_AYAT must have 115 entries (index 0 unused), got {len(SURAH_AYAT)}"
)


def is_valid_verse(surah, ayah):
    if not (1 <= surah <= 114):
        return False
    if ayah < 0 or ayah > SURAH_AYAT[surah]:
        return False
    return True


def max_ayah(surah):
    return SURAH_AYAT[surah] if 1 <= surah <= 114 else 0
    