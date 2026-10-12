"""Font resolution and text measurement.

The layout engine needs two things from a font: an *accurate width* for
measurement, and an *actual embeddable face* for drawing. Those are the same
object in PyMuPDF, so this module hands out a single :class:`FontFace` per
(family, bold, italic) role and everything else measures against it.

Why not base-14 everywhere? PDF core fonts cannot draw ``₦`` (naira), ``₹``
(rupee) or ``→``. Money and contact details must survive a round-trip, so when a
real TrueType file is available we use it. Core fonts remain as the last-resort
fallback, and any glyph they cannot draw is recorded and rendered with a readable
text equivalent where one exists.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pymupdf


HERE = Path(__file__).resolve().parent
BUNDLED_FONT_DIR = HERE.parent / "assets" / "fonts"

_GLYPH_FALLBACKS = {
    "₦": "NGN ",
    "₹": "INR ",
    "€": "EUR ",
    "£": "GBP ",
    "¥": "JPY ",
    "→": "->",
    "←": "<-",
    "•": "*",
    "·": "*",
    "–": "-",
    "—": "-",
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
}


# ---------------------------------------------------------------------------
# family -> candidate TrueType filenames (regular, bold, italic, bolditalic)
# ---------------------------------------------------------------------------

_FAMILY_FILES: Dict[str, Tuple[str, ...]] = {
    "arial": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "helvetica": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "segoeui": ("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"),
    "calibri": ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
    "times": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    "timesnewroman": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    "georgia": ("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
    "verdana": ("verdana.ttf", "verdanab.ttf", "verdanai.ttf", "verdanaz.ttf"),
    "tahoma": ("tahoma.ttf", "tahomabd.ttf"),
    "cambria": ("cambria.ttc", "cambriab.ttf", "cambriai.ttf"),
    "garamond": ("gara.ttf", "garabd.ttf", "garait.ttf"),
    "courier": ("cour.ttf", "courbd.ttf", "couri.ttf", "courbi.ttf"),
    "consolas": ("consola.ttf", "consolab.ttf", "consolai.ttf", "consolaz.ttf"),
}

#: Base-14 PostScript names used when no TrueType file can be found.
_BASE14: Dict[str, Tuple[str, ...]] = {
    "helvetica": ("helv", "hebo", "heit", "hebi"),
    "arial": ("helv", "hebo", "heit", "hebi"),
    "segoeui": ("helv", "hebo", "heit", "hebi"),
    "calibri": ("helv", "hebo", "heit", "hebi"),
    "verdana": ("helv", "hebo", "heit", "hebi"),
    "tahoma": ("helv", "hebo", "heit", "hebi"),
    "garamond": ("tiro", "tibo", "tiit", "tibi"),
    "times": ("tiro", "tibo", "tiit", "tibi"),
    "timesnewroman": ("tiro", "tibo", "tiit", "tibi"),
    "georgia": ("tiro", "tibo", "tiit", "tibi"),
    "cambria": ("tiro", "tibo", "tiit", "tibi"),
    "courier": ("cour", "cobo", "coit", "cobi"),
    "consolas": ("cour", "cobo", "coit", "cobi"),
}


def _font_search_dirs() -> List[Path]:
    dirs: List[Path] = [BUNDLED_FONT_DIR]
    if os.name == "nt":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        dirs.append(Path(windir) / "Fonts")
        dirs.append(Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts")
    else:
        dirs += [
            Path("/System/Library/Fonts"),
            Path("/Library/Fonts"),
            Path.home() / "Library" / "Fonts",
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".fonts",
            Path.home() / ".local" / "share" / "fonts",
        ]
    return [d for d in dirs if str(d) and d.exists()]


def normalize_family(name: str) -> str:
    key = (name or "").strip().lower().replace(" ", "").replace("-", "")
    if key in _FAMILY_FILES:
        return key
    for known in _FAMILY_FILES:
        if known in key:
            return known
    return ""


@dataclass
class FontFace:
    """An embeddable face plus the metrics needed to lay text out."""

    display: str
    family: str
    bold: bool
    italic: bool
    fontfile: Optional[str] = None
    base14: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    _font: Optional[pymupdf.Font] = field(default=None, repr=False)
    _missing: Dict[str, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self._font is None:
            self._font = self._load()

    # -- loading -----------------------------------------------------------
    def _load(self) -> pymupdf.Font:
        if self.fontfile:
            try:
                return pymupdf.Font(fontfile=self.fontfile)
            except Exception:
                pass
        if self.base14:
            try:
                return pymupdf.Font(fontname=self.base14)
            except Exception:
                pass
        return pymupdf.Font(fontname="helv")

    # -- metrics -----------------------------------------------------------
    def text_length(self, text: str, size: float) -> float:
        if not text:
            return 0.0
        try:
            safe_text = "".join(
                ch if self.has_glyph(ch) else _GLYPH_FALLBACKS.get(ch, "?")
                for ch in text
            )
            return float(self._font.text_length(safe_text, fontsize=size))
        except Exception:
            return len(text) * size * 0.5

    @property
    def ascender(self) -> float:
        return float(getattr(self._font, "ascender", 0.8))

    @property
    def descender(self) -> float:
        return float(getattr(self._font, "descender", -0.2))

    def has_glyph(self, ch: str) -> bool:
        try:
            return bool(self._font.has_glyph(ord(ch)))
        except Exception:
            return True

    def sanitize(self, text: str) -> str:
        """Replace unsupported glyphs with readable text, recording each one.

        Unknown glyphs remain visibly marked with ``?`` rather than disappearing.
        """
        out_chars: List[str] = []
        for ch in text:
            if ch in ("\n", "\t", "\r") or self.has_glyph(ch):
                out_chars.append(ch)
            else:
                self._missing[ch] = self._missing.get(ch, 0) + 1
                out_chars.append(_GLYPH_FALLBACKS.get(ch, "?"))
        return "".join(out_chars)

    def missing_glyphs(self) -> Dict[str, int]:
        return dict(self._missing)

    @property
    def draw_name(self) -> str:
        """Name to hand to ``insert_font`` / ``insert_text``."""
        return self.base14 or "F0"


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


class FontRegistry:
    """Resolves and caches faces for the duration of one render."""

    def __init__(self) -> None:
        self._cache: Dict[Tuple[str, bool, bool], FontFace] = {}
        self._dirs = _font_search_dirs()
        self._embedded: Dict[str, FontFace] = {}

    def resolve(self, family: str, bold: bool = False, italic: bool = False) -> FontFace:
        key = ((family or "").strip().lower(), bool(bold), bool(italic))
        if key in self._cache:
            return self._cache[key]

        fam_key = normalize_family(family) or "helvetica"
        face = self._from_ttf(fam_key, family, bold, italic)
        if face is None:
            base = _BASE14.get(fam_key, _BASE14["helvetica"])
            idx = (1 if bold else 0) + (2 if italic else 0)
            face = FontFace(
                display=family or "Helvetica",
                family=fam_key,
                bold=bold,
                italic=italic,
                base14=base[idx],
            )
        self._cache[key] = face
        return face

    def _from_ttf(self, fam_key: str, display: str, bold: bool, italic: bool) -> Optional[FontFace]:
        files = _FAMILY_FILES.get(fam_key, ())
        if not files:
            return None
        idx = (1 if bold else 0) + (2 if italic else 0)
        # Prefer the exact weight; fall back to regular rather than nothing.
        order = [idx, 0] if idx else [0]
        for i in order:
            if i >= len(files):
                continue
            name = files[i]
            path = self._find(name)
            if path:
                label = {0: "Regular", 1: "Bold", 2: "Italic", 3: "Bold Italic"}[idx]
                return FontFace(
                    display=f"{display or fam_key.title()} {label}".strip(),
                    family=fam_key,
                    bold=bold,
                    italic=italic,
                    fontfile=str(path),
                )
        return None

    def _find(self, filename: str) -> Optional[Path]:
        for d in self._dirs:
            candidate = d / filename
            if candidate.exists():
                return candidate
        return None

    # -- embedding for drawing --------------------------------------------
    def register(self, page: "pymupdf.Page", face: FontFace) -> str:
        """Insert the face into a page and return the draw-time font name.

        The name is cached per file so every page refers to the same font
        resource, but the resource is inserted on each page that draws with it,
        because a PDF page carries its own font table.
        """
        if face.base14:
            return face.base14
        if face.fontfile is None:
            return "helv"
        name = self._embedded.get(face.fontfile)
        if name is None:
            name = f"QGF{len(self._embedded)}"
            self._embedded[face.fontfile] = name
        page.insert_font(fontname=name, fontfile=face.fontfile)
        return name


# ---------------------------------------------------------------------------
# wrapping / measurement
# ---------------------------------------------------------------------------


def wrap_text(text: str, face: FontFace, size: float, width: float) -> List[str]:
    """Greedy word wrap that never drops a word.

    A single word wider than ``width`` is hard-split by character so nothing can
    overflow the column even for unbroken URLs or reference numbers.
    """
    if not text:
        return []
    width = max(width, 1.0)
    lines: List[str] = []
    for hard_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if hard_line == "":
            lines.append("")
            continue
        words = hard_line.split(" ")
        current = ""
        for word in words:
            candidate = word if not current else current + " " + word
            if face.text_length(candidate, size) <= width:
                current = candidate
                continue

            if current:
                lines.append(current)
                current = ""

            if face.text_length(word, size) <= width:
                current = word
                continue

            chunk = ""
            for ch in word:
                if face.text_length(chunk + ch, size) <= width or not chunk:
                    chunk += ch
                else:
                    lines.append(chunk)
                    chunk = ch
            current = chunk
        lines.append(current)
    return lines or [""]


def measure_text(
    text: str,
    face: FontFace,
    size: float,
    width: float,
    line_height: float,
) -> Tuple[List[str], float]:
    """Return the wrapped lines and the height they occupy."""
    lines = wrap_text(text, face, size, width)
    return lines, max(len(lines), 1) * line_height * size
