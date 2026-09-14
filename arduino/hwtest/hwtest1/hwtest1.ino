// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// h2test1.ino - synthiota1 board bring-up test:
//               I2C scan, dual MPR121 touch -> NeoPixel feedback
//               8-pot mux, rotary encoder + switch, SH1106 SPI OLED status page.
//
//
// Pin map from circuitpython/hwtest/synth_setup_synthiota.py
//
// I2S (GP20/21/22) and UART (GP16/17) are wired but not exercised here,
// matching the CircuitPython hwtest split (audio has its own test).

#include <Wire.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SH110X.h>
#include <Adafruit_MPR121.h>
#include <Adafruit_NeoPixel.h>
#include <RotaryEncoder.h>
#include <Bounce2.h>

#define i2c_sda_pin    2
#define i2c_scl_pin    3
#define led_pin        18
#define pot_pin        26
#define pot_sel0_pin   9
#define pot_sel1_pin   8
#define pot_sel2_pin   7
#define encoderA_pin   27
#define encoderB_pin   28
#define encoderSW_pin  19
#define disp_sclk_pin  10
#define disp_mosi_pin  11
#define disp_res_pin   12
#define disp_dc_pin    13

const int pot_sel_pins[3] = { pot_sel0_pin, pot_sel1_pin, pot_sel2_pin };
const int num_pots = 8;
int pot_vals[num_pots];

const uint8_t mpr121_addrs[2] = { 0x5A, 0x5B };
Adafruit_MPR121 mpr121s[2];

const int num_leds = 8 * 3 + 3;
Adafruit_NeoPixel leds(num_leds, led_pin, NEO_GRB + NEO_KHZ800);

// touch pad index -> led index. The CircuitPython hwtest's touch_to_led
// tuple is indexed the other way around (looked up via .index(touch_id));
// this is that table pre-inverted so it can be indexed directly by touch id.
const int touch_to_led[24] = {
  7, 6, 5, 4, 3, 2, 1, 0,  8, 9, 10, 11,
  21, 22, 23, 15,  14, 13, 12, 20,  19, 18, 17, 16
};

RotaryEncoder encoder(encoderA_pin, encoderB_pin, RotaryEncoder::LatchMode::FOUR3);
Bounce2::Button encoderButton;

Adafruit_SH1106G disp(132, 64, &SPI1, disp_dc_pin, disp_res_pin, -1);

void select_pot(int n) {
  for (int b = 0; b < 3; b++) {
    digitalWrite(pot_sel_pins[b], (n & (1 << b)) != 0);
  }
}

void update_pots() {
  for (int i = 0; i < num_pots; i++) {
    select_pot(i);
    delayMicroseconds(5);  // let mux output settle before the ADC samples
    pot_vals[i] = analogRead(pot_pin);
  }
}

uint32_t update_touch() {
  uint16_t t0 = mpr121s[0].touched();
  uint16_t t1 = mpr121s[1].touched();
  return (uint32_t)t0 | ((uint32_t)t1 << 12);
}

uint32_t colorWheel(byte pos) {
  pos = 255 - pos;
  if (pos < 85) {
    return leds.Color(255 - pos * 3, 0, pos * 3);
  }
  if (pos < 170) {
    pos -= 85;
    return leds.Color(0, pos * 3, 255 - pos * 3);
  }
  pos -= 170;
  return leds.Color(pos * 3, 255 - pos * 3, 0);
}

void update_touch_leds(uint32_t touched) {
  const int dim_by = 15;
  for (int i = 0; i < num_leds; i++) {
    uint32_t c = leds.getPixelColor(i);
    uint8_t r = (uint8_t)(c >> 16), g = (uint8_t)(c >> 8), b = (uint8_t)c;
    leds.setPixelColor(i, r > dim_by ? r - dim_by : 0,
                           g > dim_by ? g - dim_by : 0,
                           b > dim_by ? b - dim_by : 0);
  }
  for (int i = 0; i < 24; i++) {
    if (touched & (1UL << i)) {
      leds.setPixelColor(touch_to_led[i], colorWheel((millis() / 2) & 0xFF));
    }
  }
  leds.show();
}

// layout: a thin encoder line across the top, 8 pots as vertical sliders
// below that, then 24 touch pads as an 8x3 grid of squares at the
// bottom, the pots and pads sharing the same 8-column spacing
const int disp_col_x0 = 4;
const int disp_col_w  = 16;

const int enc_line_x0 = disp_col_x0;
const int enc_line_x1 = disp_col_x0 + (num_pots - 1) * disp_col_w + 8;  // right edge of last pot slider
const int enc_line_y  = 4;
const int enc_knob_r  = 3;
const int enc_ticks   = 16;  // wrap encoder position into this many knob stops

