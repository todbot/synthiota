// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// wave_osc.h - wavetable oscillator: plays one WAVE_LEN-sample wave of a
//              table, crossfaded into the next wave by the fractional part
//              of the wave position, the same morph as synthtools'
//              Wavetable. Mozzi's Oscil only takes int8 tables.

#pragma once
#include "wavetable.h"

static_assert(WAVE_LEN == 256, "WaveOsc indexes cells with phase >> 24");

class WaveOsc {
 public:
  void setFreq(float hz) {
    inc = (uint32_t)(hz * (4294967296.0f / MOZZI_AUDIO_RATE));
  }
  void setTable(const int16_t *t, uint16_t n) {
    table = t;
    num_waves = n;
  }
  // in 1/65536ths of a wave: 0 is wave 0, (num_waves - 1) << 16 the last
  void setWavePos(uint32_t q16) { pos = q16; }

  inline int16_t next() {
    if (!table) return 0;
    uint32_t i = pos >> 16;
    uint32_t cell = phase >> 24;  // 256 cells: top 8 bits of the phase
    phase += inc;
    const int16_t *a = table + i * WAVE_LEN;
    int32_t sa = a[cell];
    if (i + 1 >= num_waves) return sa;
    int32_t sb = a[cell + WAVE_LEN];
    return sa + (((sb - sa) * (int32_t)((pos >> 1) & 0x7FFF)) >> 15);
  }

 private:
  const int16_t *table = nullptr;
  uint16_t num_waves = 0;
  uint32_t phase = 0, inc = 0, pos = 0;
};
