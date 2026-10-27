// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// Fat12Format.h - minimal FAT12 formatter for any SdFat block device, for
//                 the small volumes SdFat's own formatter refuses (README).
//
// Makes a "super floppy" (no MBR) volume, same as CircuitPython:
//   sector 0             boot sector, with the BPB describing the layout
//   1 .. 2*fat_secs      two copies of the FAT
//   next 32 sectors      root directory (512 entries x 32 bytes)
//   rest                 data clusters

#pragma once
#include <stdint.h>
#include <string.h>
#include <SdFat_Adafruit_Fork.h>

namespace fat12_detail {
// FAT on-disk ints are little-endian, at unaligned offsets
inline void put16(uint8_t *p, uint16_t v) { p[0] = v; p[1] = v >> 8; }
inline void put32(uint8_t *p, uint32_t v) { put16(p, v); put16(p + 2, v >> 16); }
}  // namespace fat12_detail

// True if sector s reads as erased flash (all 0xFF). Format only then: an
// unmountable volume that isn't blank may still hold someone's files.
inline bool sectorErased(FsBlockDeviceInterface &dev, uint32_t s) {
  uint8_t buf[512];
  if (!dev.readSector(s, buf)) return false;
  for (uint8_t b : buf) {
    if (b != 0xFF) return false;
  }
  return true;
}

// label: up to 11 chars. serial: the volume ID; hosts cache by it, so
// pass something that varies (e.g. micros()).
inline bool fat12Format(FsBlockDeviceInterface &dev, const char *label,
                        uint32_t serial = 0x12345678) {
  using namespace fat12_detail;
  const uint16_t root_entries = 512;
  const uint32_t root_secs = root_entries * 32 / 512;
  const uint32_t total = dev.sectorCount();
  if (total < 64 || total > 0xFFFF) return false;  // tiny, or > 32MB

  // Geometry: FAT size and cluster count depend on each other, so grow
  // the FAT until it has a 12-bit entry for every cluster (+2 reserved
  // entries), then double the cluster size if that's too many clusters
  // for FAT12.
  uint8_t spc = 1;  // sectors per cluster
  uint32_t fat_secs, clusters;
  while (true) {
    for (fat_secs = 1;; fat_secs++) {
      clusters = (total - 1 - root_secs - 2 * fat_secs) / spc;
      if (((clusters + 2) * 3 + 1) / 2 <= fat_secs * 512) break;
    }
    if (clusters < 4085) break;  // more and hosts read it as FAT16
    spc *= 2;
  }

  // Boot sector: jump + OEM name, then the BIOS Parameter Block
  uint8_t buf[512];
  memset(buf, 0, sizeof(buf));
  buf[0] = 0xEB; buf[1] = 0x3C; buf[2] = 0x90;  // x86 jmp, checked by some hosts
  memcpy(buf + 3, "MSDOS5.0", 8);
  put16(buf + 11, 512);           // bytes per sector
  buf[13] = spc;
  put16(buf + 14, 1);             // reserved sectors: just this one
  buf[16] = 2;                    // number of FATs
  put16(buf + 17, root_entries);
  put16(buf + 19, total);         // total sectors
  buf[21] = 0xF8;                 // media: fixed disk
  put16(buf + 22, fat_secs);      // sectors per FAT
  put16(buf + 24, 63);            // sectors/track, heads: CHS leftovers
  put16(buf + 26, 255);
  // extended BPB: drive number, signature, serial, label, type string
  buf[36] = 0x80;
  buf[38] = 0x29;                 // says the next three fields are valid
  put32(buf + 39, serial);
  char lbl[11];
  memset(lbl, ' ', 11);           // labels are space-padded, not NUL-terminated
  size_t n = strlen(label);
  memcpy(lbl, label, n < 11 ? n : 11);
  memcpy(buf + 43, lbl, 11);
  memcpy(buf + 54, "FAT12   ", 8);  // informational only; type comes from cluster count
  buf[510] = 0x55; buf[511] = 0xAA;
  if (!dev.writeSector(0, buf)) return false;

  // FATs: all clusters free, except entries 0 and 1, which are reserved
  // and hold the media byte + end-of-chain marker (F8 FF FF packed)
  for (uint8_t f = 0; f < 2; f++) {
    for (uint32_t s = 0; s < fat_secs; s++) {
      memset(buf, 0, sizeof(buf));
      if (s == 0) { buf[0] = 0xF8; buf[1] = 0xFF; buf[2] = 0xFF; }
      if (!dev.writeSector(1 + f * fat_secs + s, buf)) return false;
    }
  }

  // Root dir: empty, except a volume-label entry, which is where hosts
  // actually read the drive name from (not the boot sector)
  uint32_t root_start = 1 + 2 * fat_secs;
  for (uint32_t s = 0; s < root_secs; s++) {
    memset(buf, 0, sizeof(buf));
    if (s == 0) {
      memcpy(buf, lbl, 11);
      buf[11] = 0x08;  // attr: volume label
    }
    if (!dev.writeSector(root_start + s, buf)) return false;
  }
  // data clusters needn't be cleared: the FAT says they're all free
  return dev.syncDevice();
}
