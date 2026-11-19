"""A desktop window: play a cartridge with picture, sound, keyboard and gamepad.

    python -m gameboy_python play "Tetris (World) (Rev 1).zip"
    python -m gameboy_python play game.gbc --machine cgb --scale 5
    python -m gameboy_python play game.gb --boot skip --palette green

The only module that needs a library beyond the cores: pygame-ce (the ``frontend`` extra), for
SDL's window, audio and game controllers. Run it on PyPy. This is the reference board, correct
before fast: where it runs below real time the window shows every frame it makes and the sound
plays at the console's pitch with gaps, rather than stretched. Where the machine is fast enough,
sound sets the pace (SDL's audio thread drains a short queue and a frame runs when it runs
short), as in the family's other frontends.

The machine is the cartridge's: a Game Boy Color for a header that asks for one ($0143 bit 7),
else the DMG. It boots from your boot ROM when one is found (``boot.find_boot_rom``), else from
the skip-boot state.

Saves: the cartridge's battery memory is read from ``NAME.sav`` beside the image at power-on and
written there on quit and power cycle (raw RAM; an MBC3's clock follows as the 48-byte trailer
BGB, SameBoy and mGBA share: docs/cartridge.md).
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import zipfile
from array import array
from collections.abc import Callable
from pathlib import Path

from gameboy_python import GameBoy, load_cartridge
from gameboy_python.boot import find_boot_rom
from gameboy_python.cartridge import parse_header
from gameboy_python.image import write_png, write_rgb_png
from gameboy_python.machines import CLOCK_HZ, DOTS_PER_FRAME, MACHINES

WIDTH, HEIGHT = 160, 144
#: Frames of sound kept queued ahead of the speaker when the board keeps up.
BUFFER_FRAMES = 3
#: LCD frames a second: 59.73 (the LCD off or on, the frontend steps by this much time).
RATE = CLOCK_HZ / DOTS_PER_FRAME

HELP = """\
Arrows      D-pad            Z   B      X   A
Right Shift Select           Enter  Start
F5          power cycle      F3  pause   F11  fullscreen
Tab (hold)  fast forward (no sound)      F12  screenshot (PNG)   Esc  quit
A gamepad plays too: buttons by position (the pad's right face button is A,
its lower one B)."""

KEYS = (  # (button, pygame key names)
    ("up", ("K_UP",)),
    ("down", ("K_DOWN",)),
    ("left", ("K_LEFT",)),
    ("right", ("K_RIGHT",)),
    ("b", ("K_z",)),
    ("a", ("K_x",)),
    ("select", ("K_RSHIFT",)),
    ("start", ("K_RETURN", "K_KP_ENTER")),
)

PAD_BUTTONS = (  # (button, SDL game controller button name)
    ("up", "CONTROLLER_BUTTON_DPAD_UP"),
    ("down", "CONTROLLER_BUTTON_DPAD_DOWN"),
    ("left", "CONTROLLER_BUTTON_DPAD_LEFT"),
    ("right", "CONTROLLER_BUTTON_DPAD_RIGHT"),
    ("b", "CONTROLLER_BUTTON_A"),
    ("a", "CONTROLLER_BUTTON_B"),
    ("select", "CONTROLLER_BUTTON_BACK"),
    ("start", "CONTROLLER_BUTTON_START"),
)

#: The DMG's four shades, lightest first, as opaque BGRA words (0xFFRRGGBB). ``grey`` is
#: image.py's neutral ramp; ``green`` is a by-eye fit of the DMG's reflective LCD, not measured.
PALETTES = {
    "grey": (0xFFFFFFFF, 0xFFAAAAAA, 0xFF555555, 0xFF000000),
    "green": (0xFFC4CFA1, 0xFF8B956D, 0xFF4D533C, 0xFF1F1F1F),
}


# -- conversions (pure, tested without pygame) --------------------------------------


def _widen(v: int) -> int:
    return round(v * 255 / 31)  # as image.rgb_png_bytes widens five bits


#: A CGB colour (RGB555, red in the low five bits) as an opaque BGRA word.
WORDS = [
    0xFF000000 | _widen(c & 31) << 16 | _widen(c >> 5 & 31) << 8 | _widen(c >> 10 & 31)
    for c in range(0x8000)
]


def frame_image(frame: bytes, cgb: bool, palette: str = "grey") -> bytes:
    """The PPU's last picture as 160x144 BGRA bytes: DMG shades through ``palette``, or the
    CGB's RGB555 words widened."""
    if cgb:
        words = array("H", frame)
        if sys.byteorder == "big":
            words.byteswap()
        pixels = array("I", map(WORDS.__getitem__, words))
    else:
        pixels = array("I", map(PALETTES[palette].__getitem__, frame))
    if sys.byteorder == "big":
        pixels.byteswap()
    return pixels.tobytes()


