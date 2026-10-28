// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// FlashBackendRP2.h - RP2040/RP2350 internal flash as a FlashBackend, for
//                     the arduino-pico core. Modeled on CircuitPython's
//                     ports/raspberrypi/supervisor/internal_flash.c.

#pragma once
#if defined(ARDUINO_ARCH_RP2040)
#include <Arduino.h>
#include <hardware/dma.h>
#include <hardware/flash.h>
#include <hardware/sync.h>
#include "FlashDisk.h"

extern uint8_t _FS_start;
extern uint8_t _FS_end;
extern uint8_t __flash_binary_end;

class FlashBackendRP2 : public FlashBackend {
 public:
  // start and size are byte offsets into flash, 4KB aligned
  FlashBackendRP2(uint32_t start, uint32_t size) : start(start), sz(size) {}

  // CircuitPython's CIRCUITPY drive, so a board that ran CircuitPython
  // keeps its files. Includes the last 4KB, which EEPROM.h also uses.
  static FlashBackendRP2 circuitpy() {
#if defined(ARDUINO_RASPBERRY_PI_PICO_W)
    const uint32_t cpy_start = 1536 * 1024;
#else
    const uint32_t cpy_start = 1024 * 1024;
#endif
    return FlashBackendRP2(cpy_start, PICO_FLASH_SIZE_BYTES - cpy_start);
  }

  // the core's "Flash Size" FS partition (the region LittleFS would use)
  static FlashBackendRP2 menuFS() {
    return FlashBackendRP2((uint32_t)&_FS_start - XIP_BASE,
                           (uint32_t)(&_FS_end - &_FS_start));
  }

  // false if the sketch binary runs into the drive, which would erase code
  bool sketchFits() {
    return sz > 0 && (uint32_t)&__flash_binary_end <= XIP_BASE + start;
  }

  uint32_t size() override { return sz; }
  uint32_t eraseSize() override { return FLASH_SECTOR_SIZE; }

  void read(uint32_t addr, uint8_t *dst, uint32_t len) override {
    memcpy(dst, (const void *)(XIP_BASE + start + addr), len);
  }

  // Code runs from this flash (XIP), so the other core is parked and this
  // core has interrupts off (lock()) for the whole erase + program. DMA is
  // paused too: chained channels whose IRQ can't run meanwhile (e.g. I2S
  // audio) restart past the end of their buffers and stream random RAM.
  bool eraseProgram(uint32_t addr, const uint8_t *src) override {
    uint32_t busy, idle;
    pauseDMA(busy, idle);
    rp2040.idleOtherCore();
    flash_range_erase(start + addr, FLASH_SECTOR_SIZE);
    flash_range_program(start + addr, src, FLASH_SECTOR_SIZE);
    rp2040.resumeOtherCore();
    resumeDMA(busy, idle);
    return true;
  }

  // Clearing EN pauses a busy channel mid-transfer; setting it resumes.
  // A disabled channel also ignores chain triggers, so a chain target must
  // never be off while its source can still finish: pause busy channels
  // before idle ones, and resume idle ones first.
  static void pauseDMA(uint32_t &busy, uint32_t &idle) {
    busy = idle = 0;
    for (uint ch = 0; ch < NUM_DMA_CHANNELS; ch++) {
      if (dma_hw->ch[ch].al1_ctrl & DMA_CH0_CTRL_TRIG_BUSY_BITS) {
        busy |= 1u << ch;
        hw_clear_bits(&dma_hw->ch[ch].al1_ctrl, DMA_CH0_CTRL_TRIG_EN_BITS);
      }
    }
    for (uint ch = 0; ch < NUM_DMA_CHANNELS; ch++) {
      if (!(busy & (1u << ch)) &&
          (dma_hw->ch[ch].al1_ctrl & DMA_CH0_CTRL_TRIG_EN_BITS)) {
        idle |= 1u << ch;
        hw_clear_bits(&dma_hw->ch[ch].al1_ctrl, DMA_CH0_CTRL_TRIG_EN_BITS);
      }
    }
  }
  static void resumeDMA(uint32_t busy, uint32_t idle) {
    for (uint32_t set : {idle, busy}) {
      for (uint ch = 0; ch < NUM_DMA_CHANNELS; ch++) {
        if (set & (1u << ch)) {
          hw_set_bits(&dma_hw->ch[ch].al1_ctrl, DMA_CH0_CTRL_TRIG_EN_BITS);
        }
      }
    }
  }

  uint32_t lock() override { return save_and_disable_interrupts(); }
  void unlock(uint32_t state) override { restore_interrupts(state); }

 private:
  uint32_t start, sz;
};

#endif  // ARDUINO_ARCH_RP2040
