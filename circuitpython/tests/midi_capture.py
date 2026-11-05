#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
# SPDX-License-Identifier: MIT
"""Capture a board's USB MIDI on the host and report what it sent.

    python3 midi_capture.py --secs 10               # just listen
    python3 midi_capture.py --run stepseq8_play.py  # run a snippet, listen

See README.md in this directory.
"""

import argparse
import glob
import subprocess
import sys
import time
from pathlib import Path

import rtmidi

RUN_ON_DEVICE = (Path.home() / "projects/circuitpython"
                 / "CircuitPython_Synth_Tools/tests/hw/run_on_device.py")
MIDI_PORT_NAME = "circuitpython"
RUN_TIMEOUT_SECS = 40
DRAIN_SECS = 0.3  # messages still on their way when the snippet ends

NOTE_OFF, NOTE_ON = 0x80, 0x90
CLOCK, START, CONTINUE, STOP = 0xF8, 0xFA, 0xFB, 0xFC


def open_midi_in(name):
    midi_in = rtmidi.MidiIn()
    midi_in.ignore_types(timing=False)  # rtmidi drops MIDI clock by default
    ports = midi_in.get_ports()
    for i, port in enumerate(ports):
        if name.lower() in port.lower():
            midi_in.open_port(i)
            print("listening on:", port)
            return midi_in
    sys.exit(f"no MIDI port matching '{name}', found: {ports}")


def serial_port():
    ports = glob.glob("/dev/tty.usbmodem*")
    if not ports:
        sys.exit("no /dev/tty.usbmodem* serial port, is the board plugged in?")
    return ports[0]


def run_snippet(path):
    """Run a snippet on the board, then restart its code.py."""
    result = subprocess.run(
        [sys.executable, str(RUN_ON_DEVICE), str(path), "--reboot",
         "--port", serial_port(), "--timeout", str(RUN_TIMEOUT_SECS)],
        capture_output=True, text=True, check=False)
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    if result.returncode:
        sys.exit(f"snippet failed, is tio holding the port? ({result.returncode})")


def gaps_ms(times):
    return [(b - a) * 1000 for a, b in zip(times, times[1:])]


def report(events):
    """``events`` is a list of (time in secs, status byte). True if all's well."""
    statuses = [status for _, status in events]
    clocks = [t for t, status in events if status == CLOCK]
    print(f"start {statuses.count(START)}  continue {statuses.count(CONTINUE)}"
          f"  stop {statuses.count(STOP)}  clocks {len(clocks)}")
    if len(clocks) > 1:
        secs = clocks[-1] - clocks[0]
        print(f"clock rate: {(len(clocks) - 1) / secs * 60 / 24:.1f} bpm")

    print("chan  ons  offs  note-on gaps ms: avg  min  max")
    all_ok = True
    for chan in range(16):
        ons = [t for t, status in events if status == NOTE_ON | chan]
        offs = statuses.count(NOTE_OFF | chan)
        if not ons and not offs:
            continue
        stuck = len(ons) != offs
        all_ok = all_ok and not stuck
        line = f"{chan + 1:4d} {len(ons):4d} {offs:5d}"
        gaps = gaps_ms(ons)
        if gaps:
            line += (f"  {sum(gaps) / len(gaps):20.1f} {min(gaps):5.1f}"
                     f" {max(gaps):5.1f}")
        print(line + ("  <-- ons and offs differ, stuck note?" if stuck else ""))
    if not events:
        print("nothing received")
        return False
    return all_ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    ap.add_argument("--secs", type=float, default=10, help="how long to listen")
    ap.add_argument("--run", type=Path, help="snippet to run on the board instead")
    ap.add_argument("--midi-port", default=MIDI_PORT_NAME,
                    help="part of the MIDI port's name")
    args = ap.parse_args()

    events = []

    def on_midi(event, _data):
        message, _delta = event
        events.append((time.monotonic(), message[0]))

    midi_in = open_midi_in(args.midi_port)
    midi_in.set_callback(on_midi)
    if args.run:
        run_snippet(args.run)
        time.sleep(DRAIN_SECS)
    else:
        print(f"listening for {args.secs:g} secs, go ahead and play")
        time.sleep(args.secs)
    midi_in.close_port()

    sys.exit(0 if report(events) else 1)


if __name__ == "__main__":
    main()
