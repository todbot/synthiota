# swarmsynth for synthiota

A Dewanatron Swarmatron-style drone machine for Synthiota, on
`synthtools`' `SwarmSynth`: eight oscillators on one pitch, fanned apart
by a single "swarm" control and each drifting independently.

The real instrument is monophonic, played from a pitch ribbon, with a
second ribbon and a knob pulling the oscillators from a few cents apart
out to a wide chord of equidistant pitches. This is that, on the pads:
the **bottom row** is eight scale degrees, the **top row** re-aims the
drone by octaves and fifths, and the **right slider** is the span
ribbon. Working the pitch and the span together -- Dewanatron's "taffy
pulling" -- is what the instrument is for.

The 8 pots are one page of 8 parameters, paired on screen so each pair
is one idea. All 8 are live; the screen shows one pair large -- turning
any pot snaps it to that pot's pair (1-2, 3-4, 5-6, 7-8), each param as
`P<n> name` over a big value. The 8 pot LEDs show all 8 values.

The pots are scaled takeover: turning one always moves its parameter,
scaled so the knob and the value converge without a jump, so a nudged
pot never snaps a drone.

## Controls

- bottom pads (1-8) .. the 8 scale degrees (natural minor), one note each
- top pads (9-16) .... transpose the drone: -24 -12 -7 0 +7 +12 +19 +24
                       semitones (pad 12 is home)
- 8 pots ............. 8 params at once; screen shows the last-turned pair
- up / down buttons .. octave down / up (C1 .. C5)
- encoder turn ....... octave down / up (same as the buttons)
- encoder press ...... latch on / off -- the drone keeps sounding after
                       you let go, so both hands are free for the knobs
- left slider ........ nudge filter cutoff (while touched)
- right slider ....... the span ribbon: swarm spread (while touched)
- pot LEDs .......... all 8 param values
- step LEDs ......... held / latched degree, and the chosen transposition
- play LED .......... lit while latched

Bottom-row pads are last-note priority, so rolling a finger across them
glides the drone instead of cutting it. Both sliders move the parameter
itself, so the screen, the pot LED and the pot's takeover all follow
the ribbon.

Page SWARM:  spred drift count wave  freq reso glide rel

- `spred` .. the outermost oscillator's offset, in octaves. 0 is unison,
             0.01 is +/-12 cents, 0.4 is an equidistant cluster spread
             over most of an octave either way.
- `drift` .. depth of each oscillator's slow independent wander. 0 is
             perfect digital tuning, which sounds like a chorus pedal;
             a few thousandths is what makes the swarm breathe.
- `count` .. oscillators per note, 1 to 8.
- `wave` ... SAW SQU TRI SIN ASAW ATRI ASQU SSQU.
- `glide` .. portamento, the pitch ribbon's glissando.

## MIDI

Responds to NOTE ON/OFF on any channel (monophonic), CC 1 (swarm
spread), CC 74 (filter cutoff), CC 120/123 (all notes off). Sends NOTE
ON/OFF for every pitch the pads trigger, on USB and UART -- including
the off that a pitch change implies, since the synth is mono.

A note arriving over MIDI is played as sent, so the top row has nothing
to re-aim while it sounds: the transposition you pick applies to the
next pad press.

## Running it

From `circuitpython/`:

    circup install -r requirements.txt

That installs `synthtools` and the other third-party libraries, plus
the local `lib/` modules (`relic_synthiota.py`, `synthiota_potpage_ui.py`).

Copy to the CIRCUITPY root: the contents of this folder, plus
`lib/synthtools/` and the `lib/*.py` modules.

`relic_synthiota.py` originates at
github.com/relic-se/CircuitPython_Synthiota

## Notes

- `wave` and `count` apply at the NEXT note-on: the waveform is baked
  into each `synthio.Note` and the count decides how many Notes a press
  builds. Re-press a pad to hear either one change. `spred` and `drift`
  are each one write into a shared block and move a held drone live,
  which is the whole point of the engine.
- Turning `count` down under a held drone re-tunes it: the fan
  coefficients are shared, so the sounding oscillators re-space to the
  new count even though they keep their number.
- `rel` stops at 2.0s on purpose. Mono at 8 oscillators is 8 Notes,
  16 while a steal overlaps the releasing swarm with the new one,
  against synthio's 24. A longer tail plus a fast roll across pads
  stacks a third releasing swarm and the oldest gets dropped.
- `SwarmSynth.FILT_F_MAX` is set from `sample_rate * 0.45` before the
  synth is constructed: the Nyquist clamp is baked into the block graph
  at build time.
- The mixer voice runs at 0.8 because each Note is amplitude
  `velocity / 127 / swarm_count`: detuned oscillators beat, so their
  peaks do periodically line up, and the level is made back up here.
- Audio runs at 44100 Hz. If it glitches, set SAMPLE_RATE to 22050.
