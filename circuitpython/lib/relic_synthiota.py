# SPDX-FileCopyrightText: 2017 Scott Shawcroft, written for Adafruit Industries
# SPDX-FileCopyrightText: Copyright (c) 2026 Cooper Dalrymple (@relic-se)
# SPDX-FileCopyrightText: Copyright (c) 2026 Tod Kurt (@todbot)
#
# SPDX-License-Identifier: MIT
"""
`relic_synthiota`
================================================================================

Helper library for Synthiota


* Author(s): Cooper Dalrymple

Implementation Notes
--------------------

**Hardware:**

* 1 x `Synthiota PCB <https://github.com/todbot/synthiota/>`_
* 1 x `Raspberry Pi Pico 2 <https://www.adafruit.com/product/6006>`_
* 1 x `PCM5102 I2S Stereo DAC <https://amzn.to/4nX4xkD>`_
* 1 x `SH1106 128x64 1.3" SPI OLED <https://amzn.to/4nX4xkD>`_
* 2 x `PJ320A 3.5mm stereo jack <https://amzn.to/4i5F33d>`_
* 8 x `RK09K 10k vertical potentiometer <https://amzn.to/47XbwEk>`_
* 1 x `EC11 rotary encoder <https://amzn.to/4o1vSSW>`_

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://circuitpython.org/downloads
* todbot's TMIDI library: https://github.com/todbot/CircuitPython_TMIDI
* Adafruit's Debouncer library: https://github.com/adafruit/Adafruit_CircuitPython_Debouncer
* Adafruit's DisplayIO SH1106 library: https://github.com/adafruit/Adafruit_CircuitPython_DisplayIO_SH1106
* Adafruit's MPR121 library: https://github.com/adafruit/Adafruit_CircuitPython_MPR121
* Adafruit's NeoPixel library: https://github.com/adafruit/Adafruit_CircuitPython_NeoPixel
"""

import array
import sys
import time

import adafruit_debouncer
import adafruit_displayio_sh1106
import adafruit_mpr121
import analogio
import audiobusio
import audiomixer
import board
import busio
import digitalio
import displayio
import fourwire
import neopixel
import rotaryio
import tmidi
import usb_midi
from micropython import const

try:
    from typing import Optional, Tuple
except ImportError:
    pass

try:
    from adafruit_pixelbuf import PixelReturnSequence, PixelReturnType, PixelSequence, PixelType
except ImportError:
    pass

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/relic-se/CircuitPython_Synthiota.git"

# pin mapping

_LED_PIN = board.GP18
_LED_COUNT = const(27)
_LED_BRIGHTNESS = 0.1

_I2C_SDA_PIN = board.GP2
_I2C_SCL_PIN = board.GP3

_DISPLAY_SCLK_PIN = board.GP10
_DISPLAY_MOSI_PIN = board.GP11
_DISPLAY_RESET_PIN = board.GP12
_DISPLAY_DC_PIN = board.GP13

_ADC_MUX_PINS = (board.GP9, board.GP8, board.GP7)
_ADC_PIN = board.GP26
_ADC_COUNT = const(8)
_ADC_SMOOTH_SHIFT = const(3)

_ENCODER_A_PIN = board.GP27
_ENCODER_B_PIN = board.GP28
_ENCODER_SW_PIN = board.GP19

_UART_RX_PIN = board.GP17
_UART_TX_PIN = board.GP16

_I2S_BCLK_PIN = board.GP20
_I2S_LRCLK_PIN = board.GP21
_I2S_DATA_PIN = board.GP22

_MPR121_I2C_ADDRS = (0x5A, 0x5B)

# program constants

_DEFAULT_SAMPLE_RATE = const(44100)
_DEFAULT_CHANNEL_COUNT = const(2)
_DEFAULT_BUFFER_SIZE = const(4096)

_DISPLAY_WIDTH = const(132)
_DISPLAY_HEIGHT = const(64)

# map touch id to led index
_PAD_TO_LED = (7, 6, 5, 4, 3, 2, 1, 0, 8, 9, 10, 11, 18, 17, 16, 15, 23, 22, 21, 20, 19, 12, 13, 14)

_LED_EDIT = const(24)
_LED_MODE = const(25)
_LED_PLAY = const(26)

