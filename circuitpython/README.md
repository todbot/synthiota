

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
library 
Each app folder has its own README with the control map and copy-to-device steps.
