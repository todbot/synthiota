# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
#
# wave_bank.py -- one Serum-style wavetable WAV in RAM, read at a fractional
# wave position into any number of INDEPENDENT waveform buffers.
#
# synthtools' Wavetable owns the one buffer it reads into, which is what a
# polysynth wants: every voice shares the position. Eight drones each want
# their own position out of the same table, and eight Wavetables would be
# eight copies of the table. So: one table, one scratch pair, a buffer per
# caller.
#
# Headed for synthtools once it has earned it.

import adafruit_wave
import ulab.numpy as np


class WaveBank:
    """A wavetable held one wave per array, plus the lerp that reads a
    fractional wave position out of it into a caller's own buffer.

    The table is allocated once, at ``max_waves`` capacity, and ``load()``
    rewrites it in place. Reading a table into a fresh array mid-session
    needs 32 KB of contiguous heap, which a running instrument has no way
    to guarantee and nothing to fall back on if it fails.
    """

    def __init__(self, size=256, max_waves=64):
        self.size = size
        self.max_waves = max_waves
        self.num_waves = 0
        self.waves = [np.zeros(size, dtype=np.int16) for _ in range(max_waves)]
        self._fa = np.zeros(size)  # float scratch: wave a, then the result
        self._fd = np.zeros(size)

    def load(self, path):
        """Read a 16-bit mono wavetable WAV, waves of ``size`` samples back
        to back. A table past ``max_waves`` is truncated, not refused."""
        w = adafruit_wave.open(path)
        try:
            if w.getsampwidth() != 2 or w.getnchannels() != 1:
                raise ValueError("16-bit mono WAV required: " + path)
            n = min(w.getnframes() // self.size, self.max_waves)
            # checked before the first write, so a file that is not a
            # wavetable leaves the table it was going to replace intact
            if n < 2:
                raise ValueError("fewer than two waves: " + path)
            w.setpos(0)
            for i in range(n):
                self.waves[i][:] = np.frombuffer(w.readframes(self.size),
                                                 dtype=np.int16)
        finally:
            w.close()
        self.num_waves = n
        return n

    def fill(self, buf, pos):
        """Write the wave at fractional ``pos`` into ``buf``: 3.25 is a
        quarter of the way from wave 3 to wave 4."""
        n = self.num_waves
        if pos < 0:
            pos = 0.0
        elif pos > n - 1:
            pos = n - 1.0
        i = int(pos)
        if i > n - 2:  # at the very top, blend the last pair
            i = n - 2
        frac = pos - i
        if frac <= 0.0:  # exact wave: int16 straight in, scratch untouched
            buf[:] = self.waves[i]
            return
        fa, fd = self._fa, self._fd
        fa[:] = self.waves[i]
        fd[:] = self.waves[i + 1]
        # float, never int16: two samples straddling zero at high amplitude
        # wrap on the subtract and overflow on the store back. In place, and
        # accumulating into fd rather than a fresh array, because this runs
        # eight times a loop pass and the garbage is what costs.
        fd -= fa
        fd *= frac
        fd += fa
        buf[:] = fd
