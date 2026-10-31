// SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt
// SPDX-License-Identifier: MIT
//
// wavesynth.ino - wavetable synth for synthiota using Mozzi, a port of
//                 circuitpython/wavesynth. Work in progress: for now a
//                 mono wavetable synth (TRS + USB MIDI) plus a USB drive
//                 on CircuitPython's CIRCUITPY partition, holding
//                 /wavetables and /patches.
//
// The 8 pots edit the 8 params of the current page, the encoder turns
// pages (24 params over 3). The 16 step pads play the scale up from the
// bottom left, up/down change octave. The right slider sets wpos, the
// left one the filter cutoff. Program change picks the table, CC1 wpos.
// Serial: 'w'/'W' table, ','/'.' wpos, 'p'/'P' picks a param, '['/']'
// changes it, '?' lists them.
//
// core0: USB (MIDI, MSC), UART MIDI, files. core1: Mozzi audio.
// Audio drops out while the host writes the drive: every flash write
// idles core1, so the output is faded to silence for each burst of host
// writes. The drive is the FlashDisk library (../libraries/FlashDisk).
//
// Needs the "Adafruit TinyUSB" USB Stack and a no-FS Flash Size option
// (see sketch.yaml / arduino/README.md).

#include "MozziConfigValues.h"
#define MOZZI_AUDIO_MODE MOZZI_OUTPUT_I2S_DAC
#define MOZZI_AUDIO_CHANNELS MOZZI_STEREO  // mono only drives the left channel
#define MOZZI_CONTROL_RATE 512  // also how often core1 drains note_queue
// its ADC setup turns GP26-29 analog, and GP27/28 are the encoder
#define MOZZI_ANALOG_READ MOZZI_ANALOG_READ_NONE

#include <Mozzi.h>

#include <FlashDisk.h>
#include <FlashBackendRP2.h>
#include <Fat12Format.h>
#include <Adafruit_TinyUSB.h>
#include <FlashDiskMSC.h>
#include <MIDI.h>
#include "wavetable.h"
#include "synth_engine.h"
#include "harmony.h"
#include "hw.h"
#include "paramset.h"
#include "ui.h"

#define uart_rx_pin  17
#define uart_tx_pin  16

#define DISK_LABEL "SYNTHIOTA"

#define SCAN_MS   2   // pads and pots
#define UI_MS     50  // params, LEDs, screen
#define VELOCITY  100
#define KEY_ROOT  48  // scale degree 0 at key C, no octave shift
const int8_t OCT_STEPS[] = { -24, -12, 0, 12, 24 };
#define OCT_MID 2
#define ENC_DIR (-1)  // this encoder counts down going clockwise

// TODO: temp switch while chasing flash corruption; 0 runs Mozzi on core0
#ifndef AUDIO_ON_CORE1
#define AUDIO_ON_CORE1 1
#endif

Params params;  // core0 writes, core1 reads
float wsel = 0, scale_sel = 0, key = 0;  // params beyond the engine's
int octave = OCT_MID;
volatile bool audio_mute = false;
volatile uint32_t ctl_ticks = 0;  // TODO: temp, core1 heartbeat for 'a'
// > the 256-sample fade plus Mozzi's 256-sample output buffer (~16ms at
// 32768Hz), so the DMA holds only silence when the first erase stalls it
#define MUTE_DRAIN_MS 30
Engine engine;  // core1 only

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
  wsel_param().hi = max(num_wave_files - 1, 0);
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
  bool ok = wave_select(fatfs, idx);
  wsel = max(wave_sel, 0);
  if (!ok) {
    Serial.printf("load failed: %s%s\n", wave_files[idx],
                  pending_table ? " (core1 hasn't taken the last one)" : "");
    return;
  }
  Serial.printf("loaded %d: %s, %d waves, %lu us\n", idx, wave_files[idx],
                pending_waves, (unsigned long)(micros() - t));
}

