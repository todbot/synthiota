// msc_flash_rp2 - share an RP2040/RP2350's CIRCUITPY flash region as a USB
//                 drive, and list it whenever the host changes it.
//
// Needs Tools > USB Stack "Adafruit TinyUSB" and a Flash Size with no FS
// (e.g. "4MB (no FS)"). A board that ran CircuitPython keeps its files.

// SdFat (via FlashDisk.h) before Adafruit_TinyUSB.h, or SAMD builds lose it
#include <FlashDisk.h>
#include <FlashBackendRP2.h>
#include <Fat12Format.h>
#include <Adafruit_TinyUSB.h>
#include <FlashDiskMSC.h>

FlashBackendRP2 backend = FlashBackendRP2::circuitpy();
FlashDisk disk(backend);
FatVolume fatfs;
FlashDiskMSC drive;

void list_root() {
  File32 dir = fatfs.open("/");
  File32 f;
  while (f.openNext(&dir, O_RDONLY)) {
    char name[64];
    f.getName(name, sizeof(name));
    Serial.printf("  %7lu %s%s\n", (unsigned long)f.fileSize(), name,
                  f.isDir() ? "/" : "");
    f.close();
  }
  dir.close();
}

void setup() {
  Serial.begin(115200);
  if (!backend.sketchFits()) {
    while (true) {
      Serial.println("sketch overlaps the drive region");
      delay(1000);
    }
  }
  if (!fatfs.begin(&disk) && sectorErased(disk, 0)) {
    fat12Format(disk, "FLASHDISK", micros());
    fatfs.begin(&disk);
  }
  drive.begin(disk, &fatfs, "FlashDisk", "RP2 flash", "1.0");
}

void loop() {
  if (drive.changed()) {
    Serial.println("drive changed:");
    list_root();
  }
}
