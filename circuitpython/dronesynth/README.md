# dronesynth for synthiota

Eight drone oscillators, each tuned by its own knob. Not a keyboard
instrument and not a swarm: there is no scale, no sequencer and nothing
to play. You tune the eight oscillators against each other, switch them
in and out, and set each one wobbling at its own speed.

The eight start an octave apart in pairs, so the knobs cover five
octaves between them rather than all landing in the same two.

The pad grid is split the way the controls are: the **bottom row**
switches oscillator 1-8 in and out, the **top row** is that oscillator's
own LFO. Tap a top pad to cycle its LFO: off, pitch (green), volume
(blue). Hold the pad and turn the encoder for that LFO's rate, from one
cycle every 50 seconds to 20 Hz, press the encoder for its shape, or
turn that oscillator's own knob for its depth.

Both rows are tap-or-hold, and a tap acts when you lift: holding a pad
makes it a modifier, so it never also switches an oscillator or cycles
a mode.

Everything is live and nothing is quantized to a beat, so the eight LFOs
drift in and out of phase with each other for as long as you leave it
running. Boots with oscillator 1 sounding.

## Controls

- 8 pots ......... oscillator pitch, 2 octaves per pot
- bottom pads .... tap: oscillator in / out
                   hold + up/down: shift that oscillator by an octave,
                   up to two either way
- top pads ....... tap: LFO off -> pitch -> volume -> off
                   hold + encoder turn: that LFO's rate
                   hold + encoder press: that LFO's shape, cycling
                   TRI D10 D30 D50 D70 D90
                   hold + its own pot: that LFO's depth
- encoder turn ... waveform, when no top pad is held
- encoder press .. pitch snap: semitones / free, no top pad held
- up / down ...... the octave all eight pots start from; oscillator 1-2
                   lands on C0, C1, C2 or C3 and the rest sit above it
- left slider .... tap an end: filter cutoff down / up
- right slider ... tap an end: the LFO depth master down / up
                   hold either end and it repeats
- bottom LEDs .... amber where an oscillator is in
- top LEDs ....... green pitch LFO, blue volume LFO, pulsing at its own
                   rate; white while a knob or the encoder is steering it
- pot LEDs ....... the eight pot positions, magenta on the one knob
                   that is setting a depth
- mode LED ....... lit while pitch snap is on
- edit LED ....... lit while a held pad is steering an LFO
- play LED ....... lit while any oscillator is in
- screen ......... per oscillator: LFO mode (`.` `P` `V`), the note it is
                   tuned to, and an underline while it sounds. The status
                   line is cutoff and the depth master, or the rate,
                   shape and depth of whichever LFO is being steered.
                   A rate under 1 Hz reads as seconds a cycle.

Pitch snap is on at boot: each pot lands on a semitone, which is how you
tune intervals that stay put. Press the encoder for free tuning and the
pots sweep continuously, for the beating two oscillators a few cents
apart make. Snapping back on leaves the detuned oscillators where they
are; each one lands on a semitone the next time its pot or an octave
button moves it.

The encoder's rate clicks are not evenly spaced: a click is 4% of the
rate down at 50 seconds a cycle and 30% up at 20 Hz, so two thirds of
the encoder's travel sits below 0.5 Hz where a drone lives. End to end
is about 58 clicks.

The LFO shapes are a triangle and five decays, named for how much of
the cycle the decay takes: `TRI D10 D30 D50 D70 D90`. Each one snaps to
full and falls away exponentially, four e-foldings over that fraction,
so it is spent before the cycle turns over. D10 is a ping, D90 a long
sag that never quite settles.

A decay only pushes one way, up from the tuned pitch or down from the
oscillator's level, so a pinged oscillator sits exactly where you tuned
it between pings. The triangle is the one shape that swings both ways,
and on pitch it is the only one that detunes an oscillator flat as well
as sharp.

## MIDI

CC only, on any channel: CC 74 (filter cutoff), CC 1 (the depth master),
CC 120/123 (all oscillators out). Notes are ignored and none are sent --
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
- Levels are measured, not guessed: rendered offline against real
  synthio, an oscillator at 1/8 of full scale peaks at 4% FS, which is
  inaudible. At `OSC_AMP = 0.3` with the mixer wide open one oscillator
  is 15% FS and all eight ride synthio's 28000 soft knee at 86% with no
  rail samples, in unison as well as spread out.
- Both strips are read as four buttons, not as positions: a tap on an
  end steps its parameter, a hold repeats after 0.35s. The continuous
  position of these strips reads too roughly on this board to play with,
  and the pads' own touch thresholds are solid. The strips have no LEDs
  of their own to show the value with -- relic's `left_slider_leds` are
  the same pixels as pot LEDs 1-3 -- so the screen's `cut` and `mod`
  readout is the indicator.
- A resting pot has to be dead still, because pot position *is* pitch:
  rest jitter measures about 0.004 on these muxed pots, which over a
  2-octave pot is 10 cents of warble on every sounding oscillator. So a
  pot only reaches the pitch for 0.4s after it last moved more than 1%
  of its travel. The cost is that a nudge smaller than about a quarter
  semitone does nothing from rest -- move past that and then fine-tune
  inside the window, or keep turning.
- A knob setting a depth moves it *relatively*, by however far the knob
  travels, so the depth does not jump to wherever the pitch left the
  knob. The pitch itself stays put until that pot is turned again with
  the pad up, and then it goes to where the knob now points.
- Each LFO owns a 128-sample waveform buffer that its shape is written
  into in place, because `synthio.LFO.waveform` is read-only once the
  LFO is built. 128 leaves the shortest decay a dozen samples, and the
  LFO interpolates between them, so a coarser table would step the
  modulation audibly.
- All eight oscillators read one shared waveform buffer, which the
  encoder writes into rather than handing out a new array, so a waveform
  change reaches oscillators already sounding.
- The volume LFO swings the amplitude between `(1 - depth)` and 1 of
  the oscillator's level, never below zero: a negative amplitude flips
  the phase instead of going quiet, which tremolos at twice the rate.
  The decay shapes run 1 to 0 rather than -1 to 1, so they take the
  whole of that span from the top while the triangle takes half of it
  either side of the middle.
- Each oscillator carries its own `synthio.Biquad` because filters hold
  state and cannot be shared; the cutoff and Q are shared blocks, so the
  slider is one write for all eight.
- Every LFO is rooted in `synth.blocks`, so it keeps running while it
  is routed nowhere or its oscillator is out. An unattached block
  freezes, and would jump phase the moment it was routed.
- Audio runs at 44100 Hz, the CPU at 200 MHz on RP2350 and 250 on
  RP2040. The loop measures 216 Hz on a Pico 2. If audio glitches, set
  SAMPLE_RATE to 22050.
- Temporary, to be pulled once the hardware is signed off: a heartbeat
  line on serial every 2s (loop rate, errors, oscillators in, the LED
  values written) and a catch around the loop that prints a traceback
  rather than dying mid-play.
