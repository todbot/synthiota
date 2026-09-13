

To install needed third-party libraries, see "requirements.txt".
You can use "circup" to install them with `circup install -r requirements.txt`

For actual applications, see the directories.

- `polysynth/`  - subtractive polysynth on synthtools' SubtractiveSynth
- `wavesynth/`  - wavetable polysynth on synthtools' WavetableSynth
- `tbish/`      - TB-303 inspired mono bass synth
- `synthtest/`  - earlier synth playground

`polysynth/` and `wavesynth/` are ported from the pico_test_synth repo
and run on the `relic_synthiota` hardware library (vendored in `lib/`,
from github.com/relic-se/CircuitPython_Synthiota). Each app folder has
its own README with the control map and copy-to-device steps.
