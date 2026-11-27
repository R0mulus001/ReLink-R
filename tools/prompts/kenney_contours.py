"""(ReLink-R 0.0.14, a developer's tool: not run by a player's build) Kenney's keyboard and mouse glyphs as contours, for the
keyboard button prompts (nx2/button_glyphs.py, family "keyboard").

A player's build has no font library (the builder's Python carries zstandard, numpy and the lifter's packages, not fontTools),
so the outlines are read here once, with fontTools, and written as plain data: nx2/keyboard_glyphs.py, standard library only.
The font is Kenney's Input Prompts 1.5 Keyboard & Mouse (CC0: third_party/kenney_input_keyboard/License.txt), the same release
Hookshot (b2456c66, #2435) and HeyListen (433c43a0) take their keyboard face from; the key table is theirs (nx2/keyboard_keys.py).

    toolchain/fontvenv/Scripts/python.exe -I tools/prompts/kenney_contours.py   (from the repository's root)
"""
import os
import sys

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "nx2"))
import keyboard_keys  # noqa: E402

FONT = os.path.join(ROOT, "third_party", "kenney_input_keyboard", "kenney_input_keyboard_&_mouse.otf")
OUT = os.path.join(ROOT, "nx2", "keyboard_glyphs.py")


class Segments(BasePen):
    """the outline as button_glyphs.py's contours: lists of ("L", p0, p1) and ("C", p0, c1, c2, p3), integer font units"""

    def __init__(self, glyphset):
        super().__init__(glyphset)
        self.contours = []
        self.cur = None
        self.start = None

    def _moveTo(self, p):
        self.contours.append([])
        self.cur = self.start = (round(p[0]), round(p[1]))

    def _lineTo(self, p):
        q = (round(p[0]), round(p[1]))
        if q != self.cur:
            self.contours[-1].append(("L", self.cur, q))
            self.cur = q

    def _curveToOne(self, c1, c2, p):
        q = (round(p[0]), round(p[1]))
        self.contours[-1].append(("C", self.cur, (round(c1[0]), round(c1[1])), (round(c2[0]), round(c2[1])), q))
        self.cur = q

    def _closePath(self):
        if self.cur != self.start:
            self.contours[-1].append(("L", self.cur, self.start))
        self.cur = self.start

    _endPath = _closePath


def main():
    font = TTFont(FONT)
    gs = font.getGlyphSet()
    upem = font["head"].unitsPerEm
    names = sorted({keyboard_keys.kenney_name(c) for c in keyboard_keys.KEYS} | {keyboard_keys.kenney_name(-1)})
    out = {}
    for n in names:
        if n not in gs:
            print("kenney_contours: no glyph %s in the font (left out: its keys show the ANY key)" % n)
            continue
        pen = Segments(gs)
        gs[n].draw(pen)
        out[n] = (gs[n].width, [c for c in pen.contours if c])
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write('"""(ReLink-R 0.0.14, made by tools/prompts/kenney_contours.py: do not edit) The outlines of Kenney\'s Input Prompts 1.5\n'
                'Keyboard & Mouse glyphs (CC0: third_party/kenney_input_keyboard/License.txt) the keyboard button prompts use, as\n'
                'nx2/button_glyphs.py contours: name -> (advance, [contour, ...]); a contour is a list of ("L", p0, p1) and\n'
                '("C", p0, c1, c2, p3), in font units of UPEM."""\n')
        f.write("UPEM = %d\n" % upem)
        f.write("GLYPHS = {\n")
        for n in sorted(out):
            w, cs = out[n]
            f.write("    %r: (%d, %r),\n" % (n, w, cs))
        f.write("}\n")
    print("kenney_contours: %d glyphs, UPEM %d -> %s (%d KB)" % (len(out), upem, OUT, os.path.getsize(OUT) // 1024))


if __name__ == "__main__":
    main()