def read_rom(path: Path) -> bytes:
    """The image: a raw file, or the first ``.gb``/``.gbc`` in a zip (else its first member)."""
    if path.suffix.lower() != ".zip":
        return path.read_bytes()
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        name = next((n for n in names if n.lower().endswith((".gb", ".gbc"))), names[0])
        return archive.read(name)


def save_path(rom: Path) -> Path:
    return rom.with_suffix(".sav")


def machine_for(rom: bytes) -> str:
    """``cgb`` for a cartridge that asks for a Game Boy Color, else ``dmg``."""
    return "cgb" if parse_header(rom).cgb_enhanced else "dmg"


class SoundBuffer:
    """Bytes queued for SDL's audio thread, which calls :meth:`fill`."""

    def __init__(self) -> None:
        self._data = bytearray()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._data)

    def push(self, data: bytes) -> None:
        with self._lock:
            self._data += data

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def fill(self, _device: object, stream: memoryview) -> None:
        """SDL's audio callback: copy what is queued, then silence."""
        size = len(stream)
        with self._lock:
            chunk = bytes(self._data[:size])
            del self._data[:size]
        stream[: len(chunk)] = chunk
        if len(chunk) < size:
            stream[len(chunk) :] = bytes(size - len(chunk))


# -- the console --------------------------------------------------------------------


class Console:
    """The board and its cartridge; no pygame."""

    def __init__(self, rom: Path, machine: str = "auto", boot: str = "auto") -> None:
        self.rom = rom
        image = read_rom(rom)
        self.machine = MACHINES[machine_for(image) if machine == "auto" else machine]
        self.cgb = self.machine.cgb_hardware
        boot_rom, self.boot_label = (
            (None, "skip-boot state") if boot == "skip" else find_boot_rom(self.machine.boot_rom)
        )
        if boot == "real" and self.boot_label != "real boot ROM":
            raise SystemExit(f"no real {self.machine.boot_rom} boot ROM ({self.boot_label})")
        self.cartridge = load_cartridge(image)
        save = save_path(rom)
        if save.exists():
            self.cartridge.load_ram(save.read_bytes())
        self.gb = GameBoy(self.cartridge, self.machine, boot_rom=boot_rom)
        self.gb.apu.capture = True
        self.sample_rate = self.gb.apu.sample_rate
        self._frames = 0

    def run_frame(self) -> bytes:
        """One LCD frame's worth of time (the LCD may be off); returns its sound as signed
        16-bit stereo."""
        self._frames += 1
        gb, step, end = self.gb, self.gb.cpu.step, self._frames * DOTS_PER_FRAME
        while gb.t < end:
            step()
        samples = gb.apu.take_samples()
        if sys.byteorder == "big":
            samples.byteswap()
        return samples.tobytes()

    def press(self, pressed: set[str]) -> None:
        """Hold exactly ``pressed`` (joypad.py's button names)."""
        joypad = self.gb.joypad
        for name in joypad.pressed ^ pressed:
            joypad.set_pressed(name, name in pressed)

    def save(self) -> None:
        data = self.cartridge.save_ram()
        if data is not None:
            save_path(self.rom).write_bytes(data)

    def screenshot(self, path: Path) -> None:
        (write_rgb_png if self.cgb else write_png)(path, self.gb.ppu.frame)


