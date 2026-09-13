# wavesynth for synthiota

A wavetable polysynth for Synthiota, on `synthtools`' `WavetableSynth`.
Ported from pico_test_synth's `wavesynth`.

`wpos` moves within the loaded wavetable and morphs sounding notes
live; `wsel` picks which `.WAV` in `wavetables/`. Two LFOs: `lamt` /
`lrate` over the filter cutoff, and `wlfo` / `wrate` sweeping `wpos` up
toward `wlfo` (a ceiling at or below `wpos` means no sweep).

The 16 step pads are an 8x2 **scale keyboard** (`lib/harmony.py`): the
bottom row is the 8 scale degrees, one note each; the top row plays a
diatonic chord on the last bottom pad pressed. Scale and key are on the
KEY/MOD page.

The 8 pots edit 8 parameters at once and the encoder turns pages (24
parameters over 3 pages: WAVE, ENV/FILT, KEY/MOD). All 8 pots on a page
are live, but the screen shows one pair large -- turning any pot snaps
it to that pot's pair (1-2, 3-4, 5-6, 7-8), each param as `P<n> name`
over a big value. The 8 pot LEDs show all 8 values on the page.

The pots are scaled takeover: turning one always moves its parameter,
scaled so the knob and the value converge without a jump, so a page
turn or a patch load never snaps a sound.

Nine patches are defined in code (`default_patches()`); there is no
disk save.

## Controls

- bottom pads (1-8) ...... the 8 scale degrees, one note each
- top pads (9-16) ........ chord on the last bottom pad: root, oct, 5th,
                           triad, 7th, 9th, sus, spread (all diatonic)
- 8 pots ................. 8 params at once; screen shows the last-turned pair
- encoder turn ........... previous / next page
- encoder HOLD + bottom pad  load patch 1..8
- up / down buttons ...... octave down / up
- left slider ............ nudge filter cutoff (while touched)
- right slider ........... wavetable position (while touched)
- pot LEDs .............. all 8 param values on this page
- step LEDs ............. currently held pads

Page WAVE:    freq reso wpos wsel wlfo wrate atk rel
Page ENV/FILT: fatk frel famt ftype lamt lrate vdep vol
Page KEY/MOD: scale key wshp w1x wvel vrate pamt ptime
  (wshp/w1x/wvel = wave-LFO shape / one-shot / velocity depth)

## MIDI

Responds to NOTE ON/OFF on any channel (played chromatically, not
snapped to the scale), CC 1 (wavetable position), CC 74 (filter
cutoff), CC 120/123 (all notes off). Sends NOTE ON/OFF for every note a
pad triggers, on USB and UART.

## Running it

From `circuitpython/`:

    circup install -r requirements.txt

That installs the third-party libraries and the local `lib/` modules
(`relic_synthiota.py`, `synthiota_potpage_ui.py`, `harmony.py`).

`lib/synthtools/` is `.py` source copied from a checkout of
github.com/todbot/CircuitPython_SynthTools -- the current bundle release
(0.5.1) lacks the wave LFO and `synth.update()` and has a broken
`update_knobs_scale`. Delete that folder once `circup install synthtools`
gives a new enough version.

Copy to the CIRCUITPY root: the contents of this folder including
`wavetables/`, plus `lib/synthtools/` and the `lib/*.py` modules.
Then run `dot_clean -m /Volumes/CIRCUITPY`.

`harmony.py` (scales + chords) is standalone for now, headed for
`synthtools.harmony`.

`relic_synthiota.py` originates at
github.com/relic-se/CircuitPython_Synthiota.

## Notes

- Audio runs at 44100 Hz. Set `SAMPLE_RATE` to 22050 if it glitches.
- `WavetableSynth.FILT_F_MAX` is set from `sample_rate * 0.45` before
  the synth is constructed (Nyquist clamp, baked in at build time).
- `wpos` and `wlfo` are re-ranged whenever `wsel` loads a different
  file: the wavetables here hold 64 waves each and a fixed ceiling would
  hide most of every table.
- The wave LFO only advances when `synth.update()` runs; the main loop
  calls it every pass, a cheap no-op while `wlfo <= wpos`.
- macOS drops `._`-prefixed AppleDouble files into `wavetables/` on a
  FAT drive; `wave_files()` skips them, but `dot_clean -m /Volumes/CIRCUITPY`
  after copying is still worth it.
