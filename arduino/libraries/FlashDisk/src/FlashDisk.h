// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// FlashDisk.h - a flash region as an SdFat block device (512-byte sectors)
//               with a one-erase-block write-back cache. The chip-specific
//               part is a FlashBackend; see README.md for why it's built
//               this way.

#pragma once
#include <stdint.h>
#include <string.h>
#include <SdFat_Adafruit_Fork.h>

#ifndef FLASHDISK_BLOCK_MAX
#define FLASHDISK_BLOCK_MAX 4096  // largest eraseSize() a backend may have
#endif

class FlashBackend {
 public:
  virtual ~FlashBackend() {}
  virtual uint32_t size() = 0;       // bytes, a multiple of eraseSize()
  virtual uint32_t eraseSize() = 0;  // a multiple of 512
  virtual void read(uint32_t addr, uint8_t *dst, uint32_t len) = 0;
  // Erase the block at addr and program it from src as one step: nothing
  // else may touch the flash in between. Called with lock() held.
  virtual bool eraseProgram(uint32_t addr, const uint8_t *src) = 0;
  virtual uint32_t lock() = 0;
  virtual void unlock(uint32_t state) = 0;
};

class FlashDisk : public FsBlockDeviceInterface {
 public:
  explicit FlashDisk(FlashBackend &backend) : be(backend) {}

  Sector_t sectorCount() override { return be.size() / 512; }
  bool isBusy() override { return false; }

  bool readSector(Sector_t s, uint8_t *dst) override {
    return readSectors(s, dst, 1);
  }
  bool writeSector(Sector_t s, const uint8_t *src) override {
    return writeSectors(s, src, 1);
  }

  // never from the cache: flush it, then read the flash itself
  bool readSectors(Sector_t s, uint8_t *dst, size_t ns) override {
    if (!inRange(s, ns)) return false;
    uint32_t st = be.lock();
    bool ok = flush();
    if (ok) be.read(s * 512, dst, ns * 512);
    be.unlock(st);
    return ok;
  }

  bool writeSectors(Sector_t s, const uint8_t *src, size_t ns) override {
    const uint32_t bs = be.eraseSize();
    if (!inRange(s, ns) || bs > FLASHDISK_BLOCK_MAX) return false;
    uint32_t st = be.lock();
    bool ok = true;
    for (size_t i = 0; ok && i < ns; i++) {
      uint32_t off = (s + i) * 512;
      uint32_t blk = off - off % bs;
      if (blk != cacheAddr) {
        ok = flush();
        if (!ok) break;
        be.read(blk, cache, bs);
        cacheAddr = blk;
      }
      memcpy(cache + (off - blk), src + i * 512, 512);
    }
    be.unlock(st);
    return ok;
  }

  bool syncDevice() override {
    uint32_t st = be.lock();
    bool ok = flush();
    be.unlock(st);
    return ok;
  }

 private:
  static const uint32_t NO_CACHE = 0xFFFFFFFF;
  FlashBackend &be;
  uint8_t cache[FLASHDISK_BLOCK_MAX];
  uint32_t cacheAddr = NO_CACHE;

  bool inRange(Sector_t s, size_t ns) { return s + ns <= sectorCount(); }

  bool flush() {
    if (cacheAddr == NO_CACHE) return true;
    uint32_t addr = cacheAddr;
    cacheAddr = NO_CACHE;
    return be.eraseProgram(addr, cache);
  }
};
