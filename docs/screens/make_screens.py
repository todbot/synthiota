#!/usr/bin/env python3
"""make_screens.py -- draw example screens of stepseq8, each as a screenshot
and as a full board render with the LEDs lit, in docs/screens/.

  python3 make_screens.py             # all scenes
  python3 make_screens.py all_tracks  # just one

Nothing is drawn by hand. This runs the real circuitpython/stepseq8/code.py
against a fake board and scripted input, and each snapshot takes the display
and LEDs from the same moment.

LED brightness is lifted to show up in a picture: colors and relative
brightness are true, absolute brightness isn't.

LED positions are from schematics/synthiota1/synthiota1.kicad_pcb.
Needs Pillow, the macOS system fonts, and checkouts of CircuitPython_Synth_Tools
and CircuitPython_TMIDI in ~/projects/circuitpython/.
"""

import random
import sys
import tempfile
import types
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
APP = HERE.parent.parent / "circuitpython/stepseq8"
RENDER = HERE.parent / "synthiota_render_front.png"
LIBS = Path.home() / "projects/circuitpython"
SYNTH_TOOLS = LIBS / "CircuitPython_Synth_Tools"
FONTS = "/System/Library/Fonts/"
sys.path[:0] = [str(APP), str(SYNTH_TOOLS), str(SYNTH_TOOLS / "tests/lib"),
                str(LIBS / "CircuitPython_TMIDI")]

VISIBLE_W = 127  # the rest of the bitmap is past the glass
SCREEN_H = 64

SHOT_SCALE, SHEET_SCALE = 6, 5
SHOT_PAD = 12
OLED_OFF = (10, 14, 20)
OLED_ON = (232, 244, 255)
OLED_GRID = (22, 28, 38)

BG = "#ececef"
INK = "#1b1d22"
SHEET_COLS = 3

BOARD_W = 1116  # half the render, still more than GitHub shows
GLASS = (933, 91, 1302, 275)  # in the render
GLASS_LEFT = 1  # relic's colstart=3 puts bitmap x=0 on the glass's second column

# board edge, mm, and the render's px per mm
BX0, BY0 = 17.4, 15.4
LED_S = 2232 / 177.8
POT_LED_X = (36.4, 56.4, 76.4, 96.4, 116.4, 136.4, 157.4, 177.9)
PAD_LED_X = [36.4 + 20 * i for i in range(8)]
LED_MM = ([(x, 116.5) for x in PAD_LED_X] + [(x, 96.5) for x in PAD_LED_X]
          + [(x, 73.4) for x in POT_LED_X] + [(155.4, 43.2), (164.4, 43.2), (173.4, 43.2)])
LED_FULL = 0x66  # the brightest channel stepseq8 uses
CORE_R, HALO_R, HALO_BLUR = 13, 42, 26
EDIT_LED, MODE_LED, PLAY_LED = 24, 25, 26

LSLIDE_C, RSLIDE_C = 21, 14
CELL_PAST, CELL_OFF = 0, 1


# --- fake displayio and bitmaptools -------------------------------------------

class Bitmap:
    def __init__(self, width, height, _colors):
        self.width, self.height = width, height
        self.data = bytearray(width * height)

    def __getitem__(self, xy):
        return self.data[xy[1] * self.width + xy[0]]

    def __setitem__(self, xy, val):
        self.data[xy[1] * self.width + xy[0]] = val

    def fill(self, val):
        self.data[:] = bytes([val]) * len(self.data)


def fill_region(bmp, x1, y1, x2, y2, val):
    row = bytes([val]) * (x2 - x1)
    for y in range(y1, y2):
        bmp.data[y * bmp.width + x1 : y * bmp.width + x2] = row


def blit(dest, src, x, y, *, x1=0, y1=0, x2=None, y2=None):
    for j in range(y2 - y1):
        s = (y1 + j) * src.width + x1
        d = (y + j) * dest.width + x
        dest.data[d : d + x2 - x1] = src.data[s : s + x2 - x1]


