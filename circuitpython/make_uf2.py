#!/usr/bin/env python3
"""make_uf2.py -- build a full-flash UF2: CircuitPython firmware plus a
prebuilt CIRCUITPY drive holding an app and its libraries.

  python3 make_uf2.py adafruit-circuitpython-...uf2 polysynth

Needs picotool, circup, and mtools
If using homebrew:  brew install picotool mtools && pip3 install circup
"""

import argparse
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FLASH_BASE = 0x10000000
NVM_SIZE = 4096
FLASH_SIZES = {"rp2040": 2 * 1024 * 1024, "rp2350": 4 * 1024 * 1024}
SKIP_NAMES = {"__pycache__", "README.md"}


def fw_info(uf2_path):
    """Pull family, board, version, and CIRCUITPY start from picotool."""
    out = subprocess.run(["picotool", "info", "-a", str(uf2_path)],
                         check=True, capture_output=True, text=True).stdout
    def find(pat):
        m = re.search(pat, out, re.M)
        if not m:
            sys.exit(f"couldn't find {pat!r} in 'picotool info' output")
        return m.group(1)
    return {
        "family": find(r"family ID '([\w-]+)'"),
        "board": find(r"BOARD=(\S+)"),
        "version": find(r"^\s*version:\s+(\S+)"),
        # only the start is trustworthy: the size CP reports is a fixed
        # 1MB, the real drive runs to the end of flash
        "drive_start": int(find(r"embedded drive:\s+(0x[0-9a-fA-F]+)"), 16),
    }


def read_uf2(uf2_path):
    """Return (lowest_addr, bytes) of the UF2's payload, gaps as 0xFF."""
    data = Path(uf2_path).read_bytes()
    blocks = []
    for i in range(0, len(data), 512):
        _, _, flags, addr, size = struct.unpack_from("<5I", data, i)
        if flags & 1:  # "not main flash"
            continue
        blocks.append((addr, data[i + 32:i + 32 + size]))
    lo = min(a for a, _ in blocks)
    hi = max(a + len(d) for a, d in blocks)
    buf = bytearray(b"\xff" * (hi - lo))
    for addr, d in blocks:
        buf[addr - lo:addr - lo + len(d)] = d
    return lo, buf


def stage_app(app_dir, req_path, stage, info):
    """Lay out the CIRCUITPY contents in stage/."""
    shutil.copytree(app_dir, stage, dirs_exist_ok=True,
                    ignore=lambda d, names: [n for n in names
                                             if n.startswith(".")
                                             or n in SKIP_NAMES])
    (stage / "lib").mkdir(exist_ok=True)
    packages = []
    for line in req_path.read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        local = req_path.parent / line
        if local.is_file():
            # an app's own copy of a module shadows ours
            if not (stage / local.name).exists():
                shutil.copy2(local, stage / local.name)
        else:
            packages.append(line)
    if packages:
        reqs = stage.parent / "circup_requirements.txt"
        reqs.write_text("\n".join(packages) + "\n")
        subprocess.run(["circup", "--path", str(stage),
                        "--board-id", info["board"],
                        "--cpy-version", info["version"],
                        "install", "-r", str(reqs)], check=True)


def make_fat(img_path, size, stage):
    img = str(img_path)
    # skip mtools' floppy-geometry sanity checks, meaningless for flash
    env = dict(os.environ, MTOOLS_SKIP_CHECK="1")
    subprocess.run(["mformat", "-i", img, "-C", "-T", str(size // 512),
                    "-h", "1", "-s", "1", "-v", "CIRCUITPY", "-N", "0", "::"],
                   check=True, env=env)
    subprocess.run(["mcopy", "-i", img, "-s", "-m",
                    *[str(p) for p in sorted(stage.iterdir())], "::"],
                   check=True, env=env)
    return img_path.read_bytes()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("firmware", type=Path, help="CircuitPython .uf2")
    ap.add_argument("app", type=Path, help="app dir, e.g. polysynth")
    ap.add_argument("-o", "--output", type=Path,
                    help="output .uf2 (default: <app>-<board>.uf2)")
    ap.add_argument("-r", "--requirements", type=Path,
                    default=HERE / "requirements.txt")
    ap.add_argument("--flash-size", type=lambda s: int(s, 0),
                    help="flash bytes (default: 2MB rp2040, 4MB rp2350)")
    ap.add_argument("--keep", action="store_true",
                    help="keep the staging dir and print its path")
    args = ap.parse_args()

    info = fw_info(args.firmware)
    chip = info["family"].split("-")[0]
    flash_size = args.flash_size or FLASH_SIZES[chip]
    drive_start = info["drive_start"]
    fs_size = flash_size - drive_start
    out = args.output or Path(f"{args.app.resolve().name}-{info['board']}.uf2")

    fw_lo, fw = read_uf2(args.firmware)
    if fw_lo != FLASH_BASE:
        sys.exit(f"firmware starts at {fw_lo:#x}, expected {FLASH_BASE:#x}")
    if len(fw) > drive_start - NVM_SIZE:
        sys.exit("firmware overlaps the NVM/CIRCUITPY area")

    tmp = Path(tempfile.mkdtemp(prefix="make_uf2_"))
    try:
        stage = tmp / "CIRCUITPY"
        stage_app(args.app, args.requirements, stage, info)
        fat = make_fat(tmp / "fs.img", fs_size, stage)

        flash = bytearray(b"\xff" * flash_size)
        flash[:len(fw)] = fw
        flash[drive_start:] = fat
        bin_path = tmp / "flash.bin"
        bin_path.write_bytes(flash)
        subprocess.run(["picotool", "uf2", "convert", str(bin_path),
                        str(out), "-o", hex(FLASH_BASE),
                        "--family", info["family"]], check=True)
        used = sum(p.stat().st_size for p in stage.rglob("*") if p.is_file())
        print(f"{out}: CircuitPython {info['version']} for {info['board']}, "
              f"CIRCUITPY {used // 1024}K used of {fs_size // 1024}K "
              f"at {FLASH_BASE + drive_start:#x}")
    finally:
        if args.keep:
            print(f"staging dir: {tmp}")
        else:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
