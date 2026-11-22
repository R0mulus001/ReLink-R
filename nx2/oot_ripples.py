"""The water's ripples above 60 fps for Ocarina of Time 1.1.1: C added after one instruction of the game (a64_lift.py
Lifter.after). Issue 120: "weird ripples on the water surface" with the frame rate unlocked (the reporter's log: 69 fps,
the real-time step's ratio 0.857).

The water renderer (main+0x472e0, f_800672e0) runs its ripple simulation a whole number of times a frame: the frame's step
(the float at the surface's +0, 1.0 at 60 fps) cut to an integer (fcvtzs w9, s0 at main+0x475f8), times the surface's
substeps (+76). With the frame rate unlocked the step is the frame's real length (nx2/oot_step_rate.py), under 1 above 60
fps: cut to 0 at every frame, the rings Link and the actors make in water stood still, or moved now and then.

Right after the cut, while the step follows the real frame rate (hos_step_fps set), the count is replaced by the whole steps
of a remainder kept per surface (the object in x19 the substeps are read from): host/nn_vi.c hos_ripple_steps. Each surface
then runs its 60 steps a second whatever the frame rate. At 60 fps and under the game's own cut is kept.

The site's original word is checked: another game version leaves it out (and says so).
"""

MAIN = 0x80020000   # (main's base in this image: nx2/eden_image.py)
SITE = 0x475f8
FCVTZS_W9_S0 = 0x1e380009
TEXT = ("{ extern volatile int hos_step_fps; extern uint32_t hos_ripple_steps(uint64_t, uint32_t); "
        "if (hos_step_fps > 60) c->x[9] = hos_ripple_steps(c->x[19], (uint32_t)(c->vreg[0][0] & 0xffffffffu)); }"
        "   /* (nx2/oot_ripples.py: the ripples above 60 fps) */")


def install(lifter, img):
    """The site into lifter.after; left out when its word differs (another game version)"""
    pc = MAIN + SITE
    try:
        have = img.word(pc)
    except Exception:
        have = None
    if have != FCVTZS_W9_S0:
        print("water ripples above 60 fps: main+%#x holds %s, not %08x: left out" % (
            SITE, "?" if have is None else "%08x" % have, FCVTZS_W9_S0))
        return 0
    if pc in lifter.after:
        lifter.after[pc] += "\n" + TEXT
    else:
        lifter.after[pc] = TEXT
    print("water ripples above 60 fps: 1 of 1 site")
    return 1
