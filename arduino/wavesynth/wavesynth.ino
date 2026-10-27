// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// wavesynth.ino - wavetable synth for synthiota using Mozzi, a port of
//                 circuitpython/wavesynth. Work in progress: for now a
//                 mono wavetable synth (TRS + USB MIDI) plus a USB drive
//                 on CircuitPython's CIRCUITPY partition, holding
//                 /wavetables and /patches. Program change or serial
//                 'w'/'W' picks the table, CC1 or serial ','/'.' moves
//                 through it.
//
// core0: USB (MIDI, MSC), UART MIDI, files. core1: Mozzi audio.
// Audio drops out while the host writes the drive: every flash write
// idles core1. The drive is the FlashDisk library (../libraries/FlashDisk).
//
// Needs the "Adafruit TinyUSB" USB Stack and a no-FS Flash Size option
// (see sketch.yaml / arduino/README.md).

#include "MozziConfigValues.h"
#define MOZZI_AUDIO_MODE MOZZI_OUTPUT_I2S_DAC
#define MOZZI_AUDIO_CHANNELS MOZZI_STEREO  // mono only drives the left channel
#define MOZZI_CONTROL_RATE 512  // also how often core1 drains note_queue

#include <Mozzi.h>
#include <ADSR.h>
#include <mozzi_midi.h>

#include <FlashDisk.h>
#include <FlashBackendRP2.h>
#include <Fat12Format.h>
#include <Adafruit_TinyUSB.h>
#include <FlashDiskMSC.h>
#include <MIDI.h>
#include "wavetable.h"
#include "wave_osc.h"

#define uart_rx_pin  17
#define uart_tx_pin  16

#define DISK_LABEL "SYNTHIOTA"

// TODO: temp switch while chasing flash corruption; 0 runs Mozzi on core0
#ifndef AUDIO_ON_CORE1
#define AUDIO_ON_CORE1 1
#endif

WaveOsc osc;
ADSR<MOZZI_AUDIO_RATE, MOZZI_AUDIO_RATE> env;
// 0..65535 across whatever table core1 is playing, so it survives a swap
// to a table with a different wave count
volatile uint16_t wpos_norm = 0;

MIDI_CREATE_INSTANCE(HardwareSerial, Serial1, MIDIuart);

Adafruit_USBD_MIDI usb_midi;
MIDI_CREATE_INSTANCE(Adafruit_USBD_MIDI, usb_midi, MIDIusb);

// CircuitPython's CIRCUITPY drive, so its files survive a switch to this
// sketch and back. Needs a no-FS Flash Size option.
FlashBackendRP2 flash_backend = FlashBackendRP2::circuitpy();
FlashDisk disk(flash_backend);
FatVolume fatfs;
FlashDiskMSC drive;

// core0 -> core1 note events. One writer, one reader, so no lock.
struct NoteQueue {
  static const uint8_t N = 32;
  volatile uint32_t buf[N];
  volatile uint8_t head = 0, tail = 0;
  bool push(uint32_t v) {
    uint8_t n = (head + 1) % N;
    if (n == tail) return false;
    buf[head] = v;
    __dmb();
    head = n;
    return true;
  }
  bool pop(uint32_t &v) {
    if (tail == head) return false;
    v = buf[tail];
    __dmb();
    tail = (tail + 1) % N;
    return true;
  }
};
NoteQueue note_queue;

uint32_t note_event(bool on, uint8_t note, uint8_t vel) {
  return (on << 16) | (note << 8) | vel;
}

volatile bool core0_ready = false;
int current_note = -1;  // core1 only

void touch_file(const char *path) {
  if (fatfs.exists(path)) return;
  File32 f = fatfs.open(path, O_WRONLY | O_CREAT);
  f.close();
}

