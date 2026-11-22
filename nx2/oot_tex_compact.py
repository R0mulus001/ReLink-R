"""The texture heap's compaction asked for once in a while, Ocarina of Time 1.1.1: C added after one instruction of the game
(a64_lift.py Lifter.after).

The texture data manager's per-frame step (f_80797240) asks the heap's compaction thread for a round whenever none runs and its
flag bit 1 (+960, set once at its setup) is on: it loads the flag byte (ldrb w8, [x19, #960], main+0x777274) and tests bit 1.
Every texture a round moves is made again at its new address, which the renderer sees as a new texture (uploads, descriptors,
sync: 3 to 5 ms in a crowded place such as the market).

Right after that load, when bit 1 is set and the host says no (host/oot_tex_compact.c, once every HOS_TEX_COMPACT_MS), the bit
is cleared in w8, so the step's own test skips the request. w8 is not read after the test (the step loads it again), and the
flag in memory is left as it is. A round that has begun still finishes: the request is the only thing spaced out.

The site's original word is checked: another game version leaves it out (and says so).
"""

MAIN = 0x80020000   # (main's base in this image: nx2/eden_image.py)
SITE = 0x777274
LDRB_W8_X19_960 = 0x394f0268
TEXT = ("{ extern int hos_tex_compact_due(void); "
        "if (((c->x[8] >> 1) & 1) && !hos_tex_compact_due()) c->x[8] &= ~2ULL; }"
        "   /* (nx2/oot_tex_compact.py: the texture heap's compaction once in a while) */")


def install(lifter, img):
    """The site into lifter.after; left out when its word differs (another game version)"""
    pc = MAIN + SITE
    try:
        have = img.word(pc)
    except Exception:
        have = None
    if have != LDRB_W8_X19_960:
        print("texture heap compaction: main+%#x holds %s, not %08x: left out" % (
            SITE, "?" if have is None else "%08x" % have, LDRB_W8_X19_960))
        return 0
    if pc in lifter.after:
        lifter.after[pc] += "\n" + TEXT
    else:
        lifter.after[pc] = TEXT
    print("texture heap compaction: 1 of 1 site")
    return 1
