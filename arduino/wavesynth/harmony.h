// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// harmony.h - the scales of circuitpython/wavesynth's SCALES_USED, from
//             circuitpython/lib/harmony.py, with their screen labels.

#pragma once

struct Scale {
  const char *label;
  uint8_t n;
  uint8_t steps[12];
};

const Scale SCALES[] = {
  { "maj", 7, { 0, 2, 4, 5, 7, 9, 11 } },
  { "min", 7, { 0, 2, 3, 5, 7, 8, 10 } },
  { "dor", 7, { 0, 2, 3, 5, 7, 9, 10 } },
  { "mix", 7, { 0, 2, 4, 5, 7, 9, 10 } },
  { "lyd", 7, { 0, 2, 4, 6, 7, 9, 11 } },
  { "phr", 7, { 0, 1, 3, 5, 7, 8, 10 } },
  { "harm", 7, { 0, 2, 3, 5, 7, 8, 11 } },
  { "melo", 7, { 0, 2, 3, 5, 7, 9, 11 } },
  { "maj5", 5, { 0, 2, 4, 7, 9 } },
  { "min5", 5, { 0, 3, 5, 7, 10 } },
  { "blues", 6, { 0, 3, 5, 6, 7, 10 } },
  { "chr", 12, { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 } },
};
const int NUM_SCALES = sizeof(SCALES) / sizeof(SCALES[0]);

const char *const NOTE_NAMES[12] = { "C", "C#", "D", "D#", "E", "F",
                                     "F#", "G", "G#", "A", "A#", "B" };

// degree n >= 0 wraps up an octave per scale length
int scale_degree(const Scale &s, int root, int n) {
  return root + 12 * (n / s.n) + s.steps[n % s.n];
}
