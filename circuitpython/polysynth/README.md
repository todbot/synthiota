# polysynth for synthiota

A playable two-oscillator subtractive polysynth for Synthiota, on
`synthtools`' `SubtractiveSynth`. Ported from 
[pico_test_synth](https://github.com/todbot/pico_test_synth)'s 
`synthtools_polysynth`.

The 16 step pads are a chromatic keyboard. The 8 pots edit 8 parameters
at once; the encoder turns pages (16 parameters over 2 pages, OSC/AMP
and FILT/MOD). All 8 pots on a page are live, but the screen shows one
pair large -- turning any pot snaps it to that pot's pair (1-2, 3-4,
5-6, 7-8), each param as `P<n> name` over a big value. The 8 pot LEDs
show all 8 values on the page. USB and TRS MIDI both play the synth;
pad presses echo out both.

The pots are scaled takeover: turning one always moves its parameter,
scaled so the knob and the value converge without a jump, so a page
turn or a nudged pot never snaps a sound.

## Controls

- step pads .......... chromatic keyboard (16 notes)
- 8 pots ............. 8 params at once; screen shows the last-turned pair
- encoder turn ....... previous / next page
- up / down buttons .. octave down / up (C1 .. C5)
- left slider ........ nudge filter cutoff (while touched)
- right slider ....... vibrato depth (while touched)
- pot LEDs .......... all 8 param values on this page
- step LEDs ......... currently held notes

## MIDI

Responds to NOTE ON/OFF on any channel, CC 1 (vibrato depth), CC 74
(filter cutoff), CC 120/123 (all notes off). Sends NOTE ON/OFF for pad
presses on USB and UART.

## Running it

From `circuitpython/`:

    circup install -r requirements.txt

That installs the third-party libraries and the two local `lib/`
modules (`relic_synthiota.py`, `synthiota_potpage_ui.py`). 

Copy to the CIRCUITPY root: the contents of this folder, plus
`lib/synthtools/` and the two `lib/*.py` modules.

`relic_synthiota.py` originates at
github.com/relic-se/CircuitPython_Synthiota

`synthtools` is at github.com/todbot/CircuitPython_SynthTools.

## Notes

- `SubtractiveSynth.FILT_F_MAX` is set from `sample_rate * 0.45` before
  the synth is constructed: the Nyquist clamp is baked into the block
  graph at build time.
- Audio runs at 44100 Hz. If it glitches, set SAMPLE_RATE to 22050.
- `detune` below 1.0005 snaps to exactly 1.0, which is the single-
  oscillator path (one Note per key). Any real detune spends two Notes
  per key.
