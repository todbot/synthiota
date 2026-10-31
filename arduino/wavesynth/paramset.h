// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// paramset.h - synthtools' ParamSet in KNOB_SCALE mode: NK knobs over
//              pages of NK params. A turn always moves the value, by the
//              knob's movement scaled by the runway each has left, so
//              knob and value converge without a jump:
//                knob rising:   val += dk * (hi - val) / (1 - k_was)
//                knob falling:  val += dk * (val - lo) / k_was

#pragma once

struct Param {
  const char *name;
  float *v;  // the live value: anything else that sets it writes here too
  float lo, hi;
  float step;  // serial '['/']'
  const char *fmt;
  const char *(*text)(int) = nullptr;  // for discrete params
  float span() { return hi - lo; }
  float norm() { return span() > 0 ? (*v - lo) / span() : 0; }
};

template <int NK>
class ParamSet {
 public:
  Param *params;
  int nparams;

  ParamSet(Param *p, int n, float deadband) : params(p), nparams(n), deadband(deadband) {}

  int pages() { return nparams / NK; }
  int page() { return idx; }
  Param &knob(int k) { return params[idx * NK + k]; }
  void setPage(int i) {
    idx = i;
    readopt();
  }
  // after a page turn or a patch load: the knobs haven't moved but the
  // params under them have
  void readopt() {
    adopted = false;
    for (int k = 0; k < NK; k++) tracking[k] = false;
  }

  // returns a bit per knob whose param changed
  uint32_t update(const float *knobs) {
    if (!adopted) {
      for (int k = 0; k < NK; k++) last[k] = knobs[k];
      adopted = true;
      return 0;
    }
    uint32_t changed = 0;
    for (int k = 0; k < NK; k++) {
      Param &p = knob(k);
      float kv = knobs[k], was = last[k], dk = kv - was;
      // last stays put so slow turns accumulate past the deadband
      if (-deadband < dk && dk < deadband) continue;
      last[k] = kv;
      float before = *p.v;
      float nv = p.lo + p.span() * kv;
      if (tracking[k]) {
        *p.v = nv;
      } else if (fabsf(nv - *p.v) < MIN_CHANGE * p.span() && (nv - *p.v) * dk >= 0) {
        // catch up, but never against the turn
        tracking[k] = true;
        *p.v = nv;
      } else {
        if (dk > 0) {
          *p.v = was < 1 ? *p.v + dk * (p.hi - *p.v) / (1 - was) : p.hi;
        } else {
          *p.v = was > 0 ? *p.v + dk * (*p.v - p.lo) / was : p.lo;
        }
        *p.v = constrain(*p.v, p.lo, p.hi);  // first-order on big steps
      }
      if (*p.v != before) changed |= 1UL << k;
    }
    return changed;
  }

 private:
  static constexpr float MIN_CHANGE = 0.05f;
  float deadband;
  int idx = 0;
  bool adopted = false;
  bool tracking[NK];
  float last[NK];
};
