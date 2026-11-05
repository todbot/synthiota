

To install needed third-party libraries, see "requirements.txt".
You can use "circup" to install them with `circup install -r requirements.txt`

For actual applications, see the directories.

- [`polysynth`](./polysynth) -- two-oscillator subtractive polysynth
  (synthtools' `SubtractiveSynth`). The pads are a chromatic keyboard
  and the pots edit 16 params over 2 pages.
- [`wavesynth`](./wavesynth) -- wavetable polysynth (synthtools'
  `WavetableSynth`). The pads are a scale keyboard, with chords on the
  top row, and the pots edit 24 params over 3 pages.
- [`swarmsynth`](./swarmsynth) -- Swarmatron-style drone (synthtools'
  `SwarmSynth`): eight oscillators on one pitch, fanned apart by the
  right slider.
- [`dronesynth`](./dronesynth) -- eight drone oscillators, each tuned
  by its own knob, each with its own LFO.
- [`dronesynth_wt`](./dronesynth_wt) -- dronesynth with each oscillator
  at its own place in a shared wavetable.
- [`stepseq8`](./stepseq8) -- 8-track MIDI step sequencer in the manner of
  picostepseq, with tracks up to 32 steps long. Makes no sound itself.
- [`tbish2`](./tbish2) -- TB-303-style acid bassline (synthtools'
  `BasslineSynth`) with a 16-step sequencer you can edit on the board.
- [`tbish`](./tbish) -- the original TB-303-style synth, a technology
  demo with no pattern editing or MIDI in.
- [`hwtest`](./hwtest) -- hardware bring-up tests and the reference pin
  setup.
- [`synthtest`](./synthtest) -- earlier synth playground.

`polysynth/` and `wavesynth/` are ported from the pico_test_synth repo.
All but `tbish/`, `hwtest/` and `synthtest/` run on the `relic_synthiota`
hardware library. Each app folder has its own README with the control
map and copy-to-device steps.

## Building a UF2 for an app

`make_uf2.py` builds one UF2 holding both CircuitPython and an app's
CIRCUITPY drive. Flash it like any UF2 and the board boots straight
into the app, with no copying files or installing libraries.

    python3 make_uf2.py adafruit-circuitpython-...-en_US-11.0.0.uf2 polysynth

It takes a CircuitPython firmware UF2 and an app folder, then:

- reads the board, CircuitPython version and drive address from the
  firmware with `picotool`
- copies the app folder to the drive root, skipping `README.md`,
  `__pycache__` and dot files
- copies the local modules in `requirements.txt` (the `lib/*.py` lines)
  to the drive root, unless the app has its own copy
- installs the rest of `requirements.txt` into `/lib` with `circup`,
  matched to that board and CircuitPython version
- builds the drive and joins it to the firmware with `folder2uf2`,
  using the drive address and size from the firmware

The output is `<app>-<board>.uf2` unless `-o` names it. It writes the
firmware and only the used part of the drive, so it stays small; the
new drive replaces whatever was there. `--full` writes the whole drive
instead, wiping any leftover data.

Options:

- `-o FILE` -- output UF2
- `-a PATH` -- also put a file or folder at the drive root (repeatable)
- `-r FILE` -- a different requirements file
- `--flash-size N` -- flash size in bytes, if not 2MB (RP2040) or 4MB
  (RP2350)
- `--full` -- write the whole drive, not just its used part
- `--keep` -- keep the staged drive folder, to see what went in

Needs `picotool`, `circup` and `folder2uf2`. With Homebrew:

    brew install picotool && pip3 install circup folder2uf2

The GitHub Action in `.github/workflows/build-uf2.yml` runs this for
every app against the latest CircuitPython 11.x when a release is
published, and attaches the UF2s to the release.
