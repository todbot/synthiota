// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// FlashBackendRAM.h - a RAM buffer as a FlashBackend: a RAM disk, a test
//                     fixture, and the smallest example of a backend.

#pragma once
#include "FlashDisk.h"

class FlashBackendRAM : public FlashBackend {
 public:
  FlashBackendRAM(uint8_t *buf, uint32_t size, uint32_t erase_size = 4096)
      : buf(buf), sz(size), esz(erase_size) {}

  uint32_t size() override { return sz; }
  uint32_t eraseSize() override { return esz; }
  void read(uint32_t addr, uint8_t *dst, uint32_t len) override {
    memcpy(dst, buf + addr, len);
  }
  bool eraseProgram(uint32_t addr, const uint8_t *src) override {
    memcpy(buf + addr, src, esz);
    return true;
  }
  uint32_t lock() override { return 0; }
  void unlock(uint32_t) override {}

 private:
  uint8_t *buf;
  uint32_t sz, esz;
};
