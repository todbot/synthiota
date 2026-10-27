// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// wavetable.h - find and load the wavetable WAVs in /wavetables.
//
// A wavetable WAV is 16-bit mono PCM, N single-cycle waves of WAVE_LEN
// samples back to back. Loading happens on core0 into whichever of two
// RAM buffers core1 isn't playing; core1 swaps to it on its next control
// tick (wave_adopt()), so changing tables never tears a sample.

#pragma once
#include <SdFat_Adafruit_Fork.h>

#define WAVE_DIR        "/wavetables"
#define WAVE_LEN        256
#define MAX_WAVES       64   // 32KB per buffer, what the current files hold
#define MAX_WAVE_FILES  32
#define WAVE_NAME_LEN   64

char wave_files[MAX_WAVE_FILES][WAVE_NAME_LEN];  // sorted, names only
int num_wave_files = 0;
int wave_sel = -1;  // index into wave_files of the table last loaded
int wave_sel_waves = 0;  // its wave count

int16_t wave_bufs[2][MAX_WAVES * WAVE_LEN];
int wave_buf_next = 0;  // core0: the buffer core1 isn't using

// core0 -> core1 handoff. Set waves before table: core1 keys on table.
const int16_t *volatile pending_table = nullptr;
volatile uint16_t pending_waves = 0;
volatile uint32_t wave_swaps = 0;

const int16_t *wt_table = nullptr;  // core1 only
uint16_t wt_num_waves = 0;          // core1 only

static uint16_t rd16(const uint8_t *p) { return p[0] | (p[1] << 8); }
static uint32_t rd32(const uint8_t *p) { return rd16(p) | ((uint32_t)rd16(p + 2) << 16); }

static int cmp_names(const void *a, const void *b) {
  return strcmp((const char *)a, (const char *)b);
}

// Skips "._" AppleDouble files: a FAT drive written by macOS has them
// next to every file, and they aren't RIFF.
void wave_scan(FatVolume &fs) {
  num_wave_files = 0;
  File32 dir = fs.open(WAVE_DIR);
  if (!dir) return;
  File32 f;
  while (num_wave_files < MAX_WAVE_FILES && f.openNext(&dir, O_RDONLY)) {
    char name[WAVE_NAME_LEN];
    size_t n = f.getName(name, sizeof(name));
    if (!f.isDir() && name[0] != '.' && n > 4 && n < WAVE_NAME_LEN - 1 &&
        !strcasecmp(name + n - 4, ".WAV")) {
      strcpy(wave_files[num_wave_files++], name);
    }
    f.close();
  }
  dir.close();
  qsort(wave_files, num_wave_files, WAVE_NAME_LEN, cmp_names);
}

int wave_find(const char *name) {
  for (int i = 0; i < num_wave_files; i++) {
    if (!strcmp(wave_files[i], name)) return i;
  }
  return -1;
}

// Walks the RIFF chunks rather than assuming a 44-byte header: editors
// add LIST/cue/etc chunks. Returns waves read into dst, 0 on any error.
int wav_load(FatVolume &fs, const char *path, int16_t *dst, int max_waves) {
  File32 f = fs.open(path, O_RDONLY);
  if (!f) return 0;
  int waves = 0;
  bool fmt_ok = false;
  uint8_t h[16];
  if (f.read(h, 12) == 12 && !memcmp(h, "RIFF", 4) && !memcmp(h + 8, "WAVE", 4)) {
    while (f.read(h, 8) == 8) {
      uint32_t sz = rd32(h + 4);
      uint32_t skip = sz + (sz & 1);  // chunks are word aligned
      if (!memcmp(h, "fmt ", 4)) {
        if (sz < 16 || f.read(h, 16) != 16) break;
        // PCM, mono, 16-bit
        fmt_ok = rd16(h) == 1 && rd16(h + 2) == 1 && rd16(h + 14) == 16;
        skip -= 16;
      } else if (!memcmp(h, "data", 4)) {
        if (!fmt_ok) break;
        int n = min((int)(sz / 2 / WAVE_LEN), max_waves);
        int bytes = n * WAVE_LEN * 2;
        if (n > 0 && f.read(dst, bytes) == bytes) waves = n;
        break;
      }
      if (!f.seekCur(skip)) break;
    }
  }
  f.close();
  return waves;
}

// core0: load wave_files[idx] and hand it to core1
bool wave_select(FatVolume &fs, int idx) {
  if (idx < 0 || idx >= num_wave_files) return false;
  // core1 hasn't taken the last one yet, so both buffers are spoken for
  uint32_t t = millis();
  while (pending_table && millis() - t < 50) delay(1);
  if (pending_table) return false;

  char path[sizeof(WAVE_DIR) + WAVE_NAME_LEN];
  snprintf(path, sizeof(path), WAVE_DIR "/%s", wave_files[idx]);
  int16_t *dst = wave_bufs[wave_buf_next];
  int waves = wav_load(fs, path, dst, MAX_WAVES);
  if (!waves) return false;

  pending_waves = waves;
  __dmb();
  pending_table = dst;
  wave_buf_next ^= 1;
  wave_sel = idx;
  wave_sel_waves = waves;
  return true;
}

// core1: call at the top of updateControl()
void wave_adopt() {
  const int16_t *p = pending_table;
  if (!p) return;
  __dmb();
  wt_num_waves = pending_waves;
  wt_table = p;
  pending_table = nullptr;
  wave_swaps++;
}
