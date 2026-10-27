// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// wavesynth.ino - wavetable synth for synthiota using Mozzi, a port of
//                 circuitpython/wavesynth. Work in progress: for now a
//                 hwtest3-style mono saw synth (TRS + USB MIDI) plus a
//                 CircuitPython-style USB drive "SYNTHIOTA" on the
//                 internal flash, holding /wavetables and /patches.
//
// Needs the "Adafruit TinyUSB" USB Stack and a Flash Size option with an
// FS partition (see sketch.yaml / arduino/README.md).

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
#include <SdFat_Adafruit_Fork.h>
#include <Adafruit_SPIFlash.h>
#include "fat12_format.h"

#define uart_rx_pin  17
#define uart_tx_pin  16

#define DISK_LABEL "SYNTHIOTA"

Oscil<SAW2048_NUM_CELLS, MOZZI_AUDIO_RATE> osc(SAW2048_DATA);
ADSR<MOZZI_AUDIO_RATE, MOZZI_AUDIO_RATE> env;
LowPassFilter filt;

MIDI_CREATE_INSTANCE(HardwareSerial, Serial1, MIDIuart);

Adafruit_USBD_MIDI usb_midi;
MIDI_CREATE_INSTANCE(Adafruit_USBD_MIDI, usb_midi, MIDIusb);

// CircuitPython's partition, so CIRCUITPY mounts as-is. Needs a
// no-FS Flash Size option and a sketch under CPY_START_ADDR (1MB).
Adafruit_FlashTransport_RP2040 flashTransport(
    Adafruit_FlashTransport_RP2040::CPY_START_ADDR,
    Adafruit_FlashTransport_RP2040::CPY_SIZE);
Adafruit_SPIFlash flash(&flashTransport);
FatVolume fatfs;
Adafruit_USBD_MSC usb_msc;
volatile bool fs_changed = true;

int currentNote = -1;

int32_t msc_read_cb(uint32_t lba, void *buffer, uint32_t bufsize) {
  return flash.readBlocks(lba, (uint8_t *)buffer, bufsize / 512) ? bufsize : -1;
}

int32_t msc_write_cb(uint32_t lba, uint8_t *buffer, uint32_t bufsize) {
  return flash.writeBlocks(lba, buffer, bufsize / 512) ? bufsize : -1;
}

void msc_flush_cb() {
  flash.syncBlocks();
  fatfs.cacheClear();  // host changed the volume under us
  fs_changed = true;
}

void touch_file(const char *path) {
  if (fatfs.exists(path)) return;
  File32 f = fatfs.open(path, O_WRONLY | O_CREAT);
  f.close();
}

extern uint8_t __flash_binary_end;

bool sketch_fits() {
  return (uint32_t)&__flash_binary_end <=
         XIP_BASE + Adafruit_FlashTransport_RP2040::CPY_START_ADDR;
}

bool flash_blank() {
  uint8_t buf[512];
  if (!flash.readBlocks(0, buf, 1)) return false;
  for (uint8_t b : buf) if (b != 0xFF) return false;
  return true;
}

// Only formats never-written flash: an unmountable volume might still
// be someone's CIRCUITPY. Keeps macOS from littering it like CPy does.
bool fs_setup() {
  if (!fatfs.begin(&flash)) {
    if (!flash_blank()) {
      Serial.println("drive not mountable, leaving it alone");
      return false;
    }
    Serial.println("blank flash, formatting " DISK_LABEL);
    if (!fat12_format(flash, DISK_LABEL) || !fatfs.begin(&flash)) {
      Serial.println("format failed");
      return false;
    }
  }
  for (const char *d : { "/wavetables", "/patches", "/.fseventsd" }) {
    if (!fatfs.exists(d)) fatfs.mkdir(d);
  }
  touch_file("/.fseventsd/no_log");
  touch_file("/.metadata_never_index");
  touch_file("/.Trashes");
  flash.syncBlocks();
  return true;
}

void list_dir(const char *path) {
  File32 dir = fatfs.open(path);
  if (!dir) {
    Serial.printf("can't open %s\n", path);
    return;
  }
  Serial.printf("%s:\n", path);
  File32 f;
  while (f.openNext(&dir, O_RDONLY)) {
    char name[64];
    f.getName(name, sizeof(name));
    if (name[0] != '.') {
      Serial.printf("  %7lu %s%s\n", (unsigned long)f.fileSize(), name,
                    f.isDir() ? "/" : "");
    }
    f.close();
  }
  dir.close();
}

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

void midiNoteOn(byte channel, byte pitch, byte velocity) {
  handleNoteOn(pitch, velocity);
}
void midiNoteOff(byte channel, byte pitch, byte velocity) {
  handleNoteOff(pitch);
}

void setup() {
  Serial.begin(115200);

  // before MSC is up, so the host never sees a half-made volume
  bool fits = sketch_fits();
  if (fits) {
    flash.begin();
    fs_setup();
    usb_msc.setID("synthiota", "wavesynth", "1.0");
    usb_msc.setReadWriteCallback(msc_read_cb, msc_write_cb, msc_flush_cb);
    usb_msc.setCapacity(flash.size() / 512, 512);
    usb_msc.setUnitReady(true);
    usb_msc.begin();
  }

  MIDIusb.begin(MIDI_CHANNEL_OMNI);
  MIDIusb.turnThruOff();
  MIDIusb.setHandleNoteOn(midiNoteOn);
  MIDIusb.setHandleNoteOff(midiNoteOff);

  // USB came up before setup(); re-enumerate so the host sees MSC + MIDI
  if (TinyUSBDevice.mounted()) {
    TinyUSBDevice.detach();
    delay(10);
    TinyUSBDevice.attach();
  }

  Serial1.setRX(uart_rx_pin);
  Serial1.setTX(uart_tx_pin);
  MIDIuart.begin(MIDI_CHANNEL_OMNI);
  MIDIuart.turnThruOff();
  MIDIuart.setHandleNoteOn(midiNoteOn);
  MIDIuart.setHandleNoteOff(midiNoteOff);

  env.setADLevels(255, 255);       // no decay stage -- attack straight to full level
  env.setTimes(5, 1, 60000, 300);  // attack, decay, sustain hold, release (ms)
  filt.setCutoffFreqAndResonance(120, 0);

  startMozzi();
  if (!fits) {
    Serial.println("sketch overlaps CIRCUITPY, drive disabled");
    fs_changed = false;
  }
}

void loop() {
  audioHook();
  MIDIuart.read();
  MIDIusb.read();

  if (fs_changed) {
    fs_changed = false;
    Serial.printf("synthiota wavesynth: drive %lu KB\n",
                  (unsigned long)(flash.size() / 1024));
    list_dir("/");
    list_dir("/wavetables");
  }
}

void updateControl() {
}

AudioOutput updateAudio() {
  env.update();
  int8_t osc_val = osc.next();
  int8_t filt_val = filt.next(osc_val);
  return MonoOutput::from16Bit((int)filt_val * env.next());
}