displayio = types.ModuleType("displayio")
displayio.Bitmap = Bitmap
displayio.Palette = lambda n: [0] * n
displayio.TileGrid = lambda bmp, pixel_shader: bmp
displayio.Group = list
bitmaptools = types.ModuleType("bitmaptools")
bitmaptools.fill_region = fill_region
bitmaptools.blit = blit
sys.modules.update(displayio=displayio, bitmaptools=bitmaptools)
sys.modules["micropython"] = types.SimpleNamespace(const=lambda x: x)

clock = [0]
import adafruit_ticks  # noqa: E402

adafruit_ticks.ticks_ms = lambda: clock[0]

import tmidi  # noqa: E402


# --- fake relic_synthiota -----------------------------------------------------

class Button:
    def __init__(self):
        self.down = self.last = self.pressed = self.released = False

    def update(self):
        self.pressed = self.down and not self.last
        self.released = self.last and not self.down
        self.last = self.down


class Leds(list):
    auto_write = True
    brightness = 1.0
    shows = 0

    def show(self):
        self.shows += 1


class Board:
    """Enough of relic_synthiota.Synthiota. Its LED ranges must match relic's."""

    script = None
    midi_in = []

    def __init__(self, **_kwargs):
        Board.current = self
        self.display = types.SimpleNamespace(auto_refresh=True, root_group=None,
                                             refresh=lambda: None)
        self.leds = Leds([0] * 27)
        self.encoder = types.SimpleNamespace(position=0)
        self.encoder_button, self.up_button, self.down_button = Button(), Button(), Button()
        self.pots = (0.5,) * 8
        self.touched_list = [False] * 24
        self.steps_list = [False] * 16

    touched = property(lambda self: tuple(self.touched_list))
    touched_steps = property(lambda self: tuple(self.steps_list))

    def _set_range(self, first, vals):
        self.leds[first : first + len(vals)] = vals

    step_leds = property(None, lambda self, v: self._set_range(0, v))
    pot_leds = property(None, lambda self, v: self._set_range(16, v))
    edit_led = property(None, lambda self, v: self._set_range(EDIT_LED, [v]))
    mode_led = property(None, lambda self, v: self._set_range(MODE_LED, [v]))
    play_led = property(None, lambda self, v: self._set_range(PLAY_LED, [v]))

    def update(self):
        for b in (self.encoder_button, self.up_button, self.down_button):
            b.update()

    def get_midi_messages(self):
        clock[0] += 1
        next(Board.script)
        msgs, Board.midi_in = Board.midi_in, []
        return msgs

    def send_midi_message(self, _msg):
        pass


sys.modules["relic_synthiota"] = types.SimpleNamespace(Synthiota=Board)


class SceneDone(Exception):
    pass


# --- scripted input -----------------------------------------------------------

def wait(ms):
    end = clock[0] + ms
    while clock[0] < end:
        yield


def press(button, ms=60):
    button.down = True
    yield from wait(ms)
    button.down = False
    yield from wait(30)


def touch(pad, ms=60):
    s = Board.current
    s.touched_list[pad] = True
    yield from wait(ms)
    s.touched_list[pad] = False
    yield from wait(30)


def tap_play():
    yield from press(Board.current.encoder_button)


def select(app, n):
    while app["cur"] != n:
        yield from press(Board.current.up_button)


def pad_of_step(step):
    """The top row is steps 1-8, relic numbers the bottom row first."""
    return (step + 8) % 16