// a stalled I2S DMA replays its last buffers: make them silent first
void host_write_begin() {
  audio_mute = true;
  busy_wait_ms(MUTE_DRAIN_MS);
}

void midiProgramChange(byte channel, byte program) {
  load_wave(program);
}

// one wave per step; rounds to the nearest wave so steps land on waves
void nudge_wpos(int dir) {
  int span = wave_sel_waves > 1 ? wave_sel_waves - 1 : 1;
  int w = constrain((int)lroundf(params.wpos * span) + dir, 0, span);
  params.wpos = (float)w / span;
  Serial.printf("wpos %d / %d\n", w, span);
}

const char *const FILTER_NAMES[] = {"LPF", "HPF", "BPF", "NOTCH"};

// the ends, where the DOS-8 names differ: BRAIDS01..04, PLAITS01..03
const char *wave_label(int i) {
  static char buf[6];
  if (i < 0 || i >= num_wave_files) return "-";
  const char *n = wave_files[i];
  int len = strlen(n) - 4;  // no ".WAV"
  if (len <= 5) snprintf(buf, sizeof(buf), "%.*s", len, n);
  else snprintf(buf, sizeof(buf), "%.2s%.3s", n, n + len - 3);
  return buf;
}
const char *filter_label(int i) { return FILTER_NAMES[constrain(i, 0, 3)]; }
const char *scale_label(int i) { return SCALES[constrain(i, 0, NUM_SCALES - 1)].label; }
const char *key_label(int i) { return NOTE_NAMES[constrain(i, 0, 11)]; }
const char *wshp_label(int i) { return i ? "saw" : "tri"; }
const char *w1x_label(int i) { return i ? "1x" : "rpt"; }

// circuitpython/wavesynth's PARAMS, in page order; wpos and wlfo are
// 0..1 across the table, not in waves
Param param_list[] = {
  // WAVE
  {"freq",  &params.freq,  60, 8000, 100,   "%.0f"},
  {"reso",  &params.reso,  0.6, 6, 0.2,     "%.2f"},
  {"wpos",  &params.wpos,  0, 1, 0.05,      "%.2f"},
  {"wsel",  &wsel,         0, 0, 1,         nullptr, wave_label},
  {"wlfo",  &params.wlfo,  0, 1, 0.05,      "%.2f"},
  {"wrate", &params.wrate, 0, 5, 0.1,       "%.1f"},
  {"atk",   &params.atk,   0, 3, 0.05,      "%.2f"},
  {"rel",   &params.rel,   0, 3, 0.1,       "%.2f"},
  // ENV/FILT
  {"fatk",  &params.fatk,  0.01, 3, 0.05,   "%.2f"},
  {"frel",  &params.frel,  0.01, 3, 0.1,    "%.2f"},
  {"famt",  &params.famt,  -4000, 6000, 250, "%.0f"},
  {"ftype", &params.ftype, 0, 3, 1,         nullptr, filter_label},
  {"lamt",  &params.lamt,  0, 4000, 200,    "%.0f"},
  {"lrate", &params.lrate, 0, 8, 0.25,      "%.1f"},
  {"vdep",  &params.vdep,  0, 0.05, 0.002,  "%.3f"},
  {"vol",   &params.vol,   0.1, 1, 0.05,    "%.2f"},
  // KEY/MOD
  {"scale", &scale_sel,    0, NUM_SCALES - 1, 1, nullptr, scale_label},
  {"key",   &key,          0, 11, 1,        nullptr, key_label},
  {"wshp",  &params.wshp,  0, 1, 1,         nullptr, wshp_label},
  {"w1x",   &params.w1x,   0, 1, 1,         nullptr, w1x_label},
  {"wvel",  &params.wvel,  0, 1, 0.1,       "%.2f"},
  {"vrate", &params.vrate, 0.1, 12, 0.5,    "%.1f"},
  {"pamt",  &params.pamt,  -0.5, 0.5, 0.05, "%+.2f"},
  {"ptime", &params.ptime, 0.005, 1, 0.02,  "%.2f"},
};
const int num_params = sizeof(param_list) / sizeof(param_list[0]);
const char *const PAGE_NAMES[] = { "WAVE", "ENV/FILT", "KEY/MOD" };
static_assert(sizeof(param_list) / sizeof(Param) == 3 * 8, "3 pages of 8");