# map step pads to an index
_STEP_PADS = (7, 6, 5, 4, 3, 2, 1, 0, 8, 9, 10, 11, 18, 17, 16, 15)

# pad defs
_PAD_DOWN = const(19)
_PAD_UP = const(20)

_PAD_RSLIDE_A = const(12)
_PAD_RSLIDE_B = const(13)
_PAD_RSLIDE_C = const(14)
_RSLIDE_PADS = (_PAD_RSLIDE_A, _PAD_RSLIDE_B, _PAD_RSLIDE_C)

_PAD_LSLIDE_A = const(23)
_PAD_LSLIDE_B = const(22)
_PAD_LSLIDE_C = const(21)
_LSLIDE_PADS = (_PAD_LSLIDE_A, _PAD_LSLIDE_B, _PAD_LSLIDE_C)


class Slider:
    """Simple capacitive touch slider made from three pads attached to an MPR121."""

    def __init__(  # noqa: PLR0913
        self,
        pads: list,
        wrap: bool = False,
        offset: int = 0,
        scale: int = None,
        pull: Optional[digitalio.Pull] = None,
    ):
        """Create a Slider object using the provided MPR121 channels.

        :param pads: A list of 3 adafruit_mpr121.MPR121_Channel objects
        :param wrap: Whether or not to wrap the value in a "circular" fashion
        :param offset: An offset that will be applied to the slider value from 0 to 1
        :param scale: The size of each pad, defaults to 0.333.
        :param pull: Specify external pull resistor type. If `None`, assume pull-down or
            chip-specific implementation that does not require a pull.
        """
        if len(pads) != 3:
            raise ValueError("Invalid number of pads")

        self._channels = tuple(pads)
        self._wrap = wrap
        self._offset = offset
        self._scale = scale if scale is not None else 1 / (len(self._channels) - 1)
        self._pull = (
            pull
            if pull is not None
            else (digitalio.Pull.UP if sys.platform == "RP2350" else digitalio.Pull.DOWN)
        )

        self._threshold = [0] * len(self._channels)
        self._value = 0
        self.reset()

    def reset(self) -> None:
        """Reset the baseline data of the MPR121."""
        for i, channel in enumerate(self._channels):
            value = channel._mpr121.baseline_data(channel._channel)
            self._threshold[i] = (
                value if value > 0 else (1 if self._pull is digitalio.Pull.DOWN else 254)
            )

    @property
    def raw_value(self) -> Tuple[float]:
        """Get the relative position value of each slider pad."""
        return tuple(
            [
                (x.raw_value - self._threshold[i])
                / self._threshold[i]
                * (1 if self._pull is digitalio.Pull.DOWN else -1)
                for i, x in enumerate(self._channels)
            ]
        )

    @property
    def value(self) -> float:
        """Get the position of the slider as a number from 0 to 1 or returns `None` if there is no
        touch detected.
        """
        a, b, c = self.raw_value
        value = None

        # cases when finger is touching two pads
        if a >= 0 and b >= 0:
            value = self._scale * (0 + (b / (a + b)))
        elif b >= 0 and c >= 0:
            value = self._scale * (1 + (c / (b + c)))
        elif c >= 0 and a >= 0 and self._wrap:
            value = self._scale * (2 + (a / (c + a)))

        # special cases when finger is just on a single pad
        elif a > 0 and b <= 0 and c <= 0:
            value = 0 * self._scale
        elif a <= 0 and b > 0 and c <= 0:
            value = 1 * self._scale
        elif a <= 0 and b <= 0 and c > 0 and self._wrap:
            value = 2 * self._scale

        if value is not None:  # i.e. if touched
            # filter noise
            if abs(value - self._value) > 0.5:
                value = self._value
            else:
                self._value = value

            # apply offset
            value = (value + self._offset) % 1
        return value