def seed(app):
    """A set of tracks to look at, then the pots where those values put them."""
    # fmt: off
    arp = (48, 55, 60, 63, 67, 63, 60, 55, 48, 55, 60, 65, 68, 65, 60, 55)
    bass = (36, 36, 48, 36, 34, 34, 46, 34, 41, 41, 53, 41)
    # (track, notes, on-steps, length, division)
    tracks = (
        (0, arp, None, 16, 2),
        (1, bass, (0, 2, 3, 4, 6, 8, 10, 11), 12, 2),
        (2, (72, 75, 79, 82, 79, 75, 70), None, 7, 2),
        (3, [60 + (i * 7) % 24 for i in range(32)], [i for i in range(32) if i % 3], 32, 2),
        (4, (48, 48, 55, 60, 48), (0, 3), 5, 4),
        (5, [64 + (i * 5) % 12 for i in range(24)], (0, 1, 4, 5, 8, 12, 13, 16, 20, 22), 24, 2),
        (6, (84, 79, 76, 72, 67), (0, 2, 4), 9, 0),
        (7, (36, 43), (0, 1), 3, 6),
    )
    # fmt: on
    for num, notes, ons, length, div in tracks:
        t = app["tracks"][num]
        t.length = length
        t.div = div
        t.set_tempo(app["eng"].bpm)
        for i, step in enumerate(t.seq.steps):
            step[0] = notes[i % len(notes)]
            step[2] = (3 + (i * 5) % 12) / 16
            step[3] = i < length and (ons is None or i in ons)
    app["tracks"][4].muted = True
    app["tracks"][6].muted = True
    app["sync_params"]()
    params = app["_params"]
    Board.current.pots = tuple((p.val - p.vmin) / p.span for p in params[:8])


def snap(app, shots):
    """The next UI pass: draws, then shows the LEDs, then comes back here."""
    s = Board.current
    shows = s.leds.shows
    while s.leds.shows == shows:
        yield
    shots.append(dict(
        bmp=bytes(app["ui"].bmp.data), bmp_w=app["ui"].bmp.width, leds=list(s.leds),
        view=app["view"], page=app["page"], held=app["held"], cells=bytes(app["ui"]._cells),
        length=app["tracks"][app["cur"]].length, pos=app["tracks"][app["cur"]].pos))


def scene_track_playing(app, shots):
    yield from tap_play()
    yield from wait(620)
    yield from snap(app, shots)


def scene_track_short(app, shots):
    yield from select(app, 2)
    yield from tap_play()
    yield from wait(500)
    yield from snap(app, shots)


def scene_track_page2(app, shots):
    yield from select(app, 3)
    yield from touch(RSLIDE_C)
    yield from tap_play()
    yield from wait(2600)
    yield from snap(app, shots)


def scene_step_held(app, shots):
    yield from tap_play()
    yield from wait(400)
    Board.current.steps_list[pad_of_step(4)] = True
    yield from wait(120)
    yield from snap(app, shots)


def scene_pot_turning(app, shots):
    s = Board.current
    yield from tap_play()
    yield from wait(400)
    start, target = s.pots[0], (12 - 1) / 31
    for i in range(1, 11):
        s.pots = (start + (target - start) * i / 10,) + s.pots[1:]
        yield from wait(30)
    yield from snap(app, shots)


def scene_paused(app, shots):
    yield from tap_play()
    yield from wait(780)
    yield from tap_play()
    yield from wait(100)
    yield from snap(app, shots)


def scene_all_tracks(app, shots):
    s = Board.current
    yield from tap_play()
    yield from touch(LSLIDE_C)
    yield from wait(60)
    s.steps_list[8 + 2] = True  # top pad 3, selects track 3
    yield from wait(40)
    s.steps_list[8 + 2] = False
    yield from wait(1280)
    yield from snap(app, shots)


def scene_pattern_saved(app, shots):
    s = Board.current
    yield from tap_play()
    yield from wait(200)
    s.encoder_button.down = True
    yield from wait(40)
    s.steps_list[2] = True  # bottom pad 3
    yield from wait(1060)
    yield from snap(app, shots)


def scene_ext_clock(app, shots):
    Board.midi_in = [tmidi.Message(tmidi.START)]
    yield
    for _ in range(48):
        Board.midi_in = [tmidi.Message(tmidi.CLOCK)]
        yield from wait(21)
    yield from snap(app, shots)


