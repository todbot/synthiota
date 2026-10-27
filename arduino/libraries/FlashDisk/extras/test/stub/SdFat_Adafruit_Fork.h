// Stand-in for SdFat's block-device interface, so FlashDisk and the
// formatter build on a desktop without SdFat or Arduino.
#pragma once
#include <stddef.h>
#include <stdint.h>

typedef uint32_t Sector_t;

class FsBlockDeviceInterface {
 public:
  virtual ~FsBlockDeviceInterface() {}
  virtual bool isBusy() = 0;
  virtual bool readSector(Sector_t sector, uint8_t *dst) = 0;
  virtual bool readSectors(Sector_t sector, uint8_t *dst, size_t ns) = 0;
  virtual Sector_t sectorCount() = 0;
  virtual bool syncDevice() = 0;
  virtual bool writeSector(Sector_t sector, const uint8_t *src) = 0;
  virtual bool writeSectors(Sector_t sector, const uint8_t *src, size_t ns) = 0;
};
