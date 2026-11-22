"""nx2/oot_step_cuts.py: each site is taken only when the game's own instruction is there (the sound job's two edits together
or not at all), its text joins what another change already put after the same instruction, and the host's helper names are
the ones the texts call.

    python -I -B nx2/test_step_cuts.py
"""
import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oot_step_cuts as sc  # noqa: E402


class Image:
    def __init__(self, words):
        self.words = words

    def word(self, pc):
        return self.words[pc]   # (KeyError outside the image, as a real image raises)


class Lifter:
    def __init__(self):
        self.after = {}


def quiet(fn, *a):
    with redirect_stdout(io.StringIO()) as out:
        r = fn(*a)
    return r, out.getvalue()


def full_image():
    words = {sc.MAIN + off: w for _, off, w, _ in sc.COUNTERS}
    words.update({sc.MAIN + off: 0x1e380001 for off in sc.SOLVERS})
    words.update({sc.MAIN + off: w for off, w in sc.SOUND_WORDS})
    return words


def main():
    # (the addresses the lifted code shows: label counts from f_80a87e50, f_803edf70, f_80652cb0, f_838ceb80, f_838cfc10)
    assert [sc.MAIN + o for _, o, _, _ in sc.COUNTERS] == [0x80a88300, 0x803edfc0, 0x80652d00]
    assert [sc.MAIN + o for o in sc.SOLVERS] == [0x838cebf4, 0x838cfd20]
    assert sc.MAIN + sc.SOUND == 0x80435300 and sc.MAIN + sc.SOUND + 0x34 == 0x80435334
    # (FCVTZS Wd, Sn = 0x1e380000 | n << 5 | d)
    assert [w for _, _, w, _ in sc.COUNTERS] == [0x1e380000 | 0 << 5 | d for d in (12, 8, 22)]

    lifter = Lifter()
    n, said = quiet(sc.install, lifter, Image(full_image()))
    assert n == 3 + 2 + 2, (n, said)
    assert "2 of 2 sites" in said and "2 of 2 edits" in said, said
    for what, off, _, text in sc.COUNTERS:
        t = lifter.after[sc.MAIN + off]
        assert t == text and "hos_step_fps > 60" in t and "hos_whole_steps(" in t and "c->x[19]" in t, t
    # (each counter has its own site number: its keys and switch)
    assert [t.count("hos_whole_steps(%d," % i) for i, t in enumerate([c[3] for c in sc.COUNTERS], 1)] == [1, 1, 1]
    for off in sc.SOLVERS:
        assert "hos_solver_steps" in lifter.after[sc.MAIN + off] and "hos_step_fps > 60" in lifter.after[sc.MAIN + off]
    head, step = lifter.after[sc.MAIN + sc.SOUND], lifter.after[sc.MAIN + sc.SOUND + 0x34]
    assert "hos_sound_gate" in head and "return;" in head and "hos_sound_step" in step and "a64_vset64(c->vreg[0]" in step

    # (the host defines every helper the texts call)
    here = os.path.dirname(os.path.abspath(__file__))
    host = open(os.path.join(here, "..", "host", "nn_vi.c"), encoding="utf-8").read()
    for name in ("hos_whole_steps", "hos_solver_steps", "hos_sound_gate", "hos_sound_step"):
        assert "\n%s %s(" % ("int" if name == "hos_sound_gate" else "uint32_t", name) in host, name
    for env in ("HOS_PICKUP_CUT", "HOS_CLOCK_CUT", "HOS_WEB_CUT", "HOS_SOLVER_CUT", "HOS_SOUND_CUT"):
        assert '"%s"' % env in host, env

    # (text already after the same instruction stays, ours follows)
    lifter = Lifter()
    pc = sc.MAIN + sc.COUNTERS[1][1]
    lifter.after[pc] = "/* earlier */"
    quiet(sc.install, lifter, Image(full_image()))
    assert lifter.after[pc].startswith("/* earlier */\n") and "hos_whole_steps" in lifter.after[pc]

    # (another game version: one site's word differs: only that one is left out; a sound word differs: neither edit)
    words = full_image()
    words[sc.MAIN + sc.COUNTERS[0][1]] = 0xd503201f
    words[sc.MAIN + sc.SOLVERS[1]] = 0xd503201f
    lifter = Lifter()
    n, said = quiet(sc.install, lifter, Image(words))
    assert n == 2 + 1 + 2 and "left out" in said and "1 of 2 sites" in said, (n, said)
    assert sc.MAIN + sc.COUNTERS[0][1] not in lifter.after and sc.MAIN + sc.SOLVERS[1] not in lifter.after
    words = full_image()
    words[sc.MAIN + sc.SOUND + 0x34] = 0xd503201f
    lifter = Lifter()
    n, said = quiet(sc.install, lifter, Image(words))
    assert n == 5 and sc.MAIN + sc.SOUND not in lifter.after and sc.MAIN + sc.SOUND + 0x34 not in lifter.after, (n, said)
    r, said = quiet(sc.install, Lifter(), Image({}))
    assert r == 0 and "left out" in said, said

    # (the checked addresses lift.py hands the exefs mods check)
    s = sc.sites()
    assert sc.MAIN + sc.SOUND in s["sound job above 60 fps"] and len(s["physics solver steps above 60 fps"]) == 2
    print("ok: oot_step_cuts (6 cases)")


if __name__ == "__main__":
    main()