SCENES = {
    "track_playing": ("track view, playing", scene_track_playing),
    "track_short": ("a 7-step track", scene_track_short),
    "track_page2": ("a 32-step track, on steps 17-32", scene_track_page2),
    "step_held": ("holding step 5", scene_step_held),
    "pot_turning": ("turning the LEN pot", scene_pot_turning),
    "paused": ("paused", scene_paused),
    "all_tracks": ("all-tracks view, 5 and 7 muted", scene_all_tracks),
    "pattern_saved": ("saving pattern 3", scene_pattern_saved),
    "ext_clock": ("following MIDI clock", scene_ext_clock),
}


def run_scene(scene):
    clock[0] = 1000
    random.seed(1)
    with tempfile.TemporaryDirectory() as tmp:
        source = (APP / "code.py").read_text().replace('"/stepseq8.dat"', repr(tmp + "/s.dat"))
        code = compile(source, "code.py", "exec")
        app = {"__name__": "__main__"}
        shots = []

        def script():
            yield from wait(60)
            seed(app)
            yield from wait(60)
            yield from scene(app, shots)
            raise SceneDone

        Board.script = script()
        try:
            exec(code, app)  # pylint: disable=exec-used
        except SceneDone:
            pass
    if not shots:
        sys.exit("scene never reached its snapshot")
    return shots[0]


def check(name, shot):
    """The pads have to say what the screen says."""
    w = shot["bmp_w"]
    for y in range(SCREEN_H):
        if any(shot["bmp"][y * w + VISIBLE_W : (y + 1) * w]):
            sys.exit(f"{name}: drew past the glass on row {y}")
    if shot["view"] != 0:
        return
    for n in range(16):
        step = shot["page"] * 16 + (n + 8) % 16
        cell = shot["cells"][step]
        lit = shot["leds"][n] != 0
        want = cell not in (CELL_PAST, CELL_OFF) or (n + 8) % 16 == shot["held"]
        if lit != want:
            sys.exit(f"{name}: pad {n} LED {lit} but step {step + 1} cell is {cell}")


# --- images -------------------------------------------------------------------

def screen_image(shot, scale):
    """The panel as monobit shows it, with a grid so the pixels read as pixels."""
    w = shot["bmp_w"]
    img = Image.new("RGB", (VISIBLE_W * scale, SCREEN_H * scale), OLED_GRID)
    d = ImageDraw.Draw(img)
    for y in range(SCREEN_H):
        for x in range(VISIBLE_W):
            color = OLED_ON if shot["bmp"][y * w + x] else OLED_OFF
            d.rectangle((x * scale, y * scale, x * scale + scale - 2, y * scale + scale - 2),
                        fill=color)
    return img


def screenshot(shot):
    img = screen_image(shot, SHOT_SCALE)
    framed = Image.new("RGB", (img.width + 2 * SHOT_PAD, img.height + 2 * SHOT_PAD), OLED_OFF)
    framed.paste(img, (SHOT_PAD, SHOT_PAD))
    return framed


