

To install needed third-party libraries, see "requirements.txt".
You can use "circup" to install them with `circup install -r requirements.txt`

For actual applications, see the directories.

- `polysynth/`     - subtractive polysynth on synthtools' SubtractiveSynth
- `wavesynth/`     - wavetable polysynth on synthtools' WavetableSynth
- `swarmsynth/`    - Swarmatron-style drone on synthtools' SwarmSynth
- `dronesynth/`    - eight drone oscillators, each tuned by its own knob
- `dronesynth_wt/` - dronesynth with a shared wavetable
- `tbish/`         - TB-303 inspired mono bass synth
- `tbish2/`        - tbish on synthtools' BasslineSynth
- `synthtest/`     - earlier synth playground

`polysynth/` and `wavesynth/` are ported from the pico_test_synth repo.
All but `tbish/` and `synthtest/` run on the `relic_synthiota` hardware
library. Each app folder has its own README with the control map and
copy-to-device steps.

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
- builds a FAT image of the drive and joins it to the firmware

The output is `<app>-<board>.uf2` unless `-o` names it. It covers the
whole flash, so flashing it replaces anything already on the drive.

Options:

- `-o FILE` -- output UF2
- `-a PATH` -- also put a file or folder at the drive root (repeatable)
- `-r FILE` -- a different requirements file
- `--flash-size N` -- flash size in bytes, if not 2MB (RP2040) or 4MB
  (RP2350)
- `--keep` -- keep the staged drive folder, to see what went in

Needs `picotool`, `mtools` and `circup`. With Homebrew:

    brew install picotool mtools && pip3 install circup

The GitHub Action in `.github/workflows/build-uf2.yml` runs this for
every app against the latest CircuitPython 11.x when a release is
published, and attaches the UF2s to the release.
