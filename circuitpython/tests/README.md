# tests

Tools for checking the board from the computer. These stay on the
computer, except where noted. Don't copy this directory to CIRCUITPY.

## midi_capture.py

Listens to a board's USB MIDI and reports what it sent: Start, Continue,
Stop, clock count and tempo, then note-ons, note-offs and timing for each
channel. It exits non-zero if nothing arrived, or if a channel's note-ons
and note-offs don't match, which usually means a stuck note.

    pip3 install python-rtmidi pyserial

To check a program as you play it, start this, then tap play on the board:

    python3 midi_capture.py --secs 10

Stop the sequencer before the time runs out, or notes still sounding at the
end will show up as mismatched.

To run a test with no hands, `--run` sends a snippet to the board, captures
its MIDI, and restarts the board's `code.py` afterwards. This one plays
`stepseq8`'s sequencer flat out for 4 secs, so `stepseq8` must already be on
the board:

    python3 midi_capture.py --run stepseq8_play.py

`--run` plays notes on channels 1-8, so anything connected will sound. It
needs the serial port, so close `tio` first, and it uses `run_on_device.py`
from a checkout of CircuitPython_Synth_Tools.

Times are when the computer received each message, so they include USB and
macOS delays. Only USB is captured, not TRS, and only each message's status
byte is looked at, so note numbers and velocities aren't checked.

## stepseq8_play.py

Runs on the board, by way of `--run` above. It leaves out the screen, LEDs
and pads, so its timing is the best case. It's not a program to copy over.