class Synthiota:  # noqa: PLR0904
    """Helper library for Synthiota."""

    def __init__(
        self,
        voice_count: int = 1,
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
        channel_count: int = _DEFAULT_CHANNEL_COUNT,
        buffer_size: int = _DEFAULT_BUFFER_SIZE,
    ):
        """Setup hardware resources including audio output, midi usb/uart, touch inputs, display,
        neopixels, encoder, and potentiometers.

        :param voice_count: The maximum number of voices to mix
        :param sample_rate: The sample rate to be used for all samples
        :type sample_rate: int
        :param channel_count: The number of channels the source samples contain. 1 = mono; 2 =
            stereo.
        :type channel_count: int
        :param buffer_size: The total size in bytes of the buffers to mix into
        :type buffer_size: int
        """

        # audio
        self._voice_count = voice_count
        self._sample_rate = sample_rate
        self._channel_count = channel_count
        self._buffer_size = buffer_size
        self._audio = audiobusio.I2SOut(
            bit_clock=_I2S_BCLK_PIN,
            word_select=_I2S_LRCLK_PIN,
            data=_I2S_DATA_PIN,
        )
        self._mixer = audiomixer.Mixer(
            voice_count=voice_count,
            sample_rate=sample_rate,
            channel_count=channel_count,
            buffer_size=buffer_size,
        )
        self._audio.play(self._mixer)

        # midi
        self._uart = busio.UART(
            rx=_UART_RX_PIN,
            tx=_UART_TX_PIN,
            baudrate=31250,
            timeout=0.001,
        )
        self._midi_uart = tmidi.MIDI(
            midi_in=self._uart,
            midi_out=self._uart,
        )
        self._midi_usb = (
            tmidi.MIDI(
                midi_in=usb_midi.ports[0],
                midi_out=usb_midi.ports[1],
            )
            if len(usb_midi.ports) >= 2
            else None
        )

        # touch
        self._i2c = busio.I2C(
            scl=_I2C_SCL_PIN,
            sda=_I2C_SDA_PIN,
            frequency=400_000,
        )
        self._mpr121 = tuple(
            [adafruit_mpr121.MPR121(self._i2c, address=a) for a in _MPR121_I2C_ADDRS]
        )
        self._mpr121[1]._write_register_byte(adafruit_mpr121.MPR121_CONFIG1, 0x10)
        self._mpr121_touched = [False] * (len(_MPR121_I2C_ADDRS) * 12)

        self._up_button = adafruit_debouncer.Button(
            lambda: self._mpr121_touched[_PAD_UP],
            value_when_pressed=True,
        )
        self._down_button = adafruit_debouncer.Button(
            lambda: self._mpr121_touched[_PAD_DOWN],
            value_when_pressed=True,
        )

        self._left_slider = Slider([self._mpr121[i // 12][i % 12] for i in _LSLIDE_PADS])
        self._right_slider = Slider([self._mpr121[i // 12][i % 12] for i in _RSLIDE_PADS])

        # display
        displayio.release_displays()
        self._spi = busio.SPI(
            clock=_DISPLAY_SCLK_PIN,
            MOSI=_DISPLAY_MOSI_PIN,
        )
        self._display_bus = fourwire.FourWire(
            self._spi,
            command=_DISPLAY_DC_PIN,
            reset=_DISPLAY_RESET_PIN,
            baudrate=24_000_000,
        )
        self._display = adafruit_displayio_sh1106.SH1106(
            self._display_bus,
            width=_DISPLAY_WIDTH,
            height=_DISPLAY_HEIGHT,
            colstart=3,
        )

        # leds
        self._leds = neopixel.NeoPixel(_LED_PIN, _LED_COUNT, brightness=_LED_BRIGHTNESS)
        self._leds.fill(0x000000)

        # encoder
        self._encoder = rotaryio.IncrementalEncoder(
            pin_a=_ENCODER_A_PIN,
            pin_b=_ENCODER_B_PIN,
            divisor=4,
        )
        self._encoder_switch = digitalio.DigitalInOut(_ENCODER_SW_PIN)
        self._encoder_switch.direction = digitalio.Direction.INPUT
        self._encoder_switch.pull = digitalio.Pull.UP
        self._encoder_button = adafruit_debouncer.Button(self._encoder_switch)

        # potentiometers
        self._adc = analogio.AnalogIn(_ADC_PIN)
        self._adc_raw_value = array.array("H", [0] * _ADC_COUNT)
        self._adc_value = [0] * _ADC_COUNT
        self._adc_mux_pins = tuple([digitalio.DigitalInOut(pin) for pin in _ADC_MUX_PINS])
        for dio in self._adc_mux_pins:
            dio.direction = digitalio.Direction.OUTPUT
            dio.value = False

        # prime ADC accumulators
        for i in range(50):
            self._update_adc_values()

        # reset baseline data of MPR121 sliders
        time.sleep(0.1)
        self._left_slider.reset()
        self._right_slider.reset()

    def _adc_mux_select(self, index: int) -> None:
        for i, dio in enumerate(self._adc_mux_pins):
            dio.value = bool(index & (1 << i))

    def _get_adc_value(self, index: int) -> int:
        self._adc_mux_select(index)
        return self._adc.value

    def _update_adc_values(self) -> None:
        for i in range(_ADC_COUNT):
            value = self._get_adc_value(i)
            self._adc_raw_value[i] += (value - self._adc_raw_value[i]) >> _ADC_SMOOTH_SHIFT
            self._adc_value[i] = self._adc_raw_value[i] / 65535

    def update(self) -> None:
        """Update buttons, potentiometers, and touch inputs. Call this frequently for the best
        results!
        """
        # touch
        for i, x in enumerate(self._mpr121):
            for j, v in enumerate(x.touched_pins):
                self._mpr121_touched[i * 12 + j] = v

        # buttons
        self._up_button.update()
        self._down_button.update()
        self._encoder_button.update()

        # potentiometers
        self._update_adc_values()

    @property
    def voice_count(self) -> int:
        """The maximum number of voices available in the mixer"""
        return self._voice_count

    @property
    def sample_rate(self) -> int:
        """How quickly samples are played through the audio output in Hertz (cycles per second)"""
        return self._sample_rate

    @property
    def channel_count(self) -> int:
        """The number of channels of the audio output. 1 = mono; 2 = stereo."""
        return self._channel_count

    @property
    def buffer_size(self) -> int:
        """The total size in bytes of the buffers used by the mixer"""
        return self._buffer_size

    @property
    def audio(self) -> audiobusio.I2SOut:
        """The I2S audio output object."""
        return self._audio

    @property
    def mixer(self) -> audiomixer.Mixer:
        """The audio output mixer. Use this object to attach your audio sources."""
        return self._mixer

    @property
    def display(self) -> adafruit_displayio_sh1106.SH1106:
        """The display bus object."""
        return self._display

    @property
    def leds(self) -> neopixel.NeoPixel:
        """The neopixel driver which controls all 27 leds on the device."""
        return self._leds

    @property
    def encoder(self) -> rotaryio.IncrementalEncoder:
        """The incremental encoder object."""
        return self._encoder

    @property
    def encoder_button(self) -> adafruit_debouncer.Button:
        """The object for the encoder button."""
        return self._encoder_button

    @property
    def pots(self) -> Tuple[Optional[float]]:
        """All 8 potentiometer values as a tuple of floats from 0 to 1."""
        return tuple(self._adc_value)

    @property
    def pot_leds(self) -> Optional[PixelReturnSequence]:
        """The NeoPixels corresponding to each of the 8 potentiometer from left-to-right."""
        return self._leds[16:24]

    @pot_leds.setter
    def pot_leds(self, value: Optional[PixelSequence]) -> None:
        if isinstance(value, int):
            value = [value] * 8
        elif len(value) != 8:
            value = [value[i % len(value)] for i in range(8)]
        self._leds[16:24] = value

    @property
    def touched(self) -> Tuple[Optional[bool]]:
        """The state of all touchpads as a tuple of 24 booleans."""
        return tuple(self._mpr121_touched)

    @property
    def touched_steps(self) -> Tuple[Optional[bool]]:
        """The state of all 16 step touch pads in left-to-right order from bottom-left to
        top-right.
        """
        return tuple([self._mpr121_touched[i] for i in _STEP_PADS])

    @property
    def step_leds(self) -> Optional[PixelReturnSequence]:
        """The NeoPixels for each step touch pad in left-to-right order from bottom-left to
        top-right.
        """
        return self._leds[:16]

    @step_leds.setter
    def step_leds(self, value: Optional[PixelSequence]) -> None:
        if isinstance(value, int):
            value = [value] * 16
        elif len(value) != 16:
            value = [value[i % len(value)] for i in range(16)]
        self._leds[:16] = value

    @property
    def up_button(self) -> adafruit_debouncer.Button:
        """The object for the up button."""
        return self._up_button

    @property
    def up_led(self) -> Optional[PixelReturnType]:
        """The NeoPixel above the up button."""
        return self._leds[_PAD_TO_LED.index(_PAD_UP)]

    @up_led.setter
    def up_led(self, value: Optional[PixelType]) -> None:
        self._leds[_PAD_TO_LED.index(_PAD_UP)] = value

    @property
    def down_button(self) -> adafruit_debouncer.Button:
        """The object for the down button."""
        return self._down_button

    @property
    def down_led(self) -> Optional[PixelReturnType]:
        """The NeoPixel above the down button."""
        return self._leds[_PAD_TO_LED.index(_PAD_DOWN)]

    @down_led.setter
    def down_led(self, value: Optional[PixelType]) -> None:
        self._leds[_PAD_TO_LED.index(_PAD_DOWN)] = value

    @property
    def left_slider(self) -> Slider:
        """The object for the left horizontal touch slider."""
        return self._left_slider

    @property
    def left_slider_leds(self) -> Optional[PixelReturnSequence]:
        """The NeoPixels above the left slider from left to right."""
        return self._leds[16:19]

    @left_slider_leds.setter
    def left_slider_leds(self, value: Optional[PixelSequence]) -> None:
        if isinstance(value, int):
            value = [value] * 3
        elif len(value) != 3:
            value = [value[i % len(value)] for i in range(3)]
        self._leds[16:19] = value

    @property
    def right_slider(self) -> Slider:
        """The object for the right horizontal touch slider."""
        return self._right_slider

    @property
    def right_slider_leds(self) -> Optional[PixelReturnSequence]:
        """The NeoPixels above the right slider from left to right."""
        return self._leds[21:24]

    @right_slider_leds.setter
    def right_slider_leds(self, value: Optional[PixelSequence]) -> None:
        if isinstance(value, int):
            value = [value] * 3
        elif len(value) != 3:
            value = [value[i % len(value)] for i in range(3)]
        self._leds[21:24] = value

    @property
    def mode_leds(self) -> Optional[PixelReturnSequence]:
        """The mode NeoPixels in the order of edit, mode, and play."""
        return self._leds[24:27]

    @mode_leds.setter
    def mode_leds(self, value: Optional[PixelSequence]) -> None:
        if isinstance(value, int):
            value = [value] * 3
        elif len(value) != 3:
            value = [value[i % len(value)] for i in range(3)]
        self._leds[24:27] = value

    @property
    def edit_led(self) -> Optional[PixelReturnType]:
        """The edit NeoPixel."""
        return self._leds[_LED_EDIT]

    @edit_led.setter
    def edit_led(self, value: Optional[PixelType]) -> None:
        self._leds[_LED_EDIT] = value

    @property
    def mode_led(self) -> Optional[PixelReturnType]:
        """The mode NeoPixel."""
        return self._leds[_LED_MODE]

    @mode_led.setter
    def mode_led(self, value: Optional[PixelType]) -> None:
        self._leds[_LED_MODE] = value

    @property
    def play_led(self) -> Optional[PixelReturnType]:
        """The play NeoPixel."""
        return self._leds[_LED_PLAY]

    @play_led.setter
    def play_led(self, value: Optional[PixelType]) -> None:
        self._leds[_LED_PLAY] = value

    def get_midi_messages(self) -> Tuple[Optional[tmidi.Message]]:
        """Read all available messages from both the USB and UART MIDI ports."""
        msgs = []
        while (
            msg := (self._midi_usb.receive() if self._midi_usb is not None else None)
            or self._midi_uart.receive()
        ):
            msgs.append(msg)
        return tuple(msgs)

    def send_midi_message(self, message: tmidi.Message, channel: int | None = None) -> None:
        """Send a message to both the USB and UART MIDI ports.

        :param message: The MIDI message you would like to send.
        :param channel: The channel to send the MIDI message on. If `None`, the channel provided by
            message will be used.
        """
        if channel is None:
            channel = message.channel
        if self._midi_usb is not None:
            self._midi_usb.send(message, channel=channel)
        self._midi_uart.send(message, channel=channel)
