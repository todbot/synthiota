// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// ui.h - the two-up param screen of circuitpython/lib/synthiota_potpage_ui:
//        a header (page name, page n/N, key+octave) over one pair of the
//        page's 8 params, name small and value big. The caller picks the
//        pair, normally the last pot turned.

#pragma once
#include "hw.h"
#include "paramset.h"

void param_text(Param &p, char *buf, int len) {
  if (p.text) snprintf(buf, len, "%s", p.text(lroundf(*p.v)));
  else snprintf(buf, len, p.fmt, *p.v);
}

class PotPageUI {
 public:
  PotPageUI(ParamSet<8> &ps, const char *const *page_names)
    : ps(ps), page_names(page_names) {}

  void showPair(int pair) { shown = pair; }

  // redraws only if the text changed; true if it did
  bool update(const char *right_hdr) {
    char txt[sizeof(seen)];
    char *t = txt;
    t += snprintf(t, 24, "%-8.8s|%d/%d|%-5.5s|", page_names[ps.page()],
                  ps.page() + 1, ps.pages(), right_hdr);
    for (int s = 0; s < 2; s++) {
      int k = shown * 2 + s;
      Param &p = ps.knob(k);
      char val[16];
      param_text(p, val, sizeof(val));
      t += snprintf(t, 24, "P%d %s|%.5s|", k + 1, p.name, val);
    }
    if (!strcmp(txt, seen)) return false;
    strcpy(seen, txt);
    draw(txt);
    return true;
  }

 private:
  ParamSet<8> &ps;
  const char *const *page_names;
  int shown = 0;
  char seen[96] = "";

  // txt is '|'-separated: page, n/N, right header, then name/value x2
  void draw(char *txt) {
    const int16_t COL_X[2] = { 2, 68 };
    char *f[7];
    for (int i = 0; i < 7; i++) f[i] = strsep(&txt, "|");
    disp.clearDisplay();
    disp.setTextColor(SH110X_WHITE);
    disp.setTextSize(1);
    disp.setCursor(2, 4);
    disp.print(f[0]);
    disp.setCursor(62, 4);
    disp.print(f[1]);
    disp.setCursor(102, 4);
    disp.print(f[2]);
    for (int s = 0; s < 2; s++) {
      disp.setTextSize(1);
      disp.setCursor(COL_X[s], 20);
      disp.print(f[3 + s * 2]);
      disp.setTextSize(2);
      disp.setCursor(COL_X[s], 35);
      disp.print(f[4 + s * 2]);
    }
  }
};
