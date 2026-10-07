# tbish2 for synthiota

A TB-303 inspired monophonic bass synth for Synthiota, on `synthtools`'
`BasslineSynth` and `StepSequencer`. The synth engine comes from
[pico_test_synth](https://github.com/todbot/pico_test_synth)'s `tbish2`;
the controls are this repo's [`tbish/`](../tbish/), which is left as is.

Compared to `tbish/`, the library synth adds:

- accent raises resonance (`accent_q`) and cutoff (`accent_cutoff`),
  not just level, and consecutive accents stack
- a real `slide_time`, and slides that TIE: the pitch glides and the
  envelopes carry on, like the original
- a 24 dB/oct filter, drive (RP2350 only) and delay, all as patch fields

## Modes

The encoder steps through three modes, shown bottom right of the screen
and on the mode LEDs:

- **play** .. the 8 pots are the main 303 knobs: cutoff, envmod, resQ,
  decay, accent, wave, drive, delaymix
- **edit** .. the 8 pots set 8 step notes; the screen shows those 8
  steps, with `A` for accent and `S` for slide over each
- **more** .. the 8 pots are the rest of the synth: ampdec, amplevel,
  acctcut, acctQ, slide, drvamt, dtime, dlyfeed

Patterns are 16 steps, shown 8 at a time: `1-8` or `9-16` top right.
Edit mode works on one half, picked with the left slider's middle;
play and more show whichever half is playing.

In play and more, all 8 pots are live and the screen shows the pair
(1-2, 3-4, 5-6, 7-8) of the pot turned last. The pots are scaled
takeover: a turn always moves its parameter, scaled so knob and value
converge without a jump.

## Controls

- encoder turn ............ next / previous mode
- encoder push ............ play / pause; pausing saves to `/tbish2.json`
- step pads, playing ...... transpose the pattern (pad 9 is home)
- step pads, stopped ...... play the synth
- step pads, edit mode .... bottom row: step note <-> rest;
                            top row: normal -> accent -> slide -> both
- up / down buttons ....... transpose up / down an octave
- right slider, left end .. previous pattern
- right slider, right end . next pattern
- hold either right slider end, turn encoder .. scroll patterns
- left slider, middle ..... edit steps 1-8 / 9-16
- hold left slider left end, turn encoder ... bpm
- hold left slider right end, turn encoder .. steps per beat
- pot LEDs ................ current step, if on the shown half
- step LEDs ............... held pads; in edit mode, the pattern
                            (white = note, red = accent, blue = slide)

There's no MIDI in or out yet.

## Patterns

The first five are famous 303 lines, transcribed at
[JonDent's famous 303 bassline patterns](https://djjondent.blogspot.com/2020/04/famous-303-bassline-patterns-page-1.html).
The original BPM is in a comment on each; tbish2 doesn't change tempo
per pattern.

1. Josh Wink - Higher State of Consciousness (134 BPM)
2. Phuture - Acid Tracks (~120 BPM; notes only, no accents or slides)
3. Fast Eddie - Acid Thunder (x0xb0x transcription)
4. DJ Tim & Misjah - Access (134 BPM)
5. New Order - Confusion, Pump Panel Reconstruction (134 BPM)

The rest are tbish's own 8-step patterns, played twice. Patterns saved
in `/tbish2.json` by an 8-step version are ignored, since they no longer
fit; the knobs and bpm still load.

## Running it

From `circuitpython/`:

    circup install -r requirements.txt

Copy to the CIRCUITPY root: `code.py`, `tbish2_ui.py` and `boot.py` from
this folder, plus `lib/relic_synthiota.py`.

`boot.py` makes the filesystem writable from the board's side, so pause
can save the knobs, bpm and patterns. Without it saving fails with a
printed note, and everything else works.

Needs a CircuitPython build with `audiofilters` and `audiodelays` for
the 24 dB filter, drive and delay. Without them it runs on the voice's
own 12 dB filter and says so at boot.

## Notes

- `decay` is the FILTER fall time in seconds; the amp's decay is its own
  knob (`ampdec`) and wants to stay longer, or the sweep is masked. A run
  of slides is one held note on one amp envelope, so `ampdec` also has to
  outlast the whole run, or its later notes fade to nothing.
- `drive` is the distortion's dry/wet mix, as on tbish; how hard it
  distorts is `drvamt` on the more page. RP2350 only.
- `dtime` is milliseconds.
- Audio runs at 44100 Hz, mono: in stereo the delay's buffer is too big
  to allocate. If it glitches, set SAMPLE_RATE to 22050.
- 303 research links: see [`../tbish/README.md`](../tbish/README.md).
