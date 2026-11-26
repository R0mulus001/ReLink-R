#!/usr/bin/env python3
"""A ReLink-R (or HeyListen) log as numbers: one row per window, medians per scene, the 60 FPS check, and A/B comparisons.

    python -I tools/bench/relink_log.py LOG                      summary: busy windows per scene, medians and ranges
    python -I tools/bench/relink_log.py LOG --rows               every window (vk: every 120 presents; vi: every 5 s)
    python -I tools/bench/relink_log.py LOG --csv out.csv        the vk windows as CSV (--vi-csv for the 5-s windows)
    python -I tools/bench/relink_log.py A B [C ...] --compare    the same scenes side by side (A is the base)
    python -I tools/bench/relink_log.py LOG --gprof              the GPU pass timing blocks (RX_VK_PASS_TIMING=1/2), by kind

Windows:
  vk  every 120 presents (Presentation Thread): draws, passes, GPU ms, the replay's CPU times, barriers, mirror syncs,
      write-backs, and the profiler's per-switch counters.
  vi  every 5 s (the game's presents): FPS, present intervals; with ReLink-R 0.0.12+ (HOS_FRAME_STATS) the frame times by
      millisecond, so the 1 % low, frames over 20 ms and over 50 ms are exact to 1 ms. Older logs have only the coarse
      buckets: their 1 % low is a bound (each frame taken at its bucket's top) and "over 20 ms" counts frames over 22 ms.

Scenes: ReLink-R 0.0.12+ logs the map ("oot: map Market_Child"); a window takes the map last logged before it. Without
map lines a window is "busy" when its frames have at least --min-draws draws (2000: the Market, Lon Lon Ranch), else "light".
A vi window takes the draws of the vk windows that ended inside it.

The 60 FPS acceptance (RELINK-R-60FPS-PLAN.md, section 1), per scene over >= 60 s: every 5-s window >= 59.5 FPS, 1 % low
>= 57 FPS, frames over 20 ms <= 1 per 10 s, no frame over 50 ms.

ReLink-R 0.0.12 (Phase 0 of the 60 FPS plan). No dependencies beyond Python 3.8.
"""
import argparse
import csv
import re
import statistics
import sys

NUM = r"(-?[0-9]+(?:\.[0-9]+)?)"

# ---- line patterns --------------------------------------------------------------------------------------------------
RE_VERSION = re.compile(r"\] (?:Project ReLink|hookshot) (v[^ ]+) \(source ([0-9a-f]+)\)")
RE_ENV = re.compile(r"\] env: (.*)")
RE_MAP = re.compile(r"\] oot: map (?:now )?([A-Za-z0-9_]+)")
RE_UPSCALE = re.compile(r"\] vk: (NVIDIA DLSS|NVIDIA DLAA|AMD FSR native AA|AMD FSR|[A-Za-z0-9 ]+?) draws OoT's upscale: ([0-9]+x[0-9]+) -> ")
RE_NOUPSCALE = re.compile(r"\] vk: no upscaling: the scene is shown as it is drawn, ([0-9]+x[0-9]+) -> ")
RE_TELEPORT = re.compile(r"\] cheats: teleport \S+ to (\S+) at")
RE_PRESENTS = re.compile(r"\] vk: ([0-9]+) presents, " + NUM + r" fps; a frame: " + NUM + r" draws \(" + NUM + r" skipped\), "
                         + NUM + r" dispatches, " + NUM + r" passes, " + NUM + r" barriers, " + NUM + r" submits, " + NUM
                         + r" uploads \(" + NUM + r" MB\), " + NUM + r" ub updates \(" + NUM + r" overlays\), GPU-bound wait "
                         + NUM + r" ms")
RE_REPLAY = re.compile(r"\] vk: a frame's replay time \(ms\): (.*)")
RE_MIRRORS = re.compile(r"\] vk: a frame: mirrors ([0-9]+) \(([0-9]+) MB\): " + NUM + r" MB synced in " + NUM + r" copies, " + NUM
                        + r" MB written back")
