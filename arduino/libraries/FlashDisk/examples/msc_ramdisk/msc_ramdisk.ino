// msc_ramdisk - a 64KB FAT12 RAM disk over USB, on any board Adafruit
//               TinyUSB supports. Contents vanish on reset.
//
// Needs Tools > USB Stack "Adafruit TinyUSB" where the core offers one.
// RAMDISK_SIZE (32KB minimum) must fit in RAM, so not on a SAMD21.

// SdFat (via FlashDisk.h) before Adafruit_TinyUSB.h, or SAMD builds lose it
#include <FlashDisk.h>
#include <FlashBackendRAM.h>
#include <Fat12Format.h>
#include <Adafruit_TinyUSB.h>
#include <FlashDiskMSC.h>

#define RAMDISK_SIZE (64 * 1024)

uint8_t ram[RAMDISK_SIZE];
FlashBackendRAM backend(ram, sizeof(ram));
FlashDisk disk(backend);
FatVolume fatfs;
FlashDiskMSC drive;

void setup() {
  Serial.begin(115200);
  fat12Format(disk, "RAMDISK", micros());
  fatfs.begin(&disk);
  drive.begin(disk, &fatfs, "FlashDisk", "RAM disk", "1.0");
}

void loop() {
  if (drive.changed()) {
    Serial.printf("host wrote; %lu free clusters\n",
                  (unsigned long)fatfs.freeClusterCount());
  }
}
