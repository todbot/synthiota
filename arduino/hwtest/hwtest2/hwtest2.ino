// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// hwtest2.ino - simple monophonic MIDI synth for synthiota board using M16
//               (https://github.com/algomusic/M16), driving the
//               PCM5102 I2S DAC. Responds to both TRS UART MIDI and
//               USB MIDI.
//
// M16's RP2040 I2S backend (arduino-pico's I2S library) hardwires
// WS/LRCLK to BCLK+1; synthiota's wiring (BCLK=20, LRCLK=21) already
// satisfies that, so seti2sPins() just needs BCLK/DOUT.
//
// Needs the "Adafruit TinyUSB" USB Stack board option for USB MIDI
// (see sketch.yaml / arduino/README.md).

#include "M16.h"
#include "Osc.h"
#include "Env.h"
#include "SVF.h"
#include "MIDI16.h"

#include <Adafruit_TinyUSB.h>
#include <MIDI.h>

#define i2s_bclk_pin  20
#define i2s_lclk_pin  21
#define i2s_data_pin  22
#define uart_rx_pin   17
#define uart_tx_pin   16

WaveTable sawtoothWave;
Osc osc;
Env env;
SVF filt;

MIDI16 midiUart(uart_rx_pin, uart_tx_pin);

Adafruit_USBD_MIDI usb_midi;
MIDI_CREATE_INSTANCE(Adafruit_USBD_MIDI, usb_midi, MIDIusb);

int currentNote = -1;

void handleNoteOn(byte pitch, byte velocity) {
  osc.setPitch(pitch);
  env.start();
  currentNote = pitch;
  Serial.printf("note on  %3d vel %3d\n", pitch, velocity);
}

void handleNoteOff(byte pitch) {
  if (pitch == currentNote) {
    env.startRelease();
    currentNote = -1;
    Serial.printf("note off %3d\n", pitch);
  }
}

void usbNoteOn(byte channel, byte pitch, byte velocity) {
  handleNoteOn(pitch, velocity);
}
void usbNoteOff(byte channel, byte pitch, byte velocity) {
  handleNoteOff(pitch);
}

void setup() {
  Serial.begin(115200);
  Serial.println("synthiota hwtest2: M16 MIDI synth");

  sawtoothWave.sawGen();
  osc.setTable(sawtoothWave);
  env.setAttack(5);
  env.setRelease(300);
  filt.setFreq(3000);
  filt.setRes(0);

  seti2sPins(i2s_bclk_pin, i2s_lclk_pin, i2s_data_pin, -1);
  setIsDualCore(false);  // single voice, no partitioning needed
  audioStart();

  MIDIusb.begin(MIDI_CHANNEL_OMNI);
  MIDIusb.setHandleNoteOn(usbNoteOn);
  MIDIusb.setHandleNoteOff(usbNoteOff);
  while (!TinyUSBDevice.mounted()) delay(1);
}

void loop() {
#if IS_RP2040()
  audioLoop();
#endif

  MIDIusb.read();

  uint8_t status;
  while ((status = midiUart.read()) != 0) {
    if (status == MIDI16::noteOn) {
      handleNoteOn(midiUart.getData1(), midiUart.getData2());
    } else if (status == MIDI16::noteOff) {
      handleNoteOff(midiUart.getData1());
    }
  }
}

void audioUpdate() {
  int32_t sample = (filt.nextLPF(osc.next()) * env.getValue()) >> 16;
  audioBlockWrite(sample, sample);
}
