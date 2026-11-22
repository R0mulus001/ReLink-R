"""The texture heap's compaction told to the host before each texture it moves, Ocarina of Time 1.1.1: C added after one
instruction of the game (a64_lift.py Lifter.after), right before each of the round's copies.

The compaction thread (aglTextureDataMgr::Compaction, entry f_807da3f0, the round's steps f_807dbd60, f_807dbf90 and
f_807db4a0) moves a texture by copying its storage to the new place with the CPU, then makes the texture again there. On the
console the storage holds a texture's texels whoever wrote them. Here a texture the GPU drew (the terrain's tiles: 260 x 260
normal maps and their neighbours) has its texels in the renderer's image only, so the copy carried whatever the memory held
and the texture made at the new place was uploaded from that: the ground turned to stripes after some minutes of play, in
every room of the map, until the map was loaded again (issues 47 and 72).

Each copy is either memcpy(x0 = to, x1 = from, x2 = size) or, when the manager has a copier object (+0x90), its first
virtual function (x0 = the object, x1 = to, x2 = from, x3 = size). After the last instruction that sets the arguments of
each, hos_tex_moving(from, size, to) (host/oot_tex_compact.c) has the renderer write what the GPU drew in [from, from + size)
back into that memory first, as it does before virtual pages are remapped.

Each site's original word is checked: another game version leaves it out (and says so).
"""

MAIN = 0x80020000   # (main's base in this image: nx2/eden_image.py)

ADD_X1_X8_X9 = 0x8b090101
LDR_X2_X27_28 = 0xf9401762
LDR_X2_X26_28 = 0xf9401742
LDR_X10_X10 = 0xf940014a
LDR_X8_X8 = 0xf9400108

DECL = "extern void hos_tex_moving(uint64_t, uint64_t, uint64_t); "
MEMCPY = "{ " + DECL + "hos_tex_moving(c->x[1], c->x[2], c->x[0]); }   /* (nx2/oot_tex_move.py: a texture about to be moved) */"
COPIER = "{ " + DECL + "hos_tex_moving(c->x[2], c->x[3], c->x[1]); }   /* (nx2/oot_tex_move.py: a texture about to be moved) */"

# (the offset in main of the instruction before the call, its word, the text)
SITES = [
    (0x7bc2fc, ADD_X1_X8_X9, MEMCPY),    # f_807dbf90: bl memcpy at +0x7bc300
    (0x7bc67c, LDR_X2_X27_28, MEMCPY),   # f_807dbf90: bl memcpy at +0x7bc680
    (0x7bb6a8, LDR_X2_X26_28, MEMCPY),   # f_807db4a0: bl memcpy at +0x7bb6ac
    (0x7bbe48, ADD_X1_X8_X9, MEMCPY),    # f_807dbd60: bl memcpy at +0x7bbe4c
    (0x7bc2dc, LDR_X10_X10, COPIER),     # f_807dbf90: blr x10 at +0x7bc2e0
    (0x7bc660, LDR_X8_X8, COPIER),       # f_807dbf90: blr x8 at +0x7bc664
    (0x7bb678, LDR_X8_X8, COPIER),       # f_807db4a0: blr x8 at +0x7bb67c
    (0x7bbf70, LDR_X10_X10, COPIER),     # f_807dbd60: blr x10 at +0x7bbf74
]


def install(lifter, img):
    """The sites into lifter.after, all or none: a site whose word differs (another game version) leaves the change out"""
    for off, word, _ in SITES:
        pc = MAIN + off
        try:
            have = img.word(pc)
        except Exception:
            have = None
        if have != word:
            print("texture moves told to the renderer: main+%#x holds %s, not %08x: left out" % (
                off, "?" if have is None else "%08x" % have, word))
            return 0
    for off, _, text in SITES:
        pc = MAIN + off
        lifter.after[pc] = (lifter.after[pc] + "\n" if pc in lifter.after else "") + text
    print("texture moves told to the renderer: %d of %d sites" % (len(SITES), len(SITES)))
    return len(SITES)
