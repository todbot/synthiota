# dronesynth_wt for synthiota

`dronesynth` with a wavetable where its waveform was. Eight drone
oscillators, each tuned by its own knob, and each sitting at its own
position in one shared wavetable. What an oscillator's wave LFO sweeps
is that position, not its pitch: a drone that moves in timbre while it
stays in tune.

Everything else is dronesynth. There is no scale, no sequencer and
nothing to play. You tune the eight oscillators against each other,
move each one to a different place in the table, switch them in and out,
and set each one wobbling at its own speed.

The eight start an octave apart in pairs, so the knobs cover five
octaves between them, and a tenth of the table apart, so they are eight
timbres rather than one in unison.

The pad grid is split the way the controls are: the **bottom row** is
the oscillator, the **top row** is its LFO.

Tap a bottom pad to switch its oscillator in and out. Hold it and turn
that oscillator's own knob for its volume, or hold it and use up/down to
shift it an octave.

Tap a top pad to cycle its LFO: off, wave (green), volume (blue), both
at once (cyan). Hold the pad and turn the encoder for the rate of
whichever of the two it is driving, from one cycle every 50 seconds to
10 Hz, press the encoder for that one's shape, or turn that
oscillator's own knob for its depth. On wave, depth is how far up the
table the sweep reaches.

Wave and volume are two separate LFOs, each with its own rate, shape
and depth, and a held top pad reaches whichever of them the mode is
driving. So tap to wave and set its rate, shape and range, tap to
volume and set that one, and both are remembered when you tap to both.
In both mode the pair moves together: a click of the encoder is a click
on each of them, a press puts both on the wave one's shape, and the
screen shows the wave one.

Hold a bottom pad **and** the top pad above it, then turn that
oscillator's knob, to move where it starts in the table.

So the three things a sweep needs are three gestures: **start** is both
of a column's pads plus the knob, **range** a held top pad plus the
knob, **rate** a held top pad plus the encoder.

Both rows are tap-or-hold, and a tap acts when you lift: holding a pad
makes it a modifier, so it never also switches an oscillator or cycles
a mode.

Everything is live and nothing is quantized to a beat, so the eight LFOs
drift in and out of phase with each other for as long as you leave it
running. Boots with oscillator 1 sounding.

## Controls

- 8 pots ......... oscillator pitch, 2 octaves per pot
- bottom pads .... tap: oscillator in / out
                   hold + its own pot: that oscillator's volume
                   hold + up/down: shift that oscillator by an octave,
                   up to two either way
- top pads ....... tap: LFO off -> wave -> volume -> both -> off
                   hold + encoder turn: the rate of the LFO that
                   oscillator drives, or both while it is off
                   hold + encoder press: that LFO's shape, cycling
                   TRI D10 D30 D50 D70 D90
                   hold + its own pot: the depth of what that LFO
                   drives, or both of them while it is off
- both pads ...... hold + its own pot: where in the table that
                   oscillator starts
- encoder turn ... the wavetable, when no top pad is held
- encoder press .. pitch snap: semitones / free, no top pad held
- up / down ...... the octave all eight pots start from; oscillator 1-2
                   lands on C0, C1, C2 or C3 and the rest sit above it
- left slider .... tap an end: filter cutoff down / up
- right slider ... tap an end: the depth master, over all sixteen
                   depths at once, down / up
                   hold either end and it repeats
- bottom LEDs .... amber where an oscillator is in
- top LEDs ....... green wave LFO, blue volume LFO, cyan both, each
                   pulsing at its own rate; white while a knob or the
                   encoder is steering it
- pot LEDs ....... where each oscillator is in the table, white on the
                   one knob that is moving where it starts, amber on the
                   one setting a volume, magenta on the one setting a
                   depth, each showing what it is setting
- mode LED ....... lit while pitch snap is on
- edit LED ....... lit while a held pad is steering
- play LED ....... lit while any oscillator is in
- screen ......... header: the loaded wavetable, and semi / free.
                   Per oscillator: LFO mode (`.` `W` `V` `B`), the note
                   it is tuned to, and an underline while it sounds.
                   The status line is cutoff and the depth master, or
                   `L4 W 18.9s D10 30%` for the LFO being steered (which
                   of the two, its rate, its shape, its depth),
                   `L4 18.9s D10 30/75` for the wave one plus both
                   depths while the pair moves together, `O4 volume 80%`
                   for an oscillator's level, or `O4 start 12.4 of 63`
                   for where one starts in the table.

