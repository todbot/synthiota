// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// hwtest3.ino - simple monophonic MIDI synth for synthiota board using
//               Mozzi (https://sensorium.github.io/Mozzi/), driving the
//               PCM5102 I2S DAC. Responds to both TRS UART MIDI and
//               USB MIDI. Same shape as hwtest2.ino, but Mozzi instead
//               of M16.
//
// Mozzi's RP2040 I2S output already defaults to BCK=20, WS=21 (fixed at
// BCK+1), DATA=22 -- exactly synthiota's wiring -- so no pin config is
// needed here at all, unlike hwtest2's seti2sPins() call for M16.
//
// Needs the "Adafruit TinyUSB" USB Stack board option for USB MIDI
// (see sketch.yaml / arduino/README.md).

#include "MozziConfigValues.h"
#define MOZZI_AUDIO_MODE MOZZI_OUTPUT_I2S_DAC

#include <Mozzi.h>
#include <Oscil.h>
#include <ADSR.h>
#include <ResonantFilter.h>
#include <tables/saw2048_int8.h>
#include <mozzi_midi.h>

#include <Adafruit_TinyUSB.h>
#include <MIDI.h>

#define uart_rx_pin  17
#define uart_tx_pin  16

Oscil<SAW2048_NUM_CELLS, MOZZI_AUDIO_RATE> osc(SAW2048_DATA);
ADSR<MOZZI_AUDIO_RATE, MOZZI_AUDIO_RATE> env;
LowPassFilter filt;

MIDI_CREATE_INSTANCE(HardwareSerial, Serial2, MIDIuart);

Adafruit_USBD_MIDI usb_midi;
MIDI_CREATE_INSTANCE(Adafruit_USBD_MIDI, usb_midi, MIDIusb);

int currentNote = -1;

void handleNoteOn(byte pitch, byte velocity) {
  osc.setFreq(mtof(pitch));
  env.noteOn();
  currentNote = pitch;
  Serial.printf("note on  %3d vel %3d\n", pitch, velocity);
}

void handleNoteOff(byte pitch) {
  if (pitch == currentNote) {
    env.noteOff();
    currentNote = -1;
    Serial.printf("note off %3d\n", pitch);
  }
}

void uartNoteOn(byte channel, byte pitch, byte velocity) {
  handleNoteOn(pitch, velocity);
}
void uartNoteOff(byte channel, byte pitch, byte velocity) {
  handleNoteOff(pitch);
}
void usbNoteOn(byte channel, byte pitch, byte velocity) {
  handleNoteOn(pitch, velocity);
}
void usbNoteOff(byte channel, byte pitch, byte velocity) {
  handleNoteOff(pitch);
}

void setup() {
  Serial.begin(115200);
  Serial.println("synthiota hwtest3: Mozzi MIDI synth");

  env.setADLevels(255, 255);       // no decay stage -- attack straight to full level
  env.setTimes(5, 1, 60000, 300);  // attack, decay, sustain hold, release (ms)
  filt.setCutoffFreqAndResonance(120, 0);

  startMozzi();

  Serial2.setRX(uart_rx_pin);
  Serial2.setTX(uart_tx_pin);
  MIDIuart.begin(MIDI_CHANNEL_OMNI);
  MIDIuart.setHandleNoteOn(uartNoteOn);
  MIDIuart.setHandleNoteOff(uartNoteOff);

  MIDIusb.begin(MIDI_CHANNEL_OMNI);
  MIDIusb.setHandleNoteOn(usbNoteOn);
  MIDIusb.setHandleNoteOff(usbNoteOff);
  while (!TinyUSBDevice.mounted()) delay(1);
}

void loop() {
  audioHook();
  MIDIuart.read();
  MIDIusb.read();
}

void updateControl() {
}

AudioOutput updateAudio() {
  env.update();
  int8_t osc_val = osc.next();
  int8_t filt_val = filt.next(osc_val);
  return MonoOutput::from16Bit((int)filt_val * env.next());
}
