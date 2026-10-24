# dronesynth for synthiota

Eight drone oscillators, each tuned by its own knob. Not a keyboard
instrument and not a swarm: there is no scale, no sequencer and nothing
to play. You tune the eight oscillators against each other, switch them
in and out, and set each one wobbling at its own speed.

The pad grid is split the way the controls are: the **bottom row**
switches oscillator 1-8 in and out, the **top row** is that oscillator's
own LFO. Tap a top pad to cycle its LFO: off, pitch (green), volume
(blue). Hold the pad and turn the encoder to set that LFO's rate, from
one cycle a minute to 20 Hz.

Everything is live and nothing is quantized to a beat, so the eight LFOs
drift in and out of phase with each other for as long as you leave it
running. Boots with oscillator 1 sounding.

## Controls

- 8 pots ......... oscillator pitch, 2 octaves per pot
- bottom pads .... oscillator in / out
- top pads ....... tap: LFO off -> pitch -> volume -> off
                   hold + encoder turn: that LFO's rate
- encoder turn ... waveform, when no top pad is held
- encoder press .. pitch snap: semitones / free
- up / down ...... the octave the pots start from: C0, C1, C2, C3
- left slider .... filter cutoff (while touched)
- right slider ... LFO depth, both kinds (while touched)
- bottom LEDs .... amber where an oscillator is in
- top LEDs ....... green pitch LFO, blue volume LFO, pulsing at its own
                   rate; white while the encoder is steering it
- pot LEDs ....... the eight pot positions
- mode LED ....... lit while pitch snap is on
- edit LED ....... lit while the encoder is steering an LFO rate
- play LED ....... lit while any oscillator is in
- screen ......... per oscillator: LFO mode (`.` `P` `V`), the note it is
                   tuned to, and an underline while it sounds

Pitch snap is on at boot: each pot lands on a semitone, which is how you
tune intervals that stay put. Press the encoder for free tuning and the
pots sweep continuously, for the beating two oscillators a few cents
apart make.

## MIDI

CC only, on any channel: CC 74 (filter cutoff), CC 1 (LFO depth), CC
120/123 (all oscillators out). Notes are ignored and none are sent --
the pots own the pitches, so there is nothing for a note to set.

## Running it

From `circuitpython/`:

    circup install -r requirements.txt

Copy to the CIRCUITPY root: the contents of this folder, plus
`lib/synthtools/` and `lib/relic_synthiota.py`.

`relic_synthiota.py` originates at
github.com/relic-se/CircuitPython_Synthiota

## Notes

- Raw synthio, not a `synthtools` Synth: a `Synth`'s voices are keyed to
  midi notes and built at note-on, and these eight oscillators are
  free-running and separately tuned. They are eight `synthio.Note`
  objects pressed and released in place, with `synthtools` supplying the
  waveforms and the scalar blocks behind the shared cutoff.
- A resting pot has to be dead still, because pot position *is* pitch:
  rest jitter measures about 0.004 on these muxed pots, which over a
  2-octave pot is 10 cents of warble on every sounding oscillator. So a
  pot only reaches the pitch for 0.4s after it last moved more than 1%
  of its travel. The cost is that a nudge smaller than about a quarter
  semitone does nothing from rest -- move past that and then fine-tune
  inside the window, or keep turning.
- All eight oscillators read one shared waveform buffer, which the
  encoder writes into rather than handing out a new array, so a waveform
  change reaches oscillators already sounding.
- The volume LFO swings the amplitude between `(1 - depth)` and 1 of the
  oscillator's level, never below zero: a negative amplitude flips the
  phase instead of going quiet, which tremolos at twice the rate.
- Each oscillator runs at 1/8 of full scale with the level made back up
  at the mixer, so eight of them at once cannot clip.
- Each oscillator carries its own `synthio.Biquad` because filters hold
  state and cannot be shared; the cutoff and Q are shared blocks, so the
  slider is one write for all eight.
- Every LFO is also rooted in `synth.blocks`, so it keeps running while
  it is routed nowhere or its oscillator is out. An unattached block
  freezes, and would jump phase the moment it was routed.
- Audio runs at 44100 Hz with the CPU at 200 MHz. Eight filtered
  oscillators is the same load as swarmsynth's eight; if it glitches,
  set SAMPLE_RATE to 22050.
