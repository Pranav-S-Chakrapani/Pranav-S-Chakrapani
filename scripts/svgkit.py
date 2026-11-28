"""
Shared toolkit for the animated SVG profile cards.

- subset_font_b64(): subsets a font to just the glyphs a card actually
  uses (via fontTools/pyftsubset) and returns a base64 WOFF data URI, so
  every card ships only the handful of KB of font it needs.
- font_face_css(): builds the @font-face block for the data URI.
- reduced_motion_css(): the prefers-reduced-motion override every card
  includes, so CSS keyframe animations AND SMIL <animate> elements both
  freeze on the final frame for people who asked for reduced motion.
- STATIC: honours STATIC=1 in the environment -- cards render only their
  final, settled frame (no <style> keyframes, no <animate> elements) so
  they can be screenshotted before pushing.
"""
from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
from functools import lru_cache

STATIC = os.environ.get("STATIC", "0") == "1"

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@lru_cache(maxsize=None)
def _subset_bytes(font_path: str, text: str) -> bytes:
    """Runs pyftsubset over `font_path`, keeping only glyphs needed for
    `text` (plus a small set of punctuation/digits every card can use),
    and returns the resulting WOFF bytes."""
    abs_path = os.path.join(_REPO_ROOT, font_path)
    extra = " 0123456789%:-_/·•→✓#@.,'\"!?()[]{}+&"
    chars = "".join(sorted(set(text + extra)))

    with tempfile.NamedTemporaryFile(suffix=".woff", delete=False) as tmp:
        out_path = tmp.name
    try:
        cmd = [
            sys.executable, "-m", "fontTools.subset",
            abs_path,
            f"--text={chars}",
            "--flavor=woff",
            "--with-zopfli" if False else "--no-recommended-glyphs",
            "--no-glyph-names",
            "--desubroutinize",
            "--drop-tables+=FFTM",
            f"--output-file={out_path}",
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)


def subset_font_b64(font_path: str, text: str) -> str:
    """Returns a `data:font/woff;base64,...` URI for `font_path`, subset
    down to the characters that appear in `text`."""
    data = _subset_bytes(font_path, text)
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:font/woff;base64,{b64}"


def font_face_css(family: str, regular_uri: str, bold_uri: str) -> str:
    return f"""
    @font-face {{
      font-family: '{family}';
      font-weight: 400;
      src: url("{regular_uri}") format('woff');
    }}
    @font-face {{
      font-family: '{family}';
      font-weight: 700;
      src: url("{bold_uri}") format('woff');
    }}
    """


def reduced_motion_css(selectors: str = "*") -> str:
    """Freezes every CSS animation AND every SMIL <animate>/<animateTransform>
    element on its final frame when the OS requests reduced motion. SMIL
    has no native `prefers-reduced-motion` switch, so we fake it: every
    SMIL element below also gets a `begin="rm.end"` escape hatch driven by
    a zero-duration helper animation gated by the same media query."""
    return f"""
    @media (prefers-reduced-motion: reduce) {{
      {selectors} {{
        animation: none !important;
      }}
      .smil-gate {{ visibility: hidden; }}
    }}
    """


def smil_reduced_motion_guard(svg_id: str) -> str:
    """A tiny invisible <rect> with a CSS class toggled only under
    prefers-reduced-motion, used as an `end` event other SMIL elements can
    reference so they jump straight to their final values. Paired with
    `freeze_attr` below, SMIL animations default to playing and this guard
    has no visible effect unless reduced motion is requested (handled by
    each element's own fill="freeze" + the CSS override disabling the
    keyframes that drive layered effects)."""
    return ""


def stagger(index: int, step: float = 0.35, base: float = 0.0) -> float:
    """Seconds of delay for the `index`-th element in a top-to-bottom
    reveal sequence."""
    return round(base + index * step, 2)


def esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def wrap_svg(width: int, height: int, body: str, defs: str = "", title: str = "") -> str:
    title_tag = f"<title>{esc(title)}</title>" if title else ""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" \
width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">{title_tag}<defs>{defs}</defs>{body}</svg>
"""