RE_FULLB = re.compile(r"\] vk: a frame: " + NUM + r" full barriers recorded, " + NUM + r" left out")
RE_DISPB = re.compile(r"\] vk: a frame: dispatch barriers " + NUM + r" recorded, " + NUM + r" left out")
RE_PASSB = re.compile(r"\] vk: a frame: pass-start barriers " + NUM + r" full, " + NUM + r" fragment stages only")
RE_GAMEB = re.compile(r"\] vk: a frame: the game's barriers: " + NUM + r" fragment stages only, " + NUM + r" full for their flags, "
                      + NUM + r" full for work since the pass")
RE_FLAGS = re.compile(r"\] vk: a frame: the game's barriers by their NVN flags:(.*)")
RE_WHY = re.compile(r"\] vk: a frame: full barriers by reason \(RX_VK_BARRIER_WHY\):(.*)")
RE_MESH = re.compile(r"\] vk: a frame: indirect mesh draws' arguments \(RX_VK_MESH_CONV=[0-9]+\): " + NUM + r" converted one by one, "
                     + NUM + r" from " + NUM + r" batches")
RE_GPU = re.compile(r"\] vk: GPU time " + NUM + r" ms a frame \(the longest submission " + NUM + r" ms\)(.*)")
RE_GPU_UP = re.compile(r"uploads " + NUM + r" ms")
RE_GPU_GAP = re.compile(r"gaps between recordings " + NUM + r" ms(?: \(the longest " + NUM + r"\))?")
RE_GPU_BUSY = re.compile(r"busy " + NUM + r"%")
RE_HL_FULLB = re.compile(r"\] vk: a frame: " + NUM + r" full barriers recorded, " + NUM + r" left out \(nothing recorded since the "
                         r"one before; " + NUM + r" of them inside a parallel replay\)")
RE_VI_FRAMES = re.compile(r"\] vi: ([0-9]+) frames presented \(" + NUM + r" fps over the last " + NUM + r" s")
RE_VI_HIST = re.compile(r"\] vi: present intervals: <15.5 ms ([0-9]+), 15.5-17.8 ([0-9]+), 17.8-22 ([0-9]+), 22-30 ([0-9]+), "
                        r"30-40 ([0-9]+), over 40 ([0-9]+)")
RE_VI_FINE = re.compile(r"\] vi: frame times: .*?; by ms:(.*)")
RE_MSDIFF = re.compile(r"\] vk: mirror syncs' chunk diff \(RX_VK_MSYNC_DIFF=([0-9]), 600 submits, a submit\): " + NUM
                       + r" live pages hashed, .*?; MB: " + NUM + r" copied from snapshots, " + NUM + r" left out, " + NUM
                       + r" copied live; CPU " + NUM + r" ms")
RE_LATE = re.compile(r"\] vk: captures' waits for late pages: ([0-9]+), ([0-9]+) of them cut; the cap now " + NUM
                     + r" ms .*90th percentile " + NUM + r" ms")
RE_SLOW = re.compile(r"\] vk: slow submit: " + NUM + r" ms: (.*)")
RE_GPROF_HEAD = re.compile(r"\] vk: GPU pass timing, ([0-9]+) presents")
RE_GPROF_ALL = re.compile(r"\] vk:   " + NUM + r" ms a frame in all")
RE_GPROF_REC = re.compile(r"\] vk:   recordings' command buffers: " + NUM + r" ms from the first timestamp to the last in " + NUM
                          + r" a frame \(" + NUM + r" ms in spans, " + NUM + r" ms between")
RE_GPROF_UPL = re.compile(r"\] vk:   upload command buffers: " + NUM + r" ms in " + NUM + r" a frame \(" + NUM + r" ms in spans")
RE_GPROF_KIND = re.compile(r"\] vk:     ([mu]) (\S+)\s+" + NUM + r" ms\s+" + NUM + r"%\s+" + NUM + r" spans\s+" + NUM + r" items\s+"
                           + NUM + r" MB")
RE_GPROF_ROW = re.compile(r"\] vk:   ([mu]) +" + NUM + r" ms +" + NUM + r" x +" + NUM + r" us +" + NUM + r" items +" + NUM + r" MB  (.*)")
RE_GPROF_PROG = re.compile(r"\] vk:   +" + NUM + r" ms +" + NUM + r" runs +" + NUM + r" us a run +" + NUM + r" draws +" + NUM
                           + r" us a draw +prog ([0-9a-f]+)")

