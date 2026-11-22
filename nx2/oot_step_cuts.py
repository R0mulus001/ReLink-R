"""The game's other whole-step counters above 60 fps for Ocarina of Time 1.1.1: C added after single instructions of the game
(a64_lift.py Lifter.after), the same way nx2/oot_ripples.py does the water. With the frame rate unlocked the frame's step is
its real length (nx2/oot_step_rate.py), under 1 above 60 fps, and every place that cuts it to a whole number gave 0 and froze:

- the pick-up counter above Link's head (f_80a87e50, main+0xa68300 fcvtzs w12, s0): the count it shows moves toward the new
  total by (int)(step * max(distance / 50, 1)) and fades only when they meet; at 0 it stayed up until a door or a talk;
- the time of day (f_803edf70, main+0x3cdfc0 fcvtzs w8, s0): each frame adds (int)(2 * step) game seconds at
  the clock's +60; at 0 the sun stood still, between 60 and 120 fps the day ran slow;
- the Deku Tree's floor web (f_80652cb0, main+0x632d00 fcvtzs w22, s0): the elapsed time over 1/60 cut to simulation steps,
  clamped to 0..3 right after; at 0 the web did not react when Link jumped on it;
- the physics solver's step count (f_838ceb80 main+0x38aebf4, f_838cfc10 main+0x38afd20, fcvtzs w1, s0, into the solver's
  +712): (int)(step * steps of a 60 fps frame + 0.001), cut short and changing from frame to frame under a step of 1, so a
  moving platform slid out from under Link;
- the sound manager's job (f_80435300, its phase in w2): hands the step to the sound engine, whose fades, delays and ramps
  count updates of at least one whole step; fed less, voices were not released when an area unloaded and the voice budget
  filled until new sounds and the music stopped.

The counters (pick-up, clock, web) put the value the game cut into the register again, from a remainder kept per object
(host/nn_vi.c hos_whole_steps: each site has its own keys, the object in x19, and its own HOS_<NAME>_CUT=1 switch). The solver
count is rounded up instead (hos_solver_steps), and the sound job runs at 60 Hz (hos_sound_gate at its head, which returns
from the job while a whole step has not built up, and hos_sound_step after its load of the step, which hands the engine 1).
All of it only while the host's real-time step runs above 60 fps (hos_step_fps); at 60 fps and under the game's own code runs.

Each site's original word is checked: another game version leaves it out (and says so). The sound job's two edits go in
together or not at all.
"""

MAIN = 0x80020000   # (main's base in this image: nx2/eden_image.py)

DECL_STEP = "extern volatile int hos_step_fps; "
WHOLE_DECL = "extern uint32_t hos_whole_steps(uint32_t, uint64_t, uint32_t, uint32_t); "


def whole(site, reg, key_note):
    """The text after a cut into x<reg>: the count from the remainder kept per object (x19), the game's value as the fallback"""
    return ("{ " + DECL_STEP + WHOLE_DECL +
            "if (hos_step_fps > 60) c->x[%d] = hos_whole_steps(%d, c->x[19], (uint32_t)(c->vreg[0][0] & 0xffffffffu), "
            "(uint32_t)c->x[%d]); }   /* (nx2/oot_step_cuts.py: %s above 60 fps) */" % (reg, site, reg, key_note))


FCVTZS_W12_S0 = 0x1e38000c
FCVTZS_W8_S0 = 0x1e380008
FCVTZS_W22_S0 = 0x1e380016
FCVTZS_W1_S0 = 0x1e380001

# (what, the cut's offset in main, its word, the text; the site numbers are hos_whole_steps's: 1 pick-up, 2 clock, 3 web)
COUNTERS = [
    ("pick-up counter above 60 fps", 0xa68300, FCVTZS_W12_S0, whole(1, 12, "the pick-up counter")),
    ("time of day above 60 fps", 0x3cdfc0, FCVTZS_W8_S0, whole(2, 8, "the time of day")),
    ("Deku Tree web above 60 fps", 0x632d00, FCVTZS_W22_S0, whole(3, 22, "the Deku Tree's web")),
]