The sweep always runs **up** from the start wave, whatever the shape, so
the start is a floor and not a midpoint. A decay snaps to the top of the
range and falls back to the start; the triangle climbs and comes back
down. A sweep that would run off the end of the table stops there.

Pitch snap is on at boot: each pot lands on a semitone, which is how you
tune intervals that stay put. Press the encoder for free tuning and the
pots sweep continuously, for the beating two oscillators a few cents
apart make. Snapping back on leaves the detuned oscillators where they
are; each one lands on a semitone the next time its pot or an octave
button moves it.

The encoder's rate clicks are not evenly spaced: a click is 4% of the
rate down at 50 seconds a cycle and 30% up at 10 Hz, so 38 of the 53
clicks end to end sit below 0.5 Hz, where a drone lives.

A wave sweep is pushed into the waveform buffers from the main loop, a
few hundred times a second at best, so a sweep much above a few hertz
will step. The heartbeat prints the loop rate it is actually getting.
The volume LFO is sample-accurate however fast it goes, and it keeps
its own rate, so the top of the range is worth having there even where
a wave sweep cannot use it.

## MIDI

CC only, on any channel: CC 74 (filter cutoff), CC 1 (the depth master),
CC 120/123 (all oscillators out). Notes are ignored and none are sent --
the pots own the pitches, so there is nothing for a note to set.

## Running it

From `circuitpython/`:

    circup install -r requirements.txt

Copy to the CIRCUITPY root: the contents of this folder, plus
`lib/synthtools/` and `lib/relic_synthiota.py`.

**Then copy `wavesynth/wavetables/` to the CIRCUITPY root as
`/wavetables/`.** The tables are not duplicated in this folder, and
without them the program raises at boot instead of starting.

`relic_synthiota.py` originates at
github.com/relic-se/CircuitPython_Synthiota

## Notes

- Raw synthio, not a `synthtools` Synth: a `Synth`'s voices are keyed to
  midi notes and built at note-on, and these eight oscillators are
  free-running and separately tuned. They are eight `synthio.Note`
  objects pressed and released in place, with `synthtools` supplying the
  scalar blocks behind the shared cutoff.
- `wave_bank.py` is local, not `synthtools.Wavetable`. Wavetable owns
  the one buffer it reads into, which is what a polysynth wants: every
  voice shares the position. Eight drones want eight positions out of
  one table, and eight Wavetables would be eight 32 KB copies of it.
  `WaveBank` is one table, one scratch pair, and a buffer per caller;
  it is headed for `synthtools` once it has earned it.
- The table is allocated at boot, before the display and the screen
  labels have had a go at the heap, and the encoder rewrites it in
  place. Reading a whole 32 KB table into a fresh array mid-session
  needs that much contiguous heap, which a running instrument cannot
  guarantee and has nothing to fall back on if it fails. It is held one
  array per wave rather than as one block, so even at boot the biggest
  thing it ever asks the allocator for is 512 bytes.
- A table past 64 waves of 256 samples is truncated to the first 64, and
  a file with fewer than two waves in it is refused before the table it
  would have replaced is touched.
- Eight lerps is the most expensive thing in the loop, and it runs every
  pass rather than at UI rate, because nothing else moves the wave
  position and 20 Hz steps audibly. An oscillator that is out, or whose
  position has not moved by a hundredth of a wave, costs nothing. The
  heartbeat prints the loop rate and the free heap, which is where to
  look if it ever sounds like it is struggling.
- The lerp runs in float and accumulates in place. In int16 two samples
  straddling zero at high amplitude wrap on the subtract and overflow on
  the store back; out of place it would be another two arrays of garbage
  per fill, eight times a pass.
- Each oscillator has its OWN waveform buffer, where dronesynth shares
  one between all eight. That is the whole difference in the audio
  graph: eight positions cannot share a buffer.
