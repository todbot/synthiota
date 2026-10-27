// Desktop test: FlashDisk's cache against a shadow copy, and fat12Format
// images for fsck_msdos / hdiutil (see check.sh).
#include <stdio.h>
#include <stdlib.h>
#include <vector>
#include "FlashDisk.h"
#include "FlashBackendRAM.h"
#include "Fat12Format.h"

static int fails = 0;
#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL: " __VA_ARGS__); printf("\n"); } } while (0)

// random reads/writes/syncs through the cache must always read back what
// was last written, and the backing store must match after a sync
static void cache_test(uint32_t size, uint32_t erase_size, int ops) {
  std::vector<uint8_t> flash(size, 0xFF), shadow(size, 0xFF), buf(16 * 512);
  FlashBackendRAM be(flash.data(), size, erase_size);
  FlashDisk disk(be);
  uint32_t nsec = disk.sectorCount();
  srand(size ^ erase_size);
  for (int i = 0; i < ops; i++) {
    uint32_t ns = 1 + rand() % 16;
    uint32_t s = rand() % (nsec - ns + 1);
    switch (rand() % 3) {
      case 0:
        for (auto &b : buf) b = rand();
        CHECK(disk.writeSectors(s, buf.data(), ns), "write %u+%u", s, ns);
        memcpy(&shadow[s * 512], buf.data(), ns * 512);
        break;
      case 1:
        CHECK(disk.readSectors(s, buf.data(), ns), "read %u+%u", s, ns);
        CHECK(!memcmp(&shadow[s * 512], buf.data(), ns * 512),
              "stale read %u+%u (erase %u)", s, ns, erase_size);
        break;
      case 2:
        disk.syncDevice();
        CHECK(flash == shadow, "flash != shadow after sync (erase %u)", erase_size);
        break;
    }
  }
  CHECK(!disk.readSectors(nsec - 1, buf.data(), 2), "read past end accepted");
  CHECK(!disk.writeSectors(nsec, buf.data(), 1), "write past end accepted");
  printf("cache %uKB erase %u: %d ops\n", size / 1024, erase_size, ops);
}

static void format_image(uint32_t size, const char *path) {
  std::vector<uint8_t> flash(size, 0xFF);
  FlashBackendRAM be(flash.data(), size);
  FlashDisk disk(be);
  CHECK(sectorErased(disk, 0), "fresh image not erased");
  CHECK(fat12Format(disk, "FLASHDISK", size), "format %uKB", size / 1024);
  CHECK(!sectorErased(disk, 0), "formatted image reads as erased");
  FILE *f = fopen(path, "wb");
  fwrite(flash.data(), 1, size, f);
  fclose(f);
  printf("wrote %s\n", path);
}

int main() {
  cache_test(1024 * 1024, 4096, 20000);
  cache_test(256 * 1024, 512, 20000);
  cache_test(256 * 1024, 2048, 20000);
  const uint32_t sizes[] = {64 * 1024, 1024 * 1024, 2048 * 1024, 3072 * 1024};
  for (uint32_t sz : sizes) {
    char path[64];
    snprintf(path, sizeof(path), "fat12_%ukb.img", sz / 1024);
    format_image(sz, path);
  }
  printf(fails ? "%d FAILURES\n" : "all passed\n", fails);
  return fails != 0;
}