SOLVER_TEXT = ("{ " + DECL_STEP + "extern uint32_t hos_solver_steps(uint32_t, uint32_t, uint32_t); "
               "if (hos_step_fps > 60) c->x[1] = hos_solver_steps((uint32_t)c->x[1], (uint32_t)c->vreg[0][0], "
               "(uint32_t)c->vreg[1][0]); }   /* (nx2/oot_step_cuts.py: the solver's steps rounded up above 60 fps) */")
# (vreg 0: the float the game cut, step * steps a 60 fps frame + 0.001; vreg 1: the steps a 60 fps frame, as a float)
SOLVERS = [0x38aebf4, 0x38afd20]

# The sound job: its head (a hint, as a function's first word; the phase is in w2) and the load of the step (ldr s0, [x8, #16]
# at +0x34) after the chain from the sound manager's pointer (adrp x8 at +0x24, ldr x8 at +0x2c and +0x30). The head asks the
# host whether to run: in phase 0 it reads the same step the job loads further down, the other phases follow phase 0's choice.
SOUND = 0x415300
SOUND_WORDS = [(SOUND, 0xd503237f), (SOUND + 0x24, 0xb0024348), (SOUND + 0x2c, 0xf9444908), (SOUND + 0x30, 0xf9400108),
               (SOUND + 0x34, 0xbd401100)]
SOUND_HEAD = ("{ extern int hos_sound_gate(uint32_t, uint32_t); const uint32_t _ph = (uint32_t)c->x[2]; uint32_t _st = 0; "
              "if (_ph == 0) { const uint64_t _o = recomp_load64(c, recomp_load64(c, g_module_base + 0x80435000ULL + "
              "(int64_t)75927552 + 2192) + 0); _st = (uint32_t)recomp_load32(c, _o + 16); } "
              "if (!hos_sound_gate(_ph, _st)) return; }   /* (nx2/oot_step_cuts.py: the sound job at 60 Hz above 60 fps) */")
SOUND_STEP = ("{ extern uint32_t hos_sound_step(uint32_t); a64_vset64(c->vreg[0], hos_sound_step((uint32_t)(c->vreg[0][0] "
              "& 0xffffffffu))); }   /* (nx2/oot_step_cuts.py: a whole step for the sound engine) */")


def _have(img, off):
    try:
        return img.word(MAIN + off)
    except Exception:
        return None


def _put(lifter, off, text):
    pc = MAIN + off
    if pc in lifter.after:
        lifter.after[pc] += "\n" + text
    else:
        lifter.after[pc] = text


def _checked(img, what, wants):
    """True when every (offset, word) is there; says what is out of place otherwise"""
    for off, want in wants:
        have = _have(img, off)
        if have != want:
            print("%s: main+%#x holds %s, not %08x: left out" % (what, off, "?" if have is None else "%08x" % have, want))
            return False
    return True


def install(lifter, img):
    """The sites into lifter.after, each left out when its word differs (another game version); the number of sites put"""
    n = 0
    for what, off, word, text in COUNTERS:
        if _checked(img, what, [(off, word)]):
            _put(lifter, off, text)
            print("%s: 1 of 1 site" % what)
            n += 1
    ok = [off for off in SOLVERS if _checked(img, "physics solver steps above 60 fps", [(off, FCVTZS_W1_S0)])]
    for off in ok:
        _put(lifter, off, SOLVER_TEXT)
    print("physics solver steps above 60 fps: %d of %d sites" % (len(ok), len(SOLVERS)))
    n += len(ok)
    if _checked(img, "sound job above 60 fps", SOUND_WORDS):
        _put(lifter, SOUND, SOUND_HEAD)
        _put(lifter, SOUND + 0x34, SOUND_STEP)
        print("sound job above 60 fps: 2 of 2 edits")
        n += 2
    return n


def sites():
    """{the change: [the guest addresses whose instruction it checks]} for lift.py's exefs_sites"""
    return {what: [MAIN + off] for what, off, _, _ in COUNTERS} | {
        "physics solver steps above 60 fps": [MAIN + o for o in SOLVERS],
        "sound job above 60 fps": [MAIN + o for o, _ in SOUND_WORDS]}