REPLAY_KEYS = ("submit", "present", "draw", "descriptors", "texture lookups", "uploads", "pipelines", "programs", "commands",
               "dispatch", "memory sync", "queue submit", "slot wait")
COARSE_TOPS = (15.5, 17.8, 22.0, 30.0, 40.0, 100.0)   # (a coarse bucket's top, ms: the 1 % low bound of old logs)


def flt(s):
    return float(s)


def parse_pairs(text, sep=":"):
    """' 0x1: 4.8; 0x12: 69.7;' -> {'0x1': 4.8, ...}; ' 12.5 barrier (why);' (sep None) -> {'barrier (why)': 12.5}"""
    out = {}
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        if sep:
            k, _, v = part.rpartition(sep)
            try:
                out[k.strip()] = float(v)
            except ValueError:
                pass
        else:
            v, _, k = part.partition(" ")
            try:
                out[k.strip()] = float(v)
            except ValueError:
                pass
    return out


class Log:
    def __init__(self, path, min_draws=2000, by_upscaler=True):
        self.path = path
        self.version = "?"
        self.env = ""
        self.vk = []        # vk windows (dicts)
        self.vi = []        # vi windows (dicts)
        self.late = []      # late-page reports
        self.slow = []      # slow submits (ms, map)
        self.gprof = []     # pass timing blocks
        self.maps_seen = []
        self.min_draws = min_draws
        self.by_upscaler = by_upscaler
        self._parse()

    def _parse(self):
        cur_map = None
        cur_up = None        # (the upscaler and its input size, as last logged)
        msdiff = None        # (the last chunk diff report: per submit)
        pend = {}            # (lines before a vk window's "presents" line: replay time, mirrors)
        win = None           # (the open vk window, closed by its "GPU time" line)
        vi = None
        vk_since_vi = []
        gp = None
        line_no = 0
        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line_no += 1
                m = RE_VERSION.search(line)
                if m and self.version == "?":
                    self.version = m.group(1) + " " + m.group(2)
                    continue
                m = RE_ENV.search(line)
                if m and not self.env:
                    self.env = m.group(1).strip()
                    continue
                m = RE_MAP.search(line)
                if m:
                    cur_map = m.group(1)
                    if not self.maps_seen or self.maps_seen[-1] != cur_map:
                        self.maps_seen.append(cur_map)
                    continue
                m = RE_UPSCALE.search(line)
                if m:
                    cur_up = "%s %s" % ({"NVIDIA DLSS": "DLSS", "NVIDIA DLAA": "DLAA", "AMD FSR native AA": "FSR-AA",
                                         "AMD FSR": "FSR"}.get(m.group(1), m.group(1)), m.group(2))
                    continue
                m = RE_NOUPSCALE.search(line)
                if m:
                    cur_up = "native " + m.group(1)
                    continue
                m = RE_REPLAY.search(line)
                if m:
                    d = {}
                    for part in m.group(1).split(","):
                        k, _, v = part.strip().rpartition(" ")
                        try:
                            d[k] = float(v)
                        except ValueError:
                            pass
                    pend["replay"] = d
                    continue
                m = RE_MIRRORS.search(line)
                if m:
                    pend["mirrors"] = dict(mirrors=int(m.group(1)), mirror_mb=int(m.group(2)), msync_mb=flt(m.group(3)),
                                           msync_copies=flt(m.group(4)), wb_mb=flt(m.group(5)))
                    continue
                m = RE_PRESENTS.search(line)
                if m:
                    g = m.groups()
                    win = dict(line=line_no, map=cur_map, upscaler=cur_up, presents=int(g[0]), fps=flt(g[1]), draws=flt(g[2]), skipped=flt(g[3]),
                               dispatches=flt(g[4]), passes=flt(g[5]), game_barriers=flt(g[6]), submits=flt(g[7]),
                               uploads=flt(g[8]), upload_mb=flt(g[9]), gpu_bound_wait=flt(g[12]))
                    for k, v in pend.get("replay", {}).items():
                        win["cpu_" + k.replace(" ", "_")] = v
                    win.update(pend.get("mirrors", {}))
                    if msdiff:   # (ReLink-R 0.0.13: the chunk diff's last report, a submit -> a frame)
                        k = win["submits"] or 6
                        win["msdiff_mode"] = msdiff[0]
                        win["msdiff_snap_mb"], win["msdiff_skip_mb"], win["msdiff_live_mb"], win["msdiff_cpu_ms"] = (
                            msdiff[1] * k, msdiff[2] * k, msdiff[3] * k, msdiff[4] * k)
                    pend = {}
                    continue
                if win is not None:
                    m = RE_HL_FULLB.search(line) or RE_FULLB.search(line)
                    if m:
                        win["full_barriers"], win["full_left_out"] = flt(m.group(1)), flt(m.group(2))
                        continue
                    m = RE_DISPB.search(line)
                    if m:
                        win["disp_barriers"], win["disp_left_out"] = flt(m.group(1)), flt(m.group(2))
                        continue
                    m = RE_PASSB.search(line)
                    if m:
                        win["pass_start_full"], win["pass_start_frag"] = flt(m.group(1)), flt(m.group(2))
                        continue
                    m = RE_GAMEB.search(line)
                    if m:
                        win["game_frag"], win["game_full_flags"], win["game_full_work"] = map(flt, m.groups())
                        continue
                    m = RE_MESH.search(line)
                    if m:
                        win["mesh_one_by_one"], win["mesh_batched"], win["mesh_batches"] = map(flt, m.groups())
                        continue
                    m = RE_FLAGS.search(line)
                    if m:
                        win["flags"] = parse_pairs(m.group(1))
                        continue
                    m = RE_WHY.search(line)
                    if m:
                        win["why"] = parse_pairs(m.group(1), sep=None)
                        continue
                    m = RE_GPU.search(line)
                    if m:
                        win["gpu_ms"], win["gpu_longest"] = flt(m.group(1)), flt(m.group(2))
                        rest = m.group(3)
                        u = RE_GPU_UP.search(rest)
                        if u:
                            win["gpu_upload_ms"] = flt(u.group(1))
                        g2 = RE_GPU_GAP.search(rest)
                        if g2:
                            win["gpu_gap_ms"] = flt(g2.group(1))
                            if g2.group(2):
                                win["gpu_gap_longest"] = flt(g2.group(2))
                        b = RE_GPU_BUSY.search(rest)
                        if b:
                            win["gpu_busy_pct"] = flt(b.group(1))
                        win["slow_submits"] = sum(1 for s in self.slow if s["line"] > (self.vk[-1]["line"] if self.vk else 0))
                        self.vk.append(win)
                        vk_since_vi.append(win)
                        win = None
                        continue
                m = RE_VI_FRAMES.search(line)
                if m:
                    vi = dict(line=line_no, map=cur_map, upscaler=cur_up, frames_total=int(m.group(1)), fps=flt(m.group(2)), secs=flt(m.group(3)))
                    continue
                m = RE_VI_HIST.search(line)
                if m and vi is not None:
                    vi["coarse"] = [int(x) for x in m.groups()]
                    ws = vk_since_vi or self.vk[-1:]
                    vi["draws"] = statistics.mean(w["draws"] for w in ws) if ws else 0.0
                    vi["gpu_ms"] = statistics.mean(w.get("gpu_ms", 0) for w in ws) if ws else 0.0
                    vk_since_vi = []
                    self.vi.append(vi)
                    continue
                m = RE_VI_FINE.search(line)
                if m and self.vi:
                    fine = {}
                    for part in m.group(1).split():
                        k, _, v = part.partition(":")
                        k = 100 if k.startswith("100") else int(k)
                        fine[k] = fine.get(k, 0) + int(v)
                    self.vi[-1]["fine"] = fine
                    continue
                m = RE_MSDIFF.search(line)
                if m:
                    msdiff = (int(m.group(1)), flt(m.group(3)), flt(m.group(4)), flt(m.group(5)), flt(m.group(6)))
                    continue
                m = RE_LATE.search(line)
                if m:
                    self.late.append(dict(line=line_no, map=cur_map, waits=int(m.group(1)), cut=int(m.group(2)), cap=flt(m.group(3)),
                                          p90=flt(m.group(4))))
                    continue
                m = RE_SLOW.search(line)
                if m:
                    self.slow.append(dict(line=line_no, map=cur_map, ms=flt(m.group(1)), what=m.group(2).strip()))
                    continue
                m = RE_GPROF_HEAD.search(line)
                if m:
                    gp = dict(line=line_no, map=cur_map, presents=int(m.group(1)), kinds={}, rows=[], progs=[],
                              draws=self.vk[-1]["draws"] if self.vk else 0)
                    self.gprof.append(gp)
                    continue
                if gp is not None:
                    m = RE_GPROF_ALL.search(line)
                    if m:
                        gp["all_ms"] = flt(m.group(1))
                        continue
                    m = RE_GPROF_REC.search(line)
                    if m:
                        gp["rec_ms"], gp["rec_n"], gp["rec_spans_ms"], gp["rec_glue_ms"] = map(flt, m.groups())
                        continue
                    m = RE_GPROF_UPL.search(line)
                    if m:
                        gp["up_ms"], gp["up_n"], gp["up_spans_ms"] = map(flt, m.groups())
                        continue
                    m = RE_GPROF_KIND.search(line)
                    if m:
                        gp["kinds"][m.group(1) + " " + m.group(2)] = dict(ms=flt(m.group(3)), pct=flt(m.group(4)),
                                                                          spans=flt(m.group(5)), items=flt(m.group(6)),
                                                                          mb=flt(m.group(7)))
                        continue
                    m = RE_GPROF_ROW.search(line)
                    if m:
                        gp["rows"].append(dict(cb=m.group(1), ms=flt(m.group(2)), n=flt(m.group(3)), us=flt(m.group(4)),
                                               items=flt(m.group(5)), mb=flt(m.group(6)), label=m.group(7).strip()))
                        continue
                    m = RE_GPROF_PROG.search(line)
                    if m:
                        gp["progs"].append(dict(ms=flt(m.group(1)), runs=flt(m.group(2)), draws=flt(m.group(4)), prog=m.group(6)))
                        continue

    # ---- scenes ---------------------------------------------------------------------------------------------------------
    def scene_of(self, w):
        s = w["map"] if w.get("map") else "busy" if w.get("draws", 0) >= self.min_draws else "light"
        if s != "light" and self.by_upscaler and w.get("upscaler"):
            s += " | " + w["upscaler"]
        return s

    def scenes(self):
        order = []
        for w in self.vk + self.vi:
            s = self.scene_of(w)
            if s not in order:
                order.append(s)
        return order


