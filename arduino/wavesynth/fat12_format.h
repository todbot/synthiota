// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// fat12_format.h - minimal FAT12 formatter for the internal-flash drive.
//
// SdFat's FatFormatter only makes FAT16/32, and a 1-2MB volume has too
// few clusters to be legal FAT16, so we write FAT12 like CircuitPython.

#pragma once
#include <Adafruit_SPIFlash.h>

static void put16(uint8_t *p, uint16_t v) { p[0] = v; p[1] = v >> 8; }
static void put32(uint8_t *p, uint32_t v) { put16(p, v); put16(p + 2, v >> 16); }

bool fat12_format(Adafruit_SPIFlash &flash, const char *label) {
  const uint16_t root_entries = 512;
  const uint32_t root_secs = root_entries * 32 / 512;
  const uint32_t total = flash.size() / 512;

  uint8_t spc = 1;
  uint32_t fat_secs, clusters;
  while (true) {
    for (fat_secs = 1;; fat_secs++) {
      clusters = (total - 1 - root_secs - 2 * fat_secs) / spc;
      if (((clusters + 2) * 3 + 1) / 2 <= fat_secs * 512) break;
    }
    if (clusters < 4085) break;  // more and hosts read it as FAT16
    spc *= 2;
  }

  uint8_t buf[512];
  memset(buf, 0, sizeof(buf));
  buf[0] = 0xEB; buf[1] = 0x3C; buf[2] = 0x90;
  memcpy(buf + 3, "MSDOS5.0", 8);
  put16(buf + 11, 512);
  buf[13] = spc;
  put16(buf + 14, 1);  // reserved sectors: just this one
  buf[16] = 2;         // number of FATs
  put16(buf + 17, root_entries);
  put16(buf + 19, total);
  buf[21] = 0xF8;
  put16(buf + 22, fat_secs);
  put16(buf + 24, 63);
  put16(buf + 26, 255);
  buf[36] = 0x80;
  buf[38] = 0x29;
  put32(buf + 39, micros());
  char lbl[11];
  memset(lbl, ' ', 11);
  memcpy(lbl, label, min(strlen(label), (size_t)11));
  memcpy(buf + 43, lbl, 11);
  memcpy(buf + 54, "FAT12   ", 8);
  buf[510] = 0x55; buf[511] = 0xAA;
  if (!flash.writeBlocks(0, buf, 1)) return false;

  for (uint8_t f = 0; f < 2; f++) {
    for (uint32_t s = 0; s < fat_secs; s++) {
      memset(buf, 0, sizeof(buf));
      if (s == 0) { buf[0] = 0xF8; buf[1] = 0xFF; buf[2] = 0xFF; }
      if (!flash.writeBlocks(1 + f * fat_secs + s, buf, 1)) return false;
    }
  }

  uint32_t root_start = 1 + 2 * fat_secs;
  for (uint32_t s = 0; s < root_secs; s++) {
    memset(buf, 0, sizeof(buf));
    if (s == 0) {
      memcpy(buf, lbl, 11);
      buf[11] = 0x08;  // volume label attr, so the host shows the name
    }
    if (!flash.writeBlocks(root_start + s, buf, 1)) return false;
  }
  return flash.syncBlocks();
}
