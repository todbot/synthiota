// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// synth_engine.h - the wavesynth voice, ported from synthtools'
//                  WavetableSynth + Synth (circuitpython/wavesynth's
//                  engine). Per voice: WaveOsc -> multimode filter -> amp
//                  ADSR, with a filter envelope and a pitch envelope.
//                  Shared, as in synthtools: the filter LFO, vibrato and
//                  the wave-position LFO. Modulation runs at control rate.
//
// Params are written by core0 and read by core1 each control tick; each
// is one aligned 32-bit float, so a write can't tear.

#pragma once
#include <ADSR.h>
#include <ResonantFilter.h>
#include <mozzi_midi.h>
#include "wave_osc.h"

enum FiltType { FILT_LPF, FILT_HPF, FILT_BPF, FILT_NOTCH };

// field names follow circuitpython/wavesynth's PARAMS; defaults are its
// default_patches() over synthtools' Patch defaults
struct Params {
  float freq = 2345;    // filter cutoff, Hz
  float reso = 1.1;     // filter Q, 0.6 - 6
  float ftype = FILT_LPF;
  float wpos = 0;       // 0..1 across the table
  float wlfo = 0;       // wave-LFO ceiling, 0..1; <= wpos means no sweep
  float wrate = 0.5;    // Hz
  float wshp = 0;       // 0 triangle, 1 saw
  float w1x = 0;        // 1: sweep once per note from silence, then hold
  float wvel = 0;       // 0..1, how much velocity scales the sweep depth
  float atk = 0.01, dec = 0.10, sus = 0.9, rel = 0.5;  // amp ADSR, s
  float fatk = 0.2, frel = 0.6;  // filter envelope, s
  float famt = 1500;    // Hz added at the envelope's peak; may be negative
  float lamt = 0;       // filter LFO, Hz added above freq (0..lamt)
  float lrate = 0.5;    // Hz
  float vdep = 0;       // vibrato depth, octaves
  float vrate = 5;      // Hz
  float pamt = 0;       // pitch envelope start, octaves off pitch
  float ptime = 0.1;    // s to settle to true pitch
  float vol = 0.6;
};

// synthtools divides each voice so chords don't hit the mix limiter
#define VOICE_HEADROOM 0.5f
#define CTL_DT (1.0f / MOZZI_CONTROL_RATE)
#define FILT_F_MIN 20.0f
#define FILT_F_MAX (MOZZI_AUDIO_RATE * 0.45f)

// triangle, 0..1 over phase 0..1
static inline float tri01(float p) { return p < 0.5f ? 2 * p : 2 - 2 * p; }

class Voice {
 public:
  WaveOsc osc;

  void noteOn(uint8_t n, uint8_t v) {
    note = n;
    vel = v / 127.0f;
    fenv = 0;
    penv = 1;
    gate = true;
    env.noteOn();
  }
  void noteOff() {
    gate = false;
    env.noteOff();
  }
  bool playing() { return env.playing(); }
  uint8_t current() { return note; }

  // control rate; vib in octaves and lfo01 (filter LFO, 0..1) are shared
  void control(const Params &p, float vib, float lfo01) {
    setEnvTimes(p);
    env.update();

    fenv += gate ? CTL_DT / max(p.fatk, CTL_DT) : -CTL_DT / max(p.frel, CTL_DT);
    fenv = constrain(fenv, 0.0f, 1.0f);
    penv = max(penv - CTL_DT / max(p.ptime, CTL_DT), 0.0f);

    osc.setFreq(mtof(note) * exp2f(vib + penv * p.pamt));

    float cut = p.freq + lfo01 * p.lamt + fenv * p.famt;
    cut = constrain(cut, FILT_F_MIN, FILT_F_MAX);
    // Mozzi's cutoff is linear to Nyquist; its resonance isn't a Biquad Q,
    // so this curve is by ear: Q 0.6 ~ none, Q 6 just short of oscillating
    float res = constrain((p.reso - 0.6f) / 5.4f, 0.0f, 1.0f) * 0.93f;
    filt.setCutoffFreqAndResonance(cut / (MOZZI_AUDIO_RATE / 2) * 65535, res * 65535);
    type = (uint8_t)(p.ftype + 0.5f);

    gain = (int32_t)(vel * VOICE_HEADROOM * p.vol * 256);
  }

  inline int32_t next() {
    filt.next(osc.next());
    int32_t s = type == FILT_LPF ? filt.low()
              : type == FILT_HPF ? filt.high()
              : type == FILT_BPF ? filt.band() : filt.notch();
    return ((s * env.next()) >> 8) * gain >> 8;
  }

 private:
  ADSR<MOZZI_CONTROL_RATE, MOZZI_AUDIO_RATE> env;
  MultiResonantFilter<uint16_t> filt;
  uint8_t note = 60, type = FILT_LPF;
  float vel = 1, fenv = 0, penv = 0;
  bool gate = false;
  int32_t gain = 0;
  float last_a = -1, last_d, last_s, last_r;

  // only when they change: setTimes recomputes the ADSR's increments
  void setEnvTimes(const Params &p) {
    if (p.atk == last_a && p.dec == last_d && p.sus == last_s && p.rel == last_r) return;
    last_a = p.atk; last_d = p.dec; last_s = p.sus; last_r = p.rel;
    env.setADLevels(255, (uint8_t)(constrain(p.sus, 0.0f, 1.0f) * 255));
    env.setTimes(p.atk * 1000, p.dec * 1000, 60000, p.rel * 1000);
  }
};

class Engine {
 public:
  Voice voice;

  void noteOn(uint8_t n, uint8_t v, const Params &p) {
    if (p.w1x >= 0.5f && !voice.playing()) wphase = 0;  // one-shot restarts
    wave_vel = v / 127.0f;
    voice.noteOn(n, v);
  }
  void noteOff(uint8_t n) {
    if (voice.current() == n) voice.noteOff();
  }

  void control(const Params &p, const int16_t *table, uint16_t num_waves) {
    lphase = fmodf(lphase + p.lrate * CTL_DT, 1);
    vphase = fmodf(vphase + p.vrate * CTL_DT, 1);
    bool once = p.w1x >= 0.5f;
    wphase += p.wrate * CTL_DT;
    wphase = once ? min(wphase, 1.0f) : fmodf(wphase, 1);

    float pos = p.wpos;
    if (p.wlfo > p.wpos) {
      float w = p.wshp >= 0.5f ? wphase : tri01(wphase);
      float depth = 1 - p.wvel + p.wvel * wave_vel;
      pos += (p.wlfo - p.wpos) * depth * w;
    }
    uint32_t span = num_waves > 1 ? num_waves - 1 : 0;
    voice.osc.setTable(table, num_waves);
    voice.osc.setWavePos((uint32_t)(constrain(pos, 0.0f, 1.0f) * span * 65535));

    float vib = (tri01(vphase) * 2 - 1) * p.vdep;
    voice.control(p, vib, tri01(lphase));
  }

  inline int32_t next() { return voice.next(); }

 private:
  float lphase = 0, vphase = 0, wphase = 0, wave_vel = 1;
};