def contact_sheet(rows):
    f = ImageFont.truetype(FONTS + "Avenir Next.ttc", 30, index=2)
    cell_w = VISIBLE_W * SHEET_SCALE + 2 * SHOT_PAD
    cell_h = SCREEN_H * SHEET_SCALE + 2 * SHOT_PAD
    margin, gap, label_h = 40, 36, 48
    n_rows = (len(rows) + SHEET_COLS - 1) // SHEET_COLS
    cols = min(SHEET_COLS, len(rows))
    sheet = Image.new("RGB", (margin * 2 + cols * cell_w + (cols - 1) * gap,
                              margin * 2 + n_rows * (cell_h + label_h) + (n_rows - 1) * gap), BG)
    d = ImageDraw.Draw(sheet)
    for i, (caption, shot) in enumerate(rows):
        x = margin + (i % SHEET_COLS) * (cell_w + gap)
        y = margin + (i // SHEET_COLS) * (cell_h + label_h + gap)
        d.text((x, y), caption, font=f, fill=INK)
        frame = Image.new("RGB", (cell_w, cell_h), OLED_OFF)
        frame.paste(screen_image(shot, SHEET_SCALE), (SHOT_PAD, SHOT_PAD))
        sheet.paste(frame, (x, y + label_h))
    return sheet


def led_xy(i):
    x, y = LED_MM[i]
    return (x - BX0) * LED_S, (y - BY0) * LED_S


def lifted(color):
    """Keep the hue and relative brightness, at a level a picture can show."""
    r, g, b = color >> 16 & 255, color >> 8 & 255, color & 255
    top = max(r, g, b)
    level = min(top / LED_FULL, 1.0) ** 0.5
    return tuple(round(c / top * 255 * level) for c in (r, g, b))


def board_image(shot, base):
    img = base.copy()

    x0, y0, x1, y1 = GLASS
    w = shot["bmp_w"]
    panel = Image.new("RGB", (128, SCREEN_H), OLED_OFF)
    for y in range(SCREEN_H):
        for x in range(VISIBLE_W):
            if shot["bmp"][y * w + x]:
                panel.putpixel((x + GLASS_LEFT, y), OLED_ON)
    # up first: the glass is a fractional scale, and nearest alone looks uneven
    panel = panel.resize((128 * 8, SCREEN_H * 8), Image.NEAREST)
    panel = panel.resize((x1 - x0, y1 - y0), Image.LANCZOS)
    mask = Image.new("L", panel.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *panel.size), radius=5, fill=255)
    img.paste(panel, (x0, y0), mask)

    halo = Image.new("RGB", img.size, 0)
    core = Image.new("RGB", img.size, 0)
    d_halo, d_core = ImageDraw.Draw(halo), ImageDraw.Draw(core)
    for i, color in enumerate(shot["leds"]):
        if color:
            x, y = led_xy(i)
            c = lifted(color)
            d_halo.ellipse((x - HALO_R, y - HALO_R, x + HALO_R, y + HALO_R), fill=c)
            d_core.ellipse((x - CORE_R, y - CORE_R, x + CORE_R, y + CORE_R), fill=c)
    img = ImageChops.add(img, halo.filter(ImageFilter.GaussianBlur(HALO_BLUR)))
    img = ImageChops.add(img, core.filter(ImageFilter.GaussianBlur(3)))
    return img


def small_board(board, base):
    """Half size and paletted, dithered only in the glows: they show rings
    without it, and dithering everything triples the file."""
    size = (BOARD_W, round(BOARD_W * board.height / board.width))
    small = board.resize(size, Image.LANCZOS)
    glows = ImageChops.difference(board, base).convert("L").point(lambda v: 255 if v >= 6 else 0)
    glows.paste(0, GLASS)
    glows = glows.resize(size, Image.BILINEAR).point(lambda v: 255 if v else 0)
    flat = small.quantize(256, method=Image.Quantize.MEDIANCUT)
    img = flat.copy()
    img.paste(small.quantize(palette=flat, dither=Image.Dither.FLOYDSTEINBERG), (0, 0), glows)
    return img


def check_glows(name, shot, base, img):
    for i, color in enumerate(shot["leds"]):
        x, y = (round(v) for v in led_xy(i))
        changed = img.getpixel((x, y)) != base.getpixel((x, y))
        if changed != bool(color):
            sys.exit(f"{name}: LED {i} is {color:06x} but its glow says {changed}")


def main():
    names = sys.argv[1:] or list(SCENES)
    bg = Image.open(RENDER).convert("RGB")
    base = ImageEnhance.Brightness(ImageEnhance.Color(bg).enhance(0.55)).enhance(0.8)
    rows = []
    for name in names:
        caption, scene = SCENES[name]
        shot = run_scene(scene)
        check(name, shot)
        rows.append((caption, shot))
        screenshot(shot).quantize(16).save(HERE / f"{name}.png", optimize=True)
        board = board_image(shot, base)
        check_glows(name, shot, base, board)
        small_board(board, base).save(HERE / f"{name}_board.png", optimize=True)
        print(name, [f"{v:06x}" for v in shot["leds"] if v][:4], "...")
    if len(names) == len(SCENES):
        contact_sheet(rows).quantize(32).save(HERE / "screens.png", optimize=True)


if __name__ == "__main__":
    main()