// Only formats never-written flash: an unmountable volume might still
// be someone's CIRCUITPY. Keeps macOS from littering it like CPy does.
bool fs_setup() {
  if (!fatfs.begin(&disk)) {
    if (!sectorErased(disk, 0)) {
      Serial.println("drive not mountable, leaving it alone");
      return false;
    }
    Serial.println("blank flash, formatting " DISK_LABEL);
    if (!fat12Format(disk, DISK_LABEL, micros()) || !fatfs.begin(&disk)) {
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
  disk.syncDevice();
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

// reloads even an unchanged name: the host may have overwritten the file
void wave_rescan() {
  char cur[WAVE_NAME_LEN] = "";
  if (wave_sel >= 0) strcpy(cur, wave_files[wave_sel]);
  wave_scan(fatfs);
  Serial.printf("%d wavetables\n", num_wave_files);
  int idx = cur[0] ? wave_find(cur) : -1;
  load_wave(idx < 0 ? 0 : idx);
}

void load_wave(int idx) {
  if (num_wave_files == 0) {
    Serial.println("no .WAV files in " WAVE_DIR);
    return;
  }
  idx = (idx + num_wave_files) % num_wave_files;
  uint32_t t = micros();
  if (!wave_select(fatfs, idx)) {
    Serial.printf("load failed: %s%s\n", wave_files[idx],
                  pending_table ? " (core1 hasn't taken the last one)" : "");
    return;
  }
  Serial.printf("loaded %d: %s, %d waves, %lu us\n", idx, wave_files[idx],
                pending_waves, (unsigned long)(micros() - t));
}

void midiProgramChange(byte channel, byte program) {
  load_wave(program);
}

// one wave per step; rounds to the nearest wave so steps land on waves
void nudge_wpos(int dir) {
  int span = wave_sel_waves > 1 ? wave_sel_waves - 1 : 1;
  int w = (wpos_norm * span + 32767) / 65535 + dir;
  w = w < 0 ? 0 : w > span ? span : w;
  wpos_norm = w * 65535 / span;
  Serial.printf("wpos %d / %d\n", w, span);
}

void midiControlChange(byte channel, byte cc, byte val) {
  if (cc == 1) wpos_norm = val * 65535 / 127;
}

void midiNoteOn(byte channel, byte pitch, byte velocity) {
  if (velocity == 0) {
    note_queue.push(note_event(false, pitch, 0));
    return;
  }
  note_queue.push(note_event(true, pitch, velocity));
  Serial.printf("note on  %3d vel %3d\n", pitch, velocity);
}
void midiNoteOff(byte channel, byte pitch, byte velocity) {
  note_queue.push(note_event(false, pitch, 0));
  Serial.printf("note off %3d\n", pitch);
}

void setup() {
  Serial.begin(115200);

  // before MSC is up, so the host never sees a half-made volume
  bool fits = flash_backend.sketchFits();
  if (fits) fs_setup();

  MIDIusb.begin(MIDI_CHANNEL_OMNI);
  MIDIusb.turnThruOff();
  MIDIusb.setHandleNoteOn(midiNoteOn);
  MIDIusb.setHandleNoteOff(midiNoteOff);
  MIDIusb.setHandleProgramChange(midiProgramChange);
  MIDIusb.setHandleControlChange(midiControlChange);

  // after MIDI: either re-enumerates so the host sees every interface
  if (fits) {
    drive.begin(disk, &fatfs, "synthiota", "wavesynth", "1.0");
  } else if (TinyUSBDevice.mounted()) {
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
  MIDIuart.setHandleProgramChange(midiProgramChange);
  MIDIuart.setHandleControlChange(midiControlChange);

  if (fits) {
    wave_scan(fatfs);
    load_wave(0);
  } else {
    Serial.println("sketch overlaps CIRCUITPY, drive disabled");
  }
  core0_ready = true;
#if !AUDIO_ON_CORE1
  audio_setup();
#endif
}

// TODO: temp drive debug, remove
void dump_sector(uint32_t lba) {
  uint8_t buf[512];
  bool ok = disk.readSector(lba, buf);
  Serial.printf("sector %lu %s:\n", (unsigned long)lba, ok ? "" : "READ FAIL");
  for (int i = 0; i < 512; i += 16) {
    if (i == 64) i = 432;  // skip to the MBR partition table
    Serial.printf("%03x:", i);
    for (int j = 0; j < 16; j++) Serial.printf(" %02x", buf[i + j]);
    Serial.println();
  }
}

void check_serial() {
  if (!Serial.available()) return;
  switch (Serial.read()) {
    case 'd':
      Serial.printf("disk sectors %lu, fatfs %d\n",
                    (unsigned long)disk.sectorCount(), fatfs.begin(&disk));
      dump_sector(0);
      dump_sector(1);
      break;
    case 'l':
      list_dir("/");
      list_dir(WAVE_DIR);
      break;
    case 'w': load_wave(wave_sel + 1); break;
    case 'W': load_wave(wave_sel - 1); break;
    case '.': nudge_wpos(+1); break;
    case ',': nudge_wpos(-1); break;
  }
}

void loop() {
  static uint32_t last_swaps = 0;
#if !AUDIO_ON_CORE1
  audioHook();
#endif
  check_serial();
  MIDIuart.read();
  MIDIusb.read();

  if (drive.changed()) wave_rescan();
  if (wave_swaps != last_swaps) {
    last_swaps = wave_swaps;
    Serial.printf("core1 swapped in table (%lu swaps)\n", (unsigned long)last_swaps);
  }
}

void audio_setup() {
  env.setADLevels(255, 255);       // no decay stage -- attack straight to full level
  env.setTimes(5, 1, 60000, 300);  // attack, decay, sustain hold, release (ms)
  startMozzi();
}

#if AUDIO_ON_CORE1
// wait out core0's setup: its flash writes would idle us mid-start
void setup1() {
  while (!core0_ready) delay(1);
  audio_setup();
}

void loop1() {
  audioHook();
}
#endif

void updateControl() {
  wave_adopt();
  osc.setTable(wt_table, wt_num_waves);
  uint32_t span = wt_num_waves > 1 ? wt_num_waves - 1 : 0;
  osc.setWavePos((uint32_t)wpos_norm * span);
  uint32_t ev;
  while (note_queue.pop(ev)) {
    bool on = ev >> 16;
    uint8_t note = (ev >> 8) & 0xFF;
    if (on) {
      osc.setFreq(mtof(note));
      env.noteOn();
      current_note = note;
    } else if (note == current_note) {
      env.noteOff();
      current_note = -1;
    }
  }
}

AudioOutput updateAudio() {
  env.update();
  int32_t v = (int32_t)osc.next() * env.next();
  return StereoOutput::fromNBit(24, v, v);
}