// raised well above the ~0.004 rest jitter of a muxed synthiota pot
ParamSet<8> param_set(param_list, num_params, 0.012);
PotPageUI ui(param_set, PAGE_NAMES);
int param_sel = 0;

Param &wsel_param() { return param_list[3]; }

void print_param(int i) {
  char buf[16];
  param_text(param_list[i], buf, sizeof(buf));
  Serial.printf("%-5s %s\n", param_list[i].name, buf);
}

void nudge_param(int dir) {
  Param &p = param_list[param_sel];
  *p.v = constrain(*p.v + dir * p.step, p.lo, p.hi);
  print_param(param_sel);
}

void midiControlChange(byte channel, byte cc, byte val) {
  if (cc == 1) params.wpos = val / 127.0f;
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

void note_on(uint8_t n) {
  note_queue.push(note_event(true, n, VELOCITY));
  MIDIusb.sendNoteOn(n, VELOCITY, 1);
  MIDIuart.sendNoteOn(n, VELOCITY, 1);
}
void note_off(uint8_t n) {
  note_queue.push(note_event(false, n, 0));
  MIDIusb.sendNoteOff(n, 0, 1);
  MIDIuart.sendNoteOff(n, 0, 1);
}

// TODO: the top row plays diatonic chords on the last bottom pad, once
// there's polyphony; until then it carries on up the scale
int pad_note(int step) {
  int root = KEY_ROOT + lroundf(key) + OCT_STEPS[octave];
  return scale_degree(SCALES[lroundf(scale_sel)], root, step);
}

int16_t held[NUM_STEPS];  // the note each step pad started, -1 if none
int pair = 0;  // which pot pair the screen shows; the last pot turned wins

// true if a step pad changed
bool scan_controls() {
  static uint32_t last = 0;
  pots.update();
  touch.update();
  uint32_t t = touch.touched, down = t & ~last;
  bool changed = false;
  for (int i = 0; i < NUM_STEPS; i++) {
    uint32_t bit = 1UL << STEP_PADS[i];
    if (!((t ^ last) & bit)) continue;
    changed = true;
    if (t & bit) {
      int n = pad_note(i);
      if (n < 0 || n > 127) continue;
      held[i] = n;
      note_on(n);
    } else if (held[i] >= 0) {
      note_off(held[i]);
      held[i] = -1;
    }
  }
  if (down & (1UL << PAD_UP)) octave = min(octave + 1, (int)sizeof(OCT_STEPS) - 1);
  if (down & (1UL << PAD_DOWN)) octave = max(octave - 1, 0);
  // relic's slider position can drift off its baseline, so only while touched
  if (touch.rslider.touched(t)) {
    float r = touch.rslider.value();
    if (r >= 0) params.wpos = r;
  }
  if (touch.lslider.touched(t)) {
    float l = touch.lslider.value();
    if (l >= 0) params.freq = 200 + l * 7000;
  }
  last = t;

  static long enc_last = 0;
  long pos = encoder.getPosition();
  if (pos != enc_last) {
    int n = param_set.pages();
    param_set.setPage(((param_set.page() + ENC_DIR * (pos - enc_last)) % n + n) % n);
    pair = 0;
    enc_last = pos;
  }
  return changed;
}

void update_ui(bool pads_changed) {
  static bool refresh = false;
  uint32_t turned = param_set.update(pots.val);
  for (int k = 0; k < 8; k++) {
    if (turned & (1UL << k)) pair = k / 2;
  }
  if (wave_sel >= 0 && lroundf(wsel) != wave_sel) load_wave(lroundf(wsel));

  char hdr[8];
  int o = octave - OCT_MID;
  snprintf(hdr, sizeof(hdr), o ? "%s%+d" : "%s", NOTE_NAMES[lroundf(key)], o);
  ui.showPair(pair);
  refresh |= ui.update(hdr);
  if (refresh && !pads_changed) {  // a push takes ms; not when a note starts
    disp.display();
    refresh = false;
  }

  static uint32_t shown[NUM_LEDS];
  uint32_t c[NUM_LEDS] = {};
  for (int i = 0; i < NUM_STEPS; i++) c[i] = held[i] >= 0 ? 0x00AAFF : 0;
  // the param, not the pot, so it means something after a page turn
  for (int k = 0; k < 8; k++) {
    uint8_t lvl = 6 + 249 * param_set.knob(k).norm();
    c[LED_POTS + k] = leds.Color(0, lvl, lvl);
  }
  if (memcmp(c, shown, sizeof(c))) {
    memcpy(shown, c, sizeof(c));
    for (int i = 0; i < NUM_LEDS; i++) leds.setPixelColor(i, c[i]);
    leds.show();
  }
}

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < NUM_STEPS; i++) held[i] = -1;

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
    drive.onWriteBegin(host_write_begin);
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

  hw_setup();

  if (fits) {
    wave_rescan();
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
    case 'p': param_sel = (param_sel + 1) % num_params; print_param(param_sel); break;
    case 'P': param_sel = (param_sel + num_params - 1) % num_params; print_param(param_sel); break;
    case ']': nudge_param(+1); break;
    case '[': nudge_param(-1); break;
    case '?': for (int i = 0; i < num_params; i++) print_param(i); break;
    case 'a':  // TODO: temp audio/DMA debug
      Serial.printf("ctl_ticks %lu mute %d\n", (unsigned long)ctl_ticks, audio_mute);
      for (uint ch = 0; ch < NUM_DMA_CHANNELS; ch++) {
        uint32_t c = dma_hw->ch[ch].al1_ctrl;
        if (!(c & DMA_CH0_CTRL_TRIG_EN_BITS) && !dma_hw->ch[ch].transfer_count) continue;
        Serial.printf("dma%u en %d busy %d count %lu read %08lx write %08lx\n", ch,
                      !!(c & DMA_CH0_CTRL_TRIG_EN_BITS), !!(c & DMA_CH0_CTRL_TRIG_BUSY_BITS),
                      (unsigned long)dma_hw->ch[ch].transfer_count,
                      (unsigned long)dma_hw->ch[ch].read_addr,
                      (unsigned long)dma_hw->ch[ch].write_addr);
      }
      break;
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

  static uint32_t last_scan = 0, last_ui = 0;
  static bool pads_changed = false;
  uint32_t now = millis();
  if (now - last_scan >= SCAN_MS) {
    last_scan = now;
    pads_changed |= scan_controls();
  }
  if (now - last_ui >= UI_MS) {
    last_ui = now;
    update_ui(pads_changed);
    pads_changed = false;
  }
  if (audio_mute && !drive.hostActive()) audio_mute = false;
  if (wave_swaps != last_swaps) {
    last_swaps = wave_swaps;
    Serial.printf("core1 swapped in table (%lu swaps)\n", (unsigned long)last_swaps);
  }
}

void audio_setup() {
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
  ctl_ticks++;
  wave_adopt();
  uint32_t ev;
  while (note_queue.pop(ev)) {
    uint8_t note = (ev >> 8) & 0xFF;
    if (ev >> 16) {
      engine.noteOn(note, ev & 0xFF, params);
    } else {
      engine.noteOff(note);
    }
  }
  engine.control(params, wt_table, wt_num_waves);
}

AudioOutput updateAudio() {
  static int32_t fade = 256;  // ramps, so muting doesn't click
  if (audio_mute) {
    if (fade > 0) fade--;
  } else if (fade < 256) {
    fade++;
  }
  int32_t v = engine.next() * fade >> 8;
  return StereoOutput::fromNBit(16, v, v).clip();
}