const int slider_top = 9;
const int slider_h   = 30;
const int slider_w   = 8;

const int grid_y0     = 41;
const int grid_row_h  = 7;
const int square_w    = 8;
const int square_h    = 6;

void updateDisplay(uint32_t touched, long encPos, bool encPressed) {
  disp.clearDisplay();

  // encoder: a thin line with a small knob that slides along it as the
  // encoder turns (position wraps -- there's no absolute end to the
  // travel), switching shape while the encoder switch is held down
  disp.drawFastHLine(enc_line_x0, enc_line_y, enc_line_x1 - enc_line_x0, SH110X_WHITE);
  long wrapped = ((encPos % enc_ticks) + enc_ticks) % enc_ticks;
  int knob_x = map(wrapped, 0, enc_ticks - 1,
                    enc_line_x0 + enc_knob_r, enc_line_x1 - enc_knob_r);
  if (encPressed) {
    disp.fillRect(knob_x - enc_knob_r, enc_line_y - enc_knob_r,
                  enc_knob_r * 2, enc_knob_r * 2, SH110X_WHITE);
  } else {
    disp.fillCircle(knob_x, enc_line_y, enc_knob_r, SH110X_WHITE);
  }

  // pots as vertical sliders
  for (int i = 0; i < num_pots; i++) {
    int x = disp_col_x0 + i * disp_col_w;
    disp.drawRect(x, slider_top, slider_w, slider_h, SH110X_WHITE);
    int fill_h = map(pot_vals[i], 0, 1023, 0, slider_h - 2);
    disp.fillRect(x + 1, slider_top + 1 + (slider_h - 2 - fill_h),
                  slider_w - 2, fill_h, SH110X_WHITE);
  }

  // touch pads as an 8x3 grid of squares
  for (int i = 0; i < 24; i++) {
    // touch_to_led[i] is the physical LED index for pad i (LED 0 = bottom
    // left, LED 23 = top right, 8 LEDs per row, rows bottom to top);
    // reuse it here so the grid matches the NeoPixels' physical layout.
    int led = touch_to_led[i];
    int col = led % 8;
    int row = 2 - (led / 8);
    int x = disp_col_x0 + col * disp_col_w;
    int y = grid_y0 + row * grid_row_h;
    if (touched & (1UL << i)) {
      disp.fillRect(x, y, square_w, square_h, SH110X_WHITE);
    } else {
      disp.drawRect(x, y, square_w, square_h, SH110X_WHITE);
    }
  }

  disp.display();
}

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 5000) { delay(10); }
  Serial.println("synthiota hwtest1");

  leds.begin();
  leds.setBrightness(40);
  leds.fill(leds.Color(255, 0, 255));
  leds.show();

  for (int i = 0; i < 3; i++) {
    pinMode(pot_sel_pins[i], OUTPUT);
    digitalWrite(pot_sel_pins[i], LOW);
  }

  encoderButton.attach(encoderSW_pin, INPUT_PULLUP);
  encoderButton.setPressedState(LOW);

  Wire1.setSDA(i2c_sda_pin);
  Wire1.setSCL(i2c_scl_pin);
  Wire1.begin();
  Wire1.setClock(400000);

  Serial.print("i2c1 scan:");
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire1.beginTransmission(addr);
    if (Wire1.endTransmission() == 0) {
      Serial.printf(" 0x%02X", addr);
    }
  }
  Serial.println();

  for (int i = 0; i < 2; i++) {
    if (!mpr121s[i].begin(mpr121_addrs[i], &Wire1)) {
      Serial.printf("MPR121 #%d (0x%02X) not found!\n", i, mpr121_addrs[i]);
    }
    mpr121s[i].setAutoconfig(true);
  }

  SPI1.setSCK(disp_sclk_pin);
  SPI1.setTX(disp_mosi_pin);
  disp.begin(0x3C, true);
  disp.clearDisplay();
  disp.display();

  leds.clear();
  leds.show();

  update_pots();
}

uint32_t last_status_time;

void loop() {
  encoder.tick();
  encoderButton.update();
  update_pots();
  uint32_t touched = update_touch();

  update_touch_leds(touched);
  updateDisplay(touched, encoder.getPosition(), encoderButton.isPressed());

  if (encoderButton.pressed()) {
    Serial.println("        encoder PRESS");
  }
  if (encoderButton.released()) {
    Serial.println("        encoder RELEASE");
  }

  uint32_t now = millis();
  if (now - last_status_time > 100) {
    last_status_time = now;
    Serial.printf("touch:%06lX pots:", touched);
    for (int i = 0; i < num_pots; i++) {
      Serial.printf(" %4d", pot_vals[i]);
    }
    Serial.printf(" enc:%ld\n", encoder.getPosition());
  }
}
