# FlashDisk

A microcontroller's own flash as a FAT USB drive, the way CircuitPython
does it: copy files onto the board from your computer, then read them
from your sketch.

- `FlashDisk` -- a flash region as an SdFat block device (512-byte
  sectors) with a one-erase-block write-back cache
- `FlashBackend` -- the small per-chip part `FlashDisk` sits on
- `FlashBackendRP2` -- RP2040/RP2350 internal flash (arduino-pico core)
- `FlashBackendRAM` -- a RAM disk; also the template for new backends
- `fat12Format()` -- FAT12 formatter for small volumes
- `FlashDiskMSC` -- serve it over USB with Adafruit TinyUSB

Depends on [SdFat - Adafruit Fork][sdfat]. `FlashDiskMSC` also needs
[Adafruit TinyUSB][tinyusb] (bundled with the arduino-pico and Adafruit
cores; select Tools > USB Stack > "Adafruit TinyUSB").

[sdfat]: https://github.com/adafruit/SdFat
[tinyusb]: https://github.com/adafruit/Adafruit_TinyUSB_Arduino

## Usage

```cpp
#include <FlashDisk.h>          // before Adafruit_TinyUSB.h (see Notes)
#include <FlashBackendRP2.h>
#include <Fat12Format.h>
#include <Adafruit_TinyUSB.h>
#include <FlashDiskMSC.h>

FlashBackendRP2 backend = FlashBackendRP2::circuitpy();
FlashDisk disk(backend);
FatVolume fatfs;
FlashDiskMSC drive;

void setup() {
  // other USB interfaces' begin() first, e.g. MIDI
  if (!fatfs.begin(&disk) && sectorErased(disk, 0)) {
    fat12Format(disk, "MYDRIVE", micros());
    fatfs.begin(&disk);
  }
  drive.begin(disk, &fatfs, "Vendor", "Product", "1.0");
}

void loop() {
  if (drive.changed()) {
    // host wrote files and has gone quiet: rescan with fatfs
  }
}
```

See `examples/msc_flash_rp2` and `examples/msc_ramdisk`.

## RP2040/RP2350 regions

- `FlashBackendRP2::circuitpy()` -- CircuitPython's CIRCUITPY drive,
  1MB (1.5MB on Pico W) to the end of flash. A board that ran
  CircuitPython keeps its files, and can go back to CircuitPython
  later. Use a Flash Size option with no FS, keep the sketch under the
  start (`backend.sketchFits()` checks), and don't use `EEPROM.h`: its
  4KB at the end of flash is part of this region.
- `FlashBackendRP2::menuFS()` -- the region the core's Flash Size menu
  reserves for a filesystem (what LittleFS would use).
- `FlashBackendRP2(start, size)` -- any 4KB-aligned range.

## Why it's built this way

Adafruit_SPIFlash with its RP2040 transport can serve the same region,
but on an RP2350 under host writes it corrupted the volume: lost writes,
and 4KB blocks programmed without being erased (old AND new data).
CircuitPython serving the same partition to the same host, with the
same copies, never did. FlashDisk follows CircuitPython's
`ports/raspberrypi/supervisor/internal_flash.c`, and keeps four rules:

1. A block's erase and program are one `eraseProgram()` call: nothing
   else touches the flash in between.
2. Reads never come from the cache. A pending block is flushed first,
   then the flash itself is read.
3. Every call holds the backend's `lock()` (on RP2: interrupts off), so
   the USB task interrupt running the MSC callbacks can't interleave
   with the sketch's own SdFat calls.
4. The device is exactly the region: `sectorCount()` is `size()/512`.
   (The Adafruit transport stopped 4KB short of the end, under a volume
   that claimed those sectors.)

SdFat reads and writes FAT12, but its own formatter refuses volumes
under 6MB and only makes FAT16/32, while a 1-3MB volume can only legally
be FAT12. `fat12Format()` fills that gap with a super-floppy (no MBR)
layout like CircuitPython's.

## Notes

- Expect audio and other interrupt-driven work to stall while the host
  writes: each 4KB block erase takes tens of ms with interrupts off.
  `FlashBackendRP2` pauses every DMA channel for that time: a chained
  DMA (e.g. I2S audio) whose interrupt can't run otherwise restarts past
  the end of its buffer and streams random RAM, which is loud noise.
  Audio still drops out; `drive.onWriteBegin(cb)` runs `cb` before a
  burst of host writes reaches flash, so a sketch can fade its output to
  silence there, and back in once `drive.hostActive()` goes false.
- Format only flash that has never been written (`sectorErased()`): an
  unmountable volume that isn't blank may still hold someone's files.
- Two FAT writers at once corrupt a volume. Let the host own the drive;
  for a sketch-side write, `drive.setUnitReady(false)`, write, sync,
  then `setUnitReady(true)` so the host re-reads it.
- On the Adafruit SAMD core, if `Adafruit_TinyUSB.h` is included before
  SdFat, SdFat's types go missing at compile time. Include
  `FlashDisk.h` first.

## Writing a backend

Implement the six `FlashBackend` methods; `FlashBackendRAM.h` is the
whole pattern. `eraseSize()` must be a multiple of 512 and at most
`FLASHDISK_BLOCK_MAX` (4096, the size of the cache). If code runs from
the same flash, `eraseProgram()` and `lock()` must keep everything
else (interrupts, the other core) off it.

## Tests

`extras/test` builds `FlashDisk` and `fat12Format()` on a desktop
against a stub SdFat interface: a randomized cache test against a
shadow copy, then FAT12 images (64KB-3MB) checked with macOS's
`fsck_msdos` and mounted with `diskutil image attach`.

    cd extras/test && make test

## License

MIT
