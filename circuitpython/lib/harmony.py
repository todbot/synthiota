# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
"""
``harmony``
================================================================================

Scales and chords for mapping controllers onto musical pitch.

A ``Scale`` is a root MIDI note plus a set of semitone offsets. Index it
by scale degree to get MIDI notes; degrees past the end (or negative)
wrap with octave shifts, so a row of pads maps straight onto the scale
without bounds checks. ``Scale.chord()`` stacks in-key chords by degree;
the module-level ``chord()`` builds chromatic chords from an interval
table.

Standalone for now; intended to move into ``synthtools`` as
``synthtools.harmony``. Pure Python, no dependencies.

    >>> from harmony import Scale, chord, note_name
    >>> s = Scale(60, "major")            # C major, middle C
    >>> [note_name(s.degree(n)) for n in range(8)]
    ['C4', 'D4', 'E4', 'F4', 'G4', 'A4', 'B4', 'C5']
    >>> [note_name(n) for n in s.chord(0, "triad")]
    ['C4', 'E4', 'G4']
    >>> [note_name(n) for n in s.chord(1, "triad")]   # ii is minor, for free
    ['D4', 'F4', 'A4']
    >>> [note_name(n) for n in chord(60, "dom7")]
    ['C4', 'E4', 'G4', 'A#4']
"""

__version__ = "0.0.0"

#: name -> ascending semitone offsets from the root, one octave. The root
#: (0) is always the first entry; the octave (12) is implied, not listed.
SCALES = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),  # natural minor / aeolian
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
    "harmonic_minor": (0, 2, 3, 5, 7, 8, 11),
    "melodic_minor": (0, 2, 3, 5, 7, 9, 11),
    "major_pentatonic": (0, 2, 4, 7, 9),
    "minor_pentatonic": (0, 3, 5, 7, 10),
    "blues": (0, 3, 5, 6, 7, 10),
    "whole_tone": (0, 2, 4, 6, 8, 10),
    "chromatic": (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11),
}

SCALE_NAMES = tuple(SCALES)

#: name -> semitone offsets from a root note. Chromatic, key-independent.
CHORDS = {
    "1": (0,),
    "5": (0, 7),
    "oct": (0, 12),
    "maj": (0, 4, 7),
    "min": (0, 3, 7),
    "dim": (0, 3, 6),
    "aug": (0, 4, 8),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    "6": (0, 4, 7, 9),
    "min6": (0, 3, 7, 9),
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
    "dom7": (0, 4, 7, 10),
    "dim7": (0, 3, 6, 9),
    "add9": (0, 4, 7, 14),
    "maj9": (0, 4, 7, 11, 14),
    "min9": (0, 3, 7, 10, 14),
}

CHORD_NAMES = tuple(CHORDS)

#: name -> scale-degree offsets (not semitones). Stacked in the current
#: scale, so quality follows the key: "triad" on degree 0 of a major
#: scale is major, on degree 1 it is minor, and so on.
DIATONIC_SHAPES = {
    "root": (0,),
    "oct": (0, 7),
    "5th": (0, 4),
    "triad": (0, 2, 4),
    "7th": (0, 2, 4, 6),
    "9th": (0, 2, 4, 6, 8),
    "sus": (0, 3, 4),
    "spread": (0, 4, 9),
}

DIATONIC_SHAPE_NAMES = tuple(DIATONIC_SHAPES)

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def note_name(midi, with_octave=True):
    """``"C4"``, ``"F#3"`` ... MIDI 60 is C4 here. Software that calls
    middle C "C3" should subtract 1 from the octave."""
    n = NOTE_NAMES[int(midi) % 12]
    return "%s%d" % (n, int(midi) // 12 - 1) if with_octave else n


def chord(root, name):
    """MIDI notes of chromatic chord ``name`` (see ``CHORDS``) on ``root``."""
    return [root + i for i in CHORDS[name]]


class Scale:
    """A scale: a root MIDI note and a set of semitone offsets.

    :param root: MIDI note of scale degree 0
    :param name: a key of ``SCALES``, or an explicit sequence of ascending
        semitone offsets starting at 0
    """

    def __init__(self, root=60, name="major"):
        self.root = root
        self.set_scale(name)

    def set_scale(self, name):
        """Switch scale in place, keeping the root. ``name`` is a ``SCALES``
        key or an explicit offset sequence; an unknown name falls back to
        major rather than raising, so a knob mapped past the list is safe."""
        if isinstance(name, str):
            self.name = name if name in SCALES else "major"
            self.steps = SCALES[self.name]
        else:
            self.name = "custom"
            self.steps = tuple(name)

    @property
    def size(self):
        """Notes per octave in this scale."""
        return len(self.steps)

    def degree(self, n):
        """MIDI note for 0-based scale degree ``n``. ``n`` may be any
        integer: it wraps with octave shifts, so ``degree(size)`` is the
        octave above the root and ``degree(-1)`` the step below it."""
        octaves, i = divmod(int(n), len(self.steps))
        return self.root + 12 * octaves + self.steps[i]

    def __getitem__(self, n):
        return self.degree(n)

    def chord(self, degree, shape="triad"):
        """Diatonic chord as a list of MIDI notes: the degree offsets of
        ``shape`` (a ``DIATONIC_SHAPES`` key or an explicit offset
        sequence) added to ``degree``, each taken through the scale so the
        chord stays in key."""
        offsets = DIATONIC_SHAPES[shape] if isinstance(shape, str) else shape
        return [self.degree(degree + o) for o in offsets]

    def contains(self, midi):
        """Whether ``midi`` is a note of this scale, in any octave."""
        return (int(midi) - self.root) % 12 in self.steps

    def snap(self, midi):
        """The scale note nearest ``midi`` (ties round down). Useful for
        quantizing a chromatic source -- MIDI input, an LFO -- onto the
        scale."""
        rel = int(round(midi)) - self.root
        octaves, semis = divmod(rel, 12)
        best = self.steps[0]
        for step in self.steps:
            if abs(step - semis) < abs(best - semis):
                best = step
        return self.root + 12 * octaves + best

    def __repr__(self):
        return "Scale(root=%d, name=%r)" % (self.root, self.name)


if __name__ == "__main__":
    s = Scale(60, "major")
    print("C major degrees 0..7:", [note_name(s[n]) for n in range(8)])
    print("i triad:  ", [note_name(n) for n in s.chord(0, "triad")])
    print("ii triad: ", [note_name(n) for n in s.chord(1, "triad")])
    print("V 7th:    ", [note_name(n) for n in s.chord(4, "7th")])
    s.set_scale("minor_pentatonic")
    print("A minor pent (root 57):", end=" ")
    s.root = 57
    print([note_name(s[n]) for n in range(6)])
    print("snap C#4 to A minor pent:", note_name(s.snap(61)))
    print("dom7 on C:", [note_name(n) for n in chord(60, "dom7")])
