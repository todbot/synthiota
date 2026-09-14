# synthiota Arduino sketches

Arduino sketches for the synthiota1 board (RP2040/RP2350), 
built with the [earlephilhower rp2040 core][rp2040-core] and `arduino-cli`.

[rp2040-core]: https://github.com/earlephilhower/arduino-pico

## Sketches

- **hwtest/hwtest1** -- board basic test: I2C scan, dual MPR121
  touch with NeoPixel feedback, 8-pot mux, rotary encoder + switch,
  and a SH1106 SPI OLED status page. See
  `circuitpython/hwtest/synth_setup_synthiota.py` for the pin map this
  is based on.
  
- **hwtest/hwtest2** -- simple monophonic MIDI synth using
  [M16](https://github.com/algomusic/M16), driving the PCM5102 I2S DAC. <br>
  (saw oscillator, fixed lowpass, AR envelope, TRS + USB MIDI)
  
- **hwtest/hwtest3** -- simple monophonic MIDI synth using 
  [Mozzi](https://sensorium.github.io/Mozzi/), similar to hwtest2. <br>
   (saw oscillator, fixed lowpass, AR envelope, TRS + USB MIDI)

## sketch.yaml profiles

Each sketch has a [`sketch.yaml`][sketch-yaml] pinning the exact
platform and library versions it was built against, as `pico` and
`pico2` profiles (`default_profile: pico2`). Profile builds are
self-contained -- `arduino-cli` downloads the pinned platform/library
versions into an isolated store on first use, independent of whatever
is installed globally -- so no separate `core install`/`lib install`
step is needed for these sketches.

Note the Arduino IDE does not read `sketch.yaml`; it only applies to
`arduino-cli` builds. Building from the IDE instead, just open the
`.ino` and pick the board from Tools > Board as usual (see "USB MIDI"
below for hwtest2's extra board option).

[sketch-yaml]: https://arduino.github.io/arduino-cli/latest/sketch-project-file/


## Board FQBNs

| Board               | FQBN |
|---------------------|------|
| Raspberry Pi Pico   | `rp2040:rp2040:rpipico:usbstack=tinyusb`  |
| Raspberry Pi Pico 2 | `rp2040:rp2040:rpipico2:usbstack=tinyusb` |


## USB Serial and USB MIDI 

Sketches use USB via `Adafruit_TinyUSB` and need the board's
USB Stack set to **Adafruit TinyUSB** instead of the default Pico SDK
stack. If you're using `arduino-cli`, the sketch's `sketch.yaml` profiles
already bake this in, so use  `--profile pico2` or `--profile pico`. 


## Build and upload

From inside a sketch directory (e.g. `arduino/hwtest/hwtest1`):

```sh
# Pico
arduino-cli compile --profile pico .
arduino-cli upload -p /dev/ttyACM0 --profile pico .

# Pico 2 (the default profile)
arduino-cli compile --profile pico2 .
arduino-cli upload -p /dev/ttyACM0 --profile pico2 .

# serial monitor
arduino-cli monitor -p /dev/ttyACM0
```

Adjust `/dev/ttyACM0` to match the board's actual serial port (find it
with `arduino-cli board list`).

To (re)generate a sketch's `sketch.yaml` profiles rather than
hand-tracking library versions, use `arduino-cli`'s `--dump-profile`:

```sh
arduino-cli compile --fqbn rp2040:rp2040:rpipico2 --dump-profile .
```

