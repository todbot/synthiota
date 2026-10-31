// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// hw.h - synthiota board controls, core0 only: 8 muxed pots, two MPR121s
//        (16 step pads, up/down, two 3-pad sliders), 27 NeoPixels, the
//        encoder (not yet its switch) and the SH1106. Pins from arduino/hwtest/hwtest1, pad
//        maps from circuitpython/lib/relic_synthiota.py.

#pragma once
#include <Wire.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SH110X.h>
#include <Adafruit_MPR121.h>
#include <Adafruit_NeoPixel.h>
#include <RotaryEncoder.h>

#define i2c_sda_pin    2
#define i2c_scl_pin    3
#define led_pin        18
#define pot_pin        26
#define pot_sel0_pin   9
#define pot_sel1_pin   8
#define pot_sel2_pin   7
#define encoderA_pin   27
#define encoderB_pin   28
#define disp_sclk_pin  10
#define disp_mosi_pin  11
#define disp_res_pin   12
#define disp_dc_pin    13

#define NUM_POTS  8
#define NUM_STEPS 16
#define NUM_LEDS  27
#define LED_POTS  16  // pot LEDs are 16..23; step pad i's LED is LED i

// touch ids
const uint8_t STEP_PADS[NUM_STEPS] = { 7, 6, 5, 4, 3, 2, 1, 0,
                                       8, 9, 10, 11, 18, 17, 16, 15 };
#define PAD_DOWN 19
#define PAD_UP   20
const uint8_t LSLIDE_PADS[3] = { 23, 22, 21 };
const uint8_t RSLIDE_PADS[3] = { 12, 13, 14 };


class Pots {
 public:
  float val[NUM_POTS];  // 0..1

  void begin() {
    for (int b = 0; b < 3; b++) pinMode(sel_pins[b], OUTPUT);
    analogReadResolution(12);
    for (int i = 0; i < NUM_POTS; i++) acc[i] = read(i) << 4;
    update();
  }
  // IIR as relic's >>3, with 4 extra bits so it settles on the reading
  void update() {
    for (int i = 0; i < NUM_POTS; i++) {
      acc[i] += ((read(i) << 4) - acc[i]) >> 3;
      val[i] = acc[i] / (4095.0f * 16);
    }
  }

 private:
  const uint8_t sel_pins[3] = { pot_sel0_pin, pot_sel1_pin, pot_sel2_pin };
  int32_t acc[NUM_POTS];

  int32_t read(int n) {
    for (int b = 0; b < 3; b++) digitalWrite(sel_pins[b], (n >> b) & 1);
    delayMicroseconds(5);  // mux settle
    return analogRead(pot_pin);
  }
};

// relic_synthiota's Slider: position 0..1 from how much of each of a
// pair of pads a finger covers
class Slider {
 public:
  void begin(Adafruit_MPR121 *m, const uint8_t *p) {
    mpr = m;
    pads = p;
    for (int i = 0; i < 3; i++) {
      thresh[i] = chip(i).baselineData(pads[i] % 12);
      if (thresh[i] <= 0) thresh[i] = 254;
    }
  }
  bool touched(uint32_t t) {
    bool on = t & ((1UL << pads[0]) | (1UL << pads[1]) | (1UL << pads[2]));
    if (!on) fresh = true;
    return on;
  }
  // -1 if no position can be read
  float value() {
    float r[3];
    for (int i = 0; i < 3; i++) {
      r[i] = (thresh[i] - chip(i).filteredData(pads[i] % 12)) / thresh[i];
    }
    float a = r[0], b = r[1], c = r[2], v = -1;
    if (a >= 0 && b >= 0 && a + b > 0) v = 0.5f * (b / (a + b));
    else if (b >= 0 && c >= 0 && b + c > 0) v = 0.5f * (1 + c / (b + c));
    else if (a > 0) v = 0;
    else if (b > 0) v = 0.5f;
    else if (c > 0) v = 1;
    if (v < 0) return -1;
    // relic's noise filter alone rejects a new touch far from the last
    if (fresh) fresh = false;
    else if (fabsf(v - last) > 0.5f) return last;
    return last = v;
  }

 private:
  Adafruit_MPR121 *mpr;
  const uint8_t *pads;
  float thresh[3];
  float last = 0;
  bool fresh = true;
  Adafruit_MPR121 &chip(int i) { return mpr[pads[i] / 12]; }
};

class Touch {
 public:
  uint32_t touched = 0;  // bit per touch id 0..23
  Slider lslider, rslider;

  void begin() {
    Wire1.setSDA(i2c_sda_pin);
    Wire1.setSCL(i2c_scl_pin);
    Wire1.begin();
    Wire1.setClock(400000);
    const uint8_t addrs[2] = { 0x5A, 0x5B };
    for (int i = 0; i < 2; i++) {
      if (!mpr[i].begin(addrs[i], &Wire1)) {
        Serial.printf("MPR121 0x%02X not found\n", addrs[i]);
      }
      mpr[i].setAutoconfig(true);  // or touched() never trips on this board
    }
    delay(100);  // let the baselines settle before the sliders take them
    lslider.begin(mpr, LSLIDE_PADS);
    rslider.begin(mpr, RSLIDE_PADS);
  }
  void update() {
    touched = mpr[0].touched() | ((uint32_t)mpr[1].touched() << 12);
  }
  bool pad(uint8_t id) { return touched & (1UL << id); }
  bool step(int i) { return pad(STEP_PADS[i]); }

 private:
  Adafruit_MPR121 mpr[2];
};

Adafruit_NeoPixel leds(NUM_LEDS, led_pin, NEO_GRB + NEO_KHZ800);
Adafruit_SH1106G disp(132, 64, &SPI1, disp_dc_pin, disp_res_pin, -1);
RotaryEncoder encoder(encoderA_pin, encoderB_pin, RotaryEncoder::LatchMode::FOUR3);
Pots pots;
Touch touch;

// a display push or I2C read would drop steps if only loop() ticked it
void encoder_isr() { encoder.tick(); }

void hw_setup() {
  leds.begin();
  leds.setBrightness(77);
  leds.show();

  pots.begin();
  touch.begin();

  attachInterrupt(digitalPinToInterrupt(encoderA_pin), encoder_isr, CHANGE);
  attachInterrupt(digitalPinToInterrupt(encoderB_pin), encoder_isr, CHANGE);

  SPI1.setSCK(disp_sclk_pin);
  SPI1.setTX(disp_mosi_pin);
  disp.begin(0x3C, true);
  disp.clearDisplay();
  disp.display();
}
