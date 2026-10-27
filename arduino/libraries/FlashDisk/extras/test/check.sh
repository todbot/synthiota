#!/bin/sh
# Check each image from test_flashdisk with macOS's own FAT tools: fsck,
# then attach + mount, write a file, detach, and fsck again.
cd "$(dirname "$0")"
fail() { echo "FAIL: $*"; exit 1; }
for img in fat12_*.img; do
  fsck_msdos -n "$img" > fsck.log 2>&1 || { cat fsck.log; fail "fsck $img"; }
  out=$(diskutil image attach "$img" 2>&1)
  dev=$(echo "$out" | awk '{print $1}' | head -1)
  vol=$(echo "$out" | grep -o '/Volumes/.*' | head -1)
  [ -n "$vol" ] || { echo "$out"; [ -n "$dev" ] && diskutil eject "$dev" >/dev/null; fail "mount $img"; }
  echo hello > "$vol/hello.txt" && grep -q hello "$vol/hello.txt" || fail "write $img"
  diskutil eject "$dev" > /dev/null || fail "eject $img"
  fsck_msdos -n "$img" > fsck.log 2>&1 || { cat fsck.log; fail "fsck after write $img"; }
  echo "ok $img (mounted as $vol)"
done
rm -f fsck.log