# ---- statistics -----------------------------------------------------------------------------------------------------------
def med(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def rng(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    return vals[0], vals[-1]


def frame_stats(vis):
    """The scene's frames from its vi windows: (frames, seconds, 1 % low fps, over 20 ms, over 50 ms, exact)"""
    secs = sum(v["secs"] for v in vis)
    exact = all("fine" in v for v in vis) and bool(vis)
    if exact:
        bins = {}
        for v in vis:
            for k, n in v["fine"].items():
                bins[k] = bins.get(k, 0) + n
        n = sum(bins.values())
        if not n:
            return 0, secs, None, 0, 0, True
        cut, acc, p99 = n * 0.01, 0, None
        for k in sorted(bins, reverse=True):
            acc += bins[k]
            if acc >= cut:
                p99 = k + 1.0   # (the bin's top: frame times are floored to the ms)
                break
        over20 = sum(c for k, c in bins.items() if k >= 20)
        over50 = sum(c for k, c in bins.items() if k >= 50)
        return n, secs, 1000.0 / p99, over20, over50, True
    hist = [0] * 6
    for v in vis:
        for i, c in enumerate(v.get("coarse", [0] * 6)):
            hist[i] += c
    n = sum(hist)
    if not n:
        return 0, secs, None, 0, 0, False
    cut, acc, p99 = n * 0.01, 0, None
    for i in range(5, -1, -1):
        acc += hist[i]
        if acc >= cut:
            p99 = COARSE_TOPS[i]
            break
    over20 = hist[3] + hist[4] + hist[5]   # (over 22 ms: the coarse buckets' nearest edge)
    over50 = None                          # (unknown: the top bucket is "over 40")
    return n, secs, 1000.0 / p99, over20, over50, False


def acceptance(vis):
    """The plan's section 1 for one scene's vi windows: a list of (test, value, passed)"""
    n, secs, low, o20, o50, exact = frame_stats(vis)
    out = []
    if not vis:
        return out
    worst = min(v["fps"] for v in vis)
    out.append(("every 5-s window >= 59.5 FPS", "lowest %.1f" % worst, worst >= 59.5))
    out.append(("1 %% low >= 57 FPS%s" % ("" if exact else " (bound: coarse buckets)"), "%.1f" % low if low else "-",
                bool(low and low >= 57)))
    per10 = o20 / secs * 10 if secs else 0
    out.append(("frames over 20 ms <= 1 per 10 s%s" % ("" if exact else " (counted over 22 ms)"),
                "%d in %.0f s = %.1f per 10 s" % (o20, secs, per10), per10 <= 1))
    if o50 is None:
        out.append(("no frame over 50 ms", "unknown (old log: 'over 40' %d)" % sum(v["coarse"][5] for v in vis), False))
    else:
        out.append(("no frame over 50 ms", "%d" % o50, o50 == 0))
    out.append((">= 60 s of play", "%.0f s" % secs, secs >= 60))
    return out


# ---- output -----------------------------------------------------------------------------------------------------------------
VK_COLS = [("fps", "FPS (vk)"), ("draws", "draws"), ("passes", "passes"), ("dispatches", "dispatches"), ("gpu_ms", "GPU ms"),
           ("gpu_upload_ms", "GPU uploads ms"), ("gpu_gap_ms", "GPU idle (gaps) ms"), ("gpu_busy_pct", "GPU busy %"), ("gpu_longest", "longest submission ms"),
           ("cpu_submit", "CPU submit ms"), ("cpu_memory_sync", "of it memory sync"), ("cpu_draw", "CPU draw ms"),
           ("full_barriers", "full barriers"), ("full_left_out", "full left out"), ("disp_barriers", "dispatch barriers"),
           ("pass_start_full", "pass-start full"), ("game_barriers", "game barriers"), ("game_frag", "game frag-only"),
           ("msync_mb", "msync MB"), ("msdiff_snap_mb", "diff: MB from snapshots"),
           ("msdiff_skip_mb", "diff: MB left out"), ("msdiff_live_mb", "diff: MB live"), ("msdiff_cpu_ms", "diff: CPU ms"), ("msync_copies", "msync copies"), ("wb_mb", "write-back MB"), ("uploads", "uploads"),
           ("upload_mb", "upload MB"), ("mesh_one_by_one", "mesh conv 1-by-1"), ("mesh_batched", "mesh conv batched"),
           ("slow_submits", "slow submits")]


def fmt(v, nd=1):
    if v is None:
        return "-"
    if isinstance(v, tuple):
        return "%s-%s" % (fmt(v[0], nd), fmt(v[1], nd))
    if abs(v) >= 100:
        return "%.0f" % v
    return ("%%.%df" % nd) % v


def scene_vk(log, scene):
    return [w for w in log.vk if log.scene_of(w) == scene]


def scene_vi(log, scene):
    return [w for w in log.vi if log.scene_of(w) == scene]


def summary(log, args):
    print("== %s" % log.path)
    print("   build %s; env: %s" % (log.version, log.env or "-"))
    if log.maps_seen:
        print("   maps in order: %s" % " -> ".join(log.maps_seen))
    print("   %d vk windows (120 presents), %d vi windows (5 s), %d slow submits, %d pass timing blocks" %
          (len(log.vk), len(log.vi), len(log.slow), len(log.gprof)))
    for scene in log.scenes():
        if scene == "light" and not args.all:
            continue
        vks, vis = scene_vk(log, scene), scene_vi(log, scene)
        print("\n-- scene %s: %d vk windows, %d vi windows (%.0f s)" % (scene, len(vks), len(vis), sum(v["secs"] for v in vis)))
        if vis:
            n, secs, low, o20, o50, exact = frame_stats(vis)
            print("   FPS (5-s windows) median %s, range %s; 1%% low %s%s; frames over 20 ms %s%s; over 50 ms %s" %
                  (fmt(med([v["fps"] for v in vis])), fmt(rng([v["fps"] for v in vis])), fmt(low),
                   "" if exact else " (bound)", o20, "" if exact else " (>22 ms)", "-" if o50 is None else o50))
        for k, name in VK_COLS:
            vals = [w.get(k) for w in vks]
            if all(v is None for v in vals):
                continue
            print("   %-24s median %8s   range %s" % (name, fmt(med(vals)), fmt(rng(vals))))
        flags = {}
        for w in vks:
            for k, v in w.get("flags", {}).items():
                flags.setdefault(k, []).append(v)
        if flags:
            print("   game barriers by NVN flags (median a frame): " +
                  ", ".join("%s %s" % (k, fmt(med(v))) for k, v in sorted(flags.items(), key=lambda kv: -med(kv[1]))))
        why = {}
        for w in vks:
            for k, v in w.get("why", {}).items():
                why.setdefault(k, []).append(v)
        if why:
            print("   full barriers by reason (median a frame):")
            for k, v in sorted(why.items(), key=lambda kv: -med(kv[1]))[:12]:
                print("     %7s  %s" % (fmt(med(v)), k))
        if vis:
            print("   60 FPS acceptance (plan section 1):")
            for test, val, ok in acceptance(vis):
                print("     [%s] %-46s %s" % ("pass" if ok else "FAIL", test, val))
    if log.late:
        last = log.late[-1]
        print("\n   late-page waits (captures): %d so far, %d cut; 90th percentile %s ms; cap %s ms" %
              (last["waits"], last["cut"], fmt(last["p90"]), fmt(last["cap"])))
    if log.slow:
        busy = [s for s in log.slow if s["ms"] >= 10]
        print("   slow submits: %d (%d of 10 ms or more; the longest %s ms)" % (len(log.slow), len(busy), fmt(max(s["ms"] for s in log.slow))))
    print()


def rows(log, args):
    print("vk windows:  line  scene  " + "  ".join(name for _, name in VK_COLS[:12]))
    for w in log.vk:
        if not args.all and w["draws"] < args.min_draws and not w.get("map"):
            continue
        print("  %6d %-14s " % (w["line"], log.scene_of(w)) + "  ".join(fmt(w.get(k)) for k, _ in VK_COLS[:12]))
    print("\nvi windows:  line  scene  fps  secs  draws  coarse(<15.5,-17.8,-22,-30,-40,>40)  fine")
    for v in log.vi:
        if not args.all and v["draws"] < args.min_draws and not v.get("map"):
            continue
        fine = v.get("fine")
        print("  %6d %-14s %5.1f %4.1f %6.0f  %s  %s" % (v["line"], log.scene_of(v), v["fps"], v["secs"], v["draws"],
                                                        v.get("coarse"), " ".join("%d:%d" % kv for kv in sorted(fine.items())) if fine else ""))


def write_csv(path, recs):
    keys = []
    for r in recs:
        for k, v in r.items():
            if not isinstance(v, (dict, list)) and k not in keys:
                keys.append(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in recs:
            w.writerow(r)
    print("wrote %d rows to %s" % (len(recs), path))


def compare(logs, args):
    base = logs[0]
    scenes = []
    for lg in logs:
        for s in lg.scenes():
            if s not in scenes and (not s.startswith("light") or args.all):
                scenes.append(s)
    names = ["%s (%s)" % (chr(65 + i), lg.version.split()[0]) for i, lg in enumerate(logs)]
    for i, lg in enumerate(logs):
        print("%s = %s" % (names[i], lg.path))
    for scene in scenes:
        print("\n== scene %s (medians of its windows; range in brackets; B-A as %% of A)" % scene)
        head = "  %-24s" % "" + "".join("%-24s" % n for n in names)
        print(head)

        def line(label, getter, nd=1):
            cells, meds = [], []
            for lg in logs:
                vals = getter(lg)
                m = med(vals)
                meds.append(m)
                r = rng(vals)
                cells.append("%s [%s]" % (fmt(m, nd), fmt(r, nd)) if m is not None else "-")
            extra = ""
            if meds[0] not in (None, 0) and len(meds) > 1 and all(m is not None for m in meds[1:]):
                extra = "  " + " ".join("%+.1f%%" % ((m - meds[0]) / meds[0] * 100) for m in meds[1:])
            print("  %-24s" % label + "".join("%-24s" % c for c in cells) + extra)

        line("FPS (5-s windows)", lambda lg: [v["fps"] for v in scene_vi(lg, scene)])
        for k, name in VK_COLS:
            if all(all(w.get(k) is None for w in scene_vk(lg, scene)) for lg in logs):
                continue
            line(name, lambda lg, k=k: [w.get(k) for w in scene_vk(lg, scene)])
        cells = []
        for lg in logs:
            vis = scene_vi(lg, scene)
            n, secs, low, o20, o50, exact = frame_stats(vis)
            cells.append("%s low, %s>20/%s>50%s" % (fmt(low), o20, "-" if o50 is None else o50, "" if exact else "~"))
        print("  %-24s" % "1% low, long frames" + "".join("%-24s" % c for c in cells))


def gprof_out(log, args):
    if not log.gprof:
        print("%s: no GPU pass timing blocks (run with RX_VK_PASS_TIMING=1 or 2 in relink_env.txt)" % log.path)
        return
    for gp in log.gprof:
        if not args.all and gp["draws"] < args.min_draws and not gp.get("map"):
            continue
        print("== pass timing at line %d (scene %s, %.0f draws a frame): all %s ms, recordings %s (spans %s, glue %s), uploads %s" %
              (gp["line"], gp.get("map") or ("busy" if gp["draws"] >= args.min_draws else "light"), gp["draws"],
               fmt(gp.get("all_ms"), 2), fmt(gp.get("rec_ms"), 2), fmt(gp.get("rec_spans_ms"), 2), fmt(gp.get("rec_glue_ms"), 2),
               fmt(gp.get("up_ms"), 2)))
        for k, d in sorted(gp["kinds"].items(), key=lambda kv: -kv[1]["ms"]):
            print("   %-14s %7.3f ms  %5.1f%%  %7.1f spans  %7.2f MB" % (k, d["ms"], d["pct"], d["spans"], d["mb"]))
        for r in gp["rows"][:args.top]:
            print("   %s %7.3f ms %6.1f x %8.1f us  %s" % (r["cb"], r["ms"], r["n"], r["us"], r["label"][:110]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--compare", action="store_true", help="the logs side by side, the first as the base")
    ap.add_argument("--rows", action="store_true", help="every window")
    ap.add_argument("--csv", help="the vk windows as CSV")
    ap.add_argument("--vi-csv", help="the 5-s windows as CSV")
    ap.add_argument("--gprof", action="store_true", help="the GPU pass timing blocks")
    ap.add_argument("--min-draws", type=float, default=2000, help="a window is busy from this many draws a frame (2000)")
    ap.add_argument("--all", action="store_true", help="light windows too")
    ap.add_argument("--no-upscaler", action="store_true", help="scenes not split by the upscaler in use")
    ap.add_argument("--top", type=int, default=15, help="pass timing rows shown (15)")
    args = ap.parse_args(argv)
    logs = [Log(p, args.min_draws, not args.no_upscaler) for p in args.logs]
    if args.compare or len(logs) > 1:
        compare(logs, args)
        return 0
    lg = logs[0]
    if args.csv:
        write_csv(args.csv, lg.vk)
    if args.vi_csv:
        write_csv(args.vi_csv, lg.vi)
    if args.rows:
        rows(lg, args)
    elif args.gprof:
        gprof_out(lg, args)
    elif not args.csv and not args.vi_csv:
        summary(lg, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
