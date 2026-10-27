"""The text on an image, from the optical character recognition built into Windows.

``Windows.Media.Ocr`` (through pywinrt) reads offline and needs nothing beyond Windows' own English
language features, which a Windows 10 or 11 computer set up in English has. It reads one image at a
time; the words come back with their boxes, which ``parse`` uses to tell the rows of a panel apart.

Every call runs on one thread of its own, which joins the Windows Runtime's multithreaded apartment
once and lives as long as the app: the engine is never touched from a thread that has not joined it.
"""
from __future__ import annotations

import asyncio
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

#: The language the game's text is read in: the names are matched against English catalogs.
LANGUAGE = "en-US"
#: How long one read may take before the caller stops waiting for it
TIMEOUT_S = 60.0

_LOCK = threading.Lock()
_POOL: ThreadPoolExecutor | None = None
_JOINED = False


class Unavailable(RuntimeError):
    """Text recognition cannot run on this computer; the message says why, for the player."""


@dataclass(frozen=True)
class Word:
    text: str
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class Line:
    """One line of text as the engine grouped it: its words left to right."""
    words: tuple[Word, ...]

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    @property
    def x(self) -> float:
        return min(word.x for word in self.words)

    @property
    def y(self) -> float:
        return min(word.y for word in self.words)

    @property
    def right(self) -> float:
        return max(word.x + word.w for word in self.words)

    @property
    def bottom(self) -> float:
        return max(word.y + word.h for word in self.words)

    @property
    def h(self) -> float:
        return self.bottom - self.y

    @property
    def cy(self) -> float:
        return (self.y + self.bottom) / 2


def line(*words: Word) -> Line:
    return Line(tuple(words))


def scaled(lines: list[Line], factor: float) -> list[Line]:
    """The lines with every box multiplied by ``factor``: boxes read on a resized copy, put back on
    the picture it was made from."""
    return [Line(tuple(Word(w.text, w.x * factor, w.y * factor, w.w * factor, w.h * factor) for w in found.words))
            for found in lines]


def _on_thread(work, *args):
    global _POOL
    if sys.platform != "win32":
        raise Unavailable("Reading the game screen uses the text recognition built into Windows, so it works on Windows only.")
    with _LOCK:
        if _POOL is None:
            _POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="screenread-ocr")
        pool = _POOL
    return pool.submit(work, *args).result(TIMEOUT_S)


def _engine():
    """The engine, on the OCR thread."""
    global _JOINED
    try:
        from winrt.runtime import ApartmentType, init_apartment
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine
    except ImportError as err:          # a copy of the app built without it
        raise Unavailable(f"This copy of the app has no Windows text recognition ({err}).") from None
    if not _JOINED:
        try:
            init_apartment(ApartmentType.MULTI_THREADED)
        except Exception:  # noqa: BLE001 - pywinrt joined it when it was imported
            pass
        _JOINED = True
    engine = None
    try:
        if OcrEngine.is_language_supported(Language(LANGUAGE)):
            engine = OcrEngine.try_create_from_language(Language(LANGUAGE))
    except Exception:  # noqa: BLE001 - an unexpected language tag: use the profile's languages below
        engine = None
    engine = engine or OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise Unavailable("Windows has no text recognition installed for English. Add English (United States) in Settings → "
                          "Time & language → Language & region, with its optical character recognition feature.")
    return engine


def _language() -> str:
    return str(_engine().recognizer_language.language_tag)


def available() -> tuple[bool, str]:
    """``(True, the engine's language)`` when text can be read on this computer, else ``(False, why)``."""
    try:
        return True, _on_thread(_language)
    except Unavailable as err:
        return False, str(err)
    except Exception as err:  # noqa: BLE001 - the runtime itself failed: say so rather than fail the page
        return False, f"Windows text recognition could not start ({type(err).__name__}: {err})."


async def _result(operation):
    return await operation


def _recognize(image) -> list[Line]:
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter
    engine = _engine()
    picture = image.convert("RGBA")
    limit = int(OcrEngine.max_image_dimension or 0) or max(picture.size)   # a static property of the class
    scale = min(1.0, limit / max(picture.size))
    if scale < 1.0:
        picture = picture.resize((max(1, int(picture.width * scale)), max(1, int(picture.height * scale))))
    writer = DataWriter()
    writer.write_bytes(picture.tobytes())
    bitmap = SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), BitmapPixelFormat.RGBA8,
                                                    picture.width, picture.height)
    result = asyncio.run(_result(engine.recognize_async(bitmap)))
    lines = []
    for found in result.lines:
        words = []
        for word in found.words:
            box = word.bounding_rect
            words.append(Word(word.text, box.x / scale, box.y / scale, box.width / scale, box.height / scale))
        if words:
            lines.append(Line(tuple(words)))
    return lines


def recognize(image) -> list[Line]:
    """The lines of text on a PIL image, with word boxes in the image's own pixels. An image larger than
    the engine reads is scaled down first and the boxes scaled back."""
    return _on_thread(_recognize, image)


#: the pywinrt modules a read imports, directly or from inside the others (the packaged app must carry them all)
MODULES = ("winrt.runtime", "winrt.system", "winrt.windows.foundation", "winrt.windows.foundation.collections",
           "winrt.windows.globalization", "winrt.windows.graphics.imaging", "winrt.windows.media.ocr",
           "winrt.windows.storage.streams")


def self_check() -> str:
    """The packaged app's smoke test: every module a read uses imports and, when this Windows has an English
    engine, a picture of known words reads back. Raises when either fails."""
    import importlib
    for name in MODULES:
        importlib.import_module(name)
    ready, why = available()
    if not ready:
        return f"modules OK; this Windows has no engine to read with ({why})"
    from PIL import Image, ImageDraw, ImageFont
    try:
        font, scale = ImageFont.load_default(size=48), 1
    except TypeError:                   # Pillow before 10.1: the small bitmap font, drawn and enlarged
        font, scale = ImageFont.load_default(), 4
    picture = Image.new("RGB", (900 // scale, 160 // scale), (12, 16, 28))
    ImageDraw.Draw(picture).text((24 // scale, 48 // scale), "Fera Insight Lv. 8", fill=(232, 224, 200), font=font)
    if scale > 1:
        picture = picture.resize((900, 160))
    text = " ".join(found.text for found in recognize(picture))
    if "insight" not in text.lower():
        raise RuntimeError(f"the engine read {text!r} from a picture of 'Fera Insight Lv. 8'")
    return f"OK ({why}: read {text!r})"