# -- the window ---------------------------------------------------------------------


class Frontend:
    """One console in one window. ``pygame`` is imported by :func:`main`."""

    def __init__(
        self, pygame, rom: Path, machine: str, boot: str, scale: int, audio: bool,
        fullscreen: bool, palette: str = "grey",
    ) -> None:  # fmt: skip
        self.pg = pygame
        self.rom, self.machine_name, self.boot, self.palette = rom, machine, boot, palette
        self.console = self._power_on()
        self.scale, self.fullscreen = scale, fullscreen
        self.window = self._open_window()
        self.sound = SoundBuffer()
        self.device = self._open_audio() if audio else None
        self.paused = False
        self.fast = False
        self.controllers: dict[int, object] = {}
        self._frames = 0
        self._fps_since = time.perf_counter()
        self._title()

    def _power_on(self) -> Console:
        console = Console(self.rom, self.machine_name, self.boot)
        header = console.cartridge.header
        print(
            f"machine: {console.machine.name}; {header.title!r}, {header.board}; "
            f"{console.boot_label}",
            file=sys.stderr,
        )
        return console

    def _open_window(self):
        """A window whose surface is the LCD; SDL scales it on the GPU (SCALED) and presents
        it at the display's refresh where it can (vsync)."""
        pg = self.pg
        flags = pg.SCALED | pg.RESIZABLE | (pg.FULLSCREEN if self.fullscreen else 0)
        try:
            surface = pg.display.set_mode((WIDTH, HEIGHT), flags, vsync=1)
        except pg.error:
            surface = pg.display.set_mode((WIDTH, HEIGHT), flags)
        if not self.fullscreen:
            pg.Window.from_display_module().size = (WIDTH * self.scale, HEIGHT * self.scale)
        return surface

    def _open_audio(self):
        from pygame._sdl2.audio import AUDIO_S16, AudioDevice
        from pygame._sdl2.sdl2 import INIT_AUDIO, init_subsystem

        try:
            init_subsystem(INIT_AUDIO)
            device = AudioDevice(
                devicename=None, iscapture=False, frequency=self.console.sample_rate,
                audioformat=AUDIO_S16, numchannels=2, chunksize=512, allowed_changes=0,
                callback=self.sound.fill,
            )  # fmt: skip
        except Exception as error:  # pygame._sdl2's own error type: no sound
            print(f"no sound: {error}", file=sys.stderr)
            return None
        device.pause(0)
        return device

    @property
    def _frame_bytes(self) -> int:
        return int(self.console.sample_rate / RATE) * 4

    def run_frame(self) -> None:
        self._apply_inputs()
        sound = self.console.run_frame()
        if self.device is not None and not self.fast:
            self.sound.push(sound)
        self._frames += 1

    def _apply_inputs(self) -> None:
        pg = self.pg
        keys = pg.key.get_pressed()
        pressed = {
            button for button, names in KEYS if any(keys[getattr(pg, name)] for name in names)
        }
        for controller in self.controllers.values():
            for button, name in PAD_BUTTONS:
                if controller.get_button(getattr(pg, name)):
                    pressed.add(button)
            x = controller.get_axis(pg.CONTROLLER_AXIS_LEFTX) / 32768
            y = controller.get_axis(pg.CONTROLLER_AXIS_LEFTY) / 32768
            for button, held in (("left", x < -0.5), ("right", x > 0.5), ("up", y < -0.5),
                                 ("down", y > 0.5)):  # fmt: skip
                if held:
                    pressed.add(button)
        self.console.press(pressed)

    def _handle(self, event) -> bool:
        """Handle one event; False to quit."""
        pg = self.pg
        if event.type == pg.QUIT:
            return False
        if event.type == pg.CONTROLLERDEVICEADDED:
            controller = pg._sdl2.controller.Controller(event.device_index)
            self.controllers[controller.id] = controller
        elif event.type == pg.CONTROLLERDEVICEREMOVED:
            self.controllers.pop(event.instance_id, None)
        elif event.type == pg.KEYDOWN:
            if event.key == pg.K_ESCAPE:
                return False
            if event.key == pg.K_F3:
                self.paused = not self.paused
                self.sound.clear()
            elif event.key == pg.K_F5:
                self.console.save()
                self.console = self._power_on()
                self.sound.clear()
            elif event.key == pg.K_F11:
                pg.display.toggle_fullscreen()
            elif event.key == pg.K_F12:
                self._screenshot()
            elif event.key == pg.K_TAB:
                self.fast = True
                self.sound.clear()
        elif event.type == pg.KEYUP and event.key == pg.K_TAB:
            self.fast = False
        return True

    def _screenshot(self) -> None:
        folder = Path("screenshots")
        folder.mkdir(exist_ok=True)
        path = folder / f"{self.rom.stem}-{time.strftime('%Y%m%d-%H%M%S')}.png"
        self.console.screenshot(path)
        print(f"saved {path}")

    def draw(self) -> None:
        pg = self.pg
        image = frame_image(self.console.gb.ppu.frame, self.console.cgb, self.palette)
        self.window.blit(pg.image.frombuffer(image, (WIDTH, HEIGHT), "BGRA"), (0, 0))
        pg.display.flip()
        now = time.perf_counter()
        if now - self._fps_since >= 1.0:
            self._title(self._frames / (now - self._fps_since))
            self._frames, self._fps_since = 0, now

    def _title(self, fps: float | None = None) -> None:
        state = " (paused)" if self.paused else " (fast)" if self.fast else ""
        rate = f" — {fps:.1f} fps{state}" if fps is not None else ""
        self.pg.display.set_caption(f"{self.rom.stem}{rate} — gameboy-python")

    def run(self, max_frames: int | None = None, on_frame: Callable | None = None) -> None:
        pg = self.pg
        clock = pg.time.Clock()
        shown = 0
        while True:
            for event in pg.event.get():
                if not self._handle(event):
                    return
            ran = False
            target = BUFFER_FRAMES * self._frame_bytes
            if not self.paused and (self.device is None or len(self.sound) < target):
                for _ in range(4 if self.fast else 1):
                    self.run_frame()
                ran = True
            if ran:
                self.draw()
                shown += 1
                if on_frame is not None:
                    on_frame(self)
                if max_frames is not None and shown >= max_frames:
                    return
            if self.device is None and not self.fast:
                clock.tick_busy_loop(RATE)
            elif not ran:
                time.sleep(0.002)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m gameboy_python play",
        description="Play a Game Boy or Game Boy Color cartridge in a window.",
        epilog=HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("rom", type=Path, help=".gb, .gbc, or a .zip holding one")
    parser.add_argument(
        "--machine",
        choices=["auto", *sorted(MACHINES)],
        default="auto",
        help="the console (default: a Game Boy Color when the cartridge asks for one, else DMG)",
    )
    parser.add_argument(
        "--boot",
        choices=("auto", "real", "skip"),
        default="auto",
        help="auto: your boot ROM when found, else the skip-boot state",
    )
    parser.add_argument(
        "--palette", choices=sorted(PALETTES), default="grey", help="the DMG's four shades"
    )
    parser.add_argument("--scale", type=int, default=4, help="window scale (default 4)")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--fullscreen", action="store_true")
    args = parser.parse_args(argv)
    try:
        import pygame
        import pygame._sdl2.controller
    except ImportError:
        parser.error("the window needs pygame-ce: pip install 'gameboy-python[frontend]'")
    if sys.implementation.name != "pypy":
        print("note: CPython runs this board several times slower than PyPy.", file=sys.stderr)
    # Not pygame.init(): its mixer would take the audio device the frontend opens.
    pygame.display.init()
    pygame._sdl2.controller.init()
    print(HELP)
    frontend = Frontend(
        pygame, args.rom, args.machine, args.boot, max(1, args.scale), not args.no_audio,
        args.fullscreen, args.palette,
    )  # fmt: skip
    try:
        frontend.run()
    finally:
        frontend.console.save()
        pygame.quit()
    return 0
