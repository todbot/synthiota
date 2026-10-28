// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// FlashDiskMSC.h - serve a FlashDisk as a USB drive with Adafruit TinyUSB.
//                  Only one per sketch: TinyUSB's MSC callbacks are plain
//                  functions, so they find the drive through one static.

#pragma once
#include <Adafruit_TinyUSB.h>
#include "FlashDisk.h"

class FlashDiskMSC {
 public:
  // Call after every other USB interface's begin() (MIDI, HID, ...): this
  // re-enumerates so the host sees them all. fs, if given, has its cache
  // dropped whenever the host writes, since the host changed the volume
  // under it.
  bool begin(FlashDisk &disk, FatVolume *fs = nullptr,
             const char *vendor = "FlashDisk", const char *product = "Flash Disk",
             const char *rev = "1.0") {
    disk_ = &disk;
    fs_ = fs;
    self() = this;
    msc_.setID(vendor, product, rev);
    msc_.setReadWriteCallback(readCB, writeCB, flushCB);
    msc_.setCapacity(disk.sectorCount(), 512);
    msc_.setUnitReady(true);
    if (!msc_.begin()) return false;
    if (TinyUSBDevice.mounted()) {
      TinyUSBDevice.detach();
      delay(10);
      TinyUSBDevice.attach();
    }
    return true;
  }

  // True once per burst of host writes, after the host has been quiet for
  // settle_ms: a single file copy flushes many times.
  bool changed(uint32_t settle_ms = 500) {
    if (!dirty_ || millis() - lastFlush_ < settle_ms) return false;
    dirty_ = false;
    return true;
  }

  // cb runs on the first host write of a burst, before any of it reaches
  // flash: the erases that follow stall both cores for tens of ms each,
  // so e.g. fade audio out here and wait for the output buffers to drain.
  // Runs in the USB task's context, so busy-wait rather than delay().
  void onWriteBegin(void (*cb)(), uint32_t quiet_ms = 300) {
    writeBegin_ = cb;
    quietMs_ = quiet_ms;
  }

  // true from the first write of a burst until the host has been quiet
  // (no writes or flushes) for onWriteBegin()'s quiet_ms
  bool hostActive() {
    return lastActivity_ && millis() - lastActivity_ < quietMs_;
  }

  // false tells the host the medium is gone, e.g. while the sketch itself
  // writes the volume; true again makes the host re-read it
  void setUnitReady(bool ready) { msc_.setUnitReady(ready); }

  Adafruit_USBD_MSC &msc() { return msc_; }

 private:
  Adafruit_USBD_MSC msc_;
  FlashDisk *disk_ = nullptr;
  FatVolume *fs_ = nullptr;
  volatile bool dirty_ = false;
  volatile uint32_t lastFlush_ = 0;
  volatile uint32_t lastActivity_ = 0;
  uint32_t quietMs_ = 300;
  void (*writeBegin_)() = nullptr;

  static FlashDiskMSC *&self() {
    static FlashDiskMSC *p = nullptr;
    return p;
  }

  static int32_t readCB(uint32_t lba, void *buf, uint32_t len) {
    return self()->disk_->readSectors(lba, (uint8_t *)buf, len / 512) ? len : -1;
  }
  static int32_t writeCB(uint32_t lba, uint8_t *buf, uint32_t len) {
    FlashDiskMSC *d = self();
    if (d->writeBegin_ && !d->hostActive()) d->writeBegin_();
    d->lastActivity_ = millis();
    return d->disk_->writeSectors(lba, buf, len / 512) ? len : -1;
  }
  static void flushCB() {
    FlashDiskMSC *d = self();
    d->disk_->syncDevice();
    if (d->fs_) d->fs_->cacheClear();
    d->lastFlush_ = d->lastActivity_ = millis();
    d->dirty_ = true;
  }
};
