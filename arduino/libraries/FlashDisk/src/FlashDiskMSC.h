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

  static FlashDiskMSC *&self() {
    static FlashDiskMSC *p = nullptr;
    return p;
  }

  static int32_t readCB(uint32_t lba, void *buf, uint32_t len) {
    return self()->disk_->readSectors(lba, (uint8_t *)buf, len / 512) ? len : -1;
  }
  static int32_t writeCB(uint32_t lba, uint8_t *buf, uint32_t len) {
    return self()->disk_->writeSectors(lba, buf, len / 512) ? len : -1;
  }
  static void flushCB() {
    FlashDiskMSC *d = self();
    d->disk_->syncDevice();
    if (d->fs_) d->fs_->cacheClear();
    d->lastFlush_ = millis();
    d->dirty_ = true;
  }
};