- Wave and volume are an LFO each, two per oscillator, fully
  independent: own rate, own shape buffer, own depth. One block carries
  one scale and one offset, so the two destinations needed two blocks
  whatever happened. Both are scaled whatever the mode is, which leaves
  the pad LED a swing to pulse with and makes a mode change nothing but
  a reroute.
- The volume LFOs take the eight default rates backwards, so no pair
  starts together. A click of the encoder with both routed is a click on
  each of them, which holds a ratio but cannot open one up: two LFOs
  left at the same rate would stay there for good.
- A per-oscillator level scales `OSC_AMP`, and the volume LFO swings
  under that level rather than around it, so eight oscillators at full
  level are still the eight that were measured against the soft knee.
  The knob reaches 1.0 and stops.
- Nothing in synthio reads the wave LFO: a waveform is a plain buffer,
  not a block-driven parameter, so the only thing that moves it is
  `update_waves()` reading `lfo.value` from the loop. Both LFOs are
  rooted in `synth.blocks` regardless, because an unattached block
  freezes and would jump phase the moment it was read.
- Wave positions and ranges are kept as fractions of the table, not as
  wave numbers, so they survive a switch to a table with a different
  number of waves in it.
- The volume LFO swings the amplitude between `(1 - depth)` and 1 of
  the oscillator's level, never below zero: a negative amplitude flips
  the phase instead of going quiet, which tremolos at twice the rate.
  The decay shapes run 1 to 0 rather than -1 to 1, so they take the
  whole of that span from the top while the triangle takes half of it
  either side of the middle.
- `OSC_AMP` is 0.26, not dronesynth's 0.3. Measured across all 11
  tables, every one of them is peak-normalized to the rail, where
  `get_wave()` builds its saw at 28000: left at 0.3 the eight
  oscillators would sit on synthio's soft knee instead of at the 86% of
  it that dronesynth measured, so the level is scaled back by that same
  28000/32767. Peak is what the knee limits, and this puts it back where
  it was measured. RMS is not: a frame of full-rail square carries twice
  the saw's, so a table of those sounds hotter than a table of sines
  however the peaks line up. Make it back up at the mixer voice if a
  particular table wants it.
- A resting pot has to be dead still, because pot position *is* pitch:
  rest jitter measures about 0.004 on these muxed pots, which over a
  2-octave pot is 10 cents of warble on every sounding oscillator. So a
  pot only reaches the pitch for 0.4s after it last moved more than 1%
  of its travel. The cost is that a nudge smaller than about a quarter
  semitone does nothing from rest -- move past that and then fine-tune
  inside the window, or keep turning.
- A knob steered by a held pad moves what it steers *relatively*, by
  however far the knob travels, so neither a depth nor a wave position
  jumps to wherever the pitch left the knob. The pitch itself stays put
  until that pot is turned again with the pad up, and then it goes to
  where the knob now points.
- Both strips are read as four buttons, not as positions: a tap on an
  end steps its parameter, a hold repeats after 0.35s. The continuous
  position of these strips reads too roughly on this board to play with,
  and the pads' own touch thresholds are solid. The strips have no LEDs
  of their own to show the value with -- relic's `left_slider_leds` are
  the same pixels as pot LEDs 1-3 -- so the screen's `cut` and `mod`
  readout is the indicator.
- Each of the sixteen LFOs owns a 128-sample waveform buffer that its
  shape is written into in place, because `synthio.LFO.waveform` is
  read-only once the LFO is built. 4 KB for the lot.
- Each oscillator carries its own `synthio.Biquad` because filters hold
  state and cannot be shared; the cutoff and Q are shared blocks, so the
  slider is one write for all eight.
- Audio runs at 44100 Hz, the CPU at 200 MHz on RP2350 and 250 on
  RP2040. If audio glitches, set SAMPLE_RATE to 22050.
- Temporary, to be pulled once the hardware is signed off: a heartbeat
  line on serial every 2s (loop rate, errors, oscillators in, free heap,
  cutoff) and a catch around the loop that prints a traceback rather
  than dying mid-play.
