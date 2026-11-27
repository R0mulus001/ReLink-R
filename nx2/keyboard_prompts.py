"""(ReLink-R 0.0.14) Keyboard button prompts: the game's External font with a glyph for each key, made at every build from the
player's own RomFS, beside the Xbox and PlayStation fonts (nx2/button_glyphs.py make calls make below; a failure here leaves
those as they are).

Ported in idea from Hookshot's keyboard face (b2456c66, #2435, J; co-authored by Needicla and Claude Opus 5.5) and HeyListen's
(433c43a0, f11cb284), GPL-3.0, and written for ReLink-R's own prompt fonts: the game's font decoded, Kenney's key glyphs added
(nx2/keyboard_glyphs.py, CC0, drawn into the box of the game's face-button glyphs), and the twelve Switch-button code points
(U+E040...) left on one glyph each that host/prompts.c points at the key bound to that button (relink_options.ini key_<button>).

The font is longer than the game's, and the game drops a file longer than its entry in the resource size table: so the table
is written too, with that entry raised (Hookshot nx2/prompt_assets.py size_table, #2592's idea), and the host serves it when
it serves this font.

    prompts/keyboard.otf     the font (plain OpenType, CFF)
    prompts/keyboard.txt     what the host needs to patch and wrap it (see write_sidecar)
    prompts/rsizetable.zs    the game's resource size table with the font's entry raised (a zstd frame of raw blocks)
"""
import hashlib
import math
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import button_glyphs as bg  # noqa: E402
import keyboard_glyphs  # noqa: E402
import keyboard_keys as kk  # noqa: E402
import wheel_assets as pa  # noqa: E402

KEY_HEIGHT = 1.0   # (a key's height against the box of the game's face-button glyph: the same)

# ReLink-R's default first key of each Switch button (host/nn_hid.c key_default; the order of bg.SWITCH): the glyph each slot
# holds as written, before the host points it at the bindings
DEFAULT_KEY = {"A": 0x45, "B": 0x10, "X": 0x20, "Y": 0x01, "L": 0x51, "R": 0x52, "ZL": 0x5A, "ZR": 0x58, "Plus": 0x09,
               "Minus": 0x4D, "LS": 0x11, "RS": 0x43}


def key_contours(name, box, face_adv):
    """Kenney's glyph name scaled to the height of box (x0, y0, x1, y1), the game's face-button glyph's ink, and centred
    on it; a key wider than that ink (Space, Shift, the mouse) gets a wider advance with the same bearings on both sides:
    (contours, advance, bbox)"""
    _, cs = keyboard_glyphs.GLYPHS[name]
    kb = bg.bbox(cs)
    s = (box[3] - box[1]) * KEY_HEIGHT / max(kb[3] - kb[1], 1)
    cy = (box[1] + box[3]) / 2
    kcx, kcy = (kb[0] + kb[2]) / 2, (kb[1] + kb[3]) / 2
    width = (kb[2] - kb[0]) * s
    bearing = max(box[0], 0)
    adv = max(face_adv, round(width + 2 * bearing))
    cx = (box[0] + box[2]) / 2 if adv == face_adv else adv / 2
    out = bg.transform(cs, lambda p: ((p[0] - kcx) * s + cx, (p[1] - kcy) * s + cy))
    return out, adv, bg.bbox(out)


def build(orig):
    """the keyboard font and where its patchable parts are: (bytes, info)"""
    dirs = bg.tables(orig)
    t = {tag: orig[o:o + ln] for tag, _, o, ln in dirs}
    for tag in ("CFF ", "cmap", "head", "hhea", "hmtx", "maxp"):
        if tag not in t:
            raise bg.Unfit(f"External has no {tag.strip()} table")
    num_glyphs, = struct.unpack_from(">H", t["maxp"], 4)
    nh, = struct.unpack_from(">H", t["hhea"], 34)
    metrics = []
    for g in range(num_glyphs):
        aw = struct.unpack_from(">H", t["hmtx"], 4 * min(g, nh - 1))[0]
        lsb = struct.unpack_from(">h", t["hmtx"], 4 * g + 2 if g < nh else 4 * nh + 2 * (g - nh))[0]
        metrics.append((aw, lsb))
    keep = max(bg.all_glyphs(t["cmap"])) + 1
    _, before, _ = bg.rebuild_cmap(t["cmap"], {cp: 0 for _, cp, _ in bg.SWITCH})
    switch_glyph = {name: before[cp] for name, cp, _ in bg.SWITCH}
    advances = {}
    for name, _, cls in bg.SWITCH:
        advances.setdefault(cls, metrics[switch_glyph[name]][0])
    # (the box a key fills: ReLink's own Xbox face label's, drawn to the game's face-button glyph)
    face_cs, _ = bg.label("xbox", "south", advances)
    box = bg.bbox(face_cs)

    cff = t["CFF "]
    _, default_w, nominal_w = bg.rebuild_cff(cff, keep, [])
    names = sorted(keyboard_glyphs.GLYPHS)
    extra, ext_metrics, ext_box = [], [], []
    for i, n in enumerate(names):
        cs, adv, b = key_contours(n, box, advances["face"])
        extra.append((f"kb.{i}", bg.charstring(cs, None if adv == default_w else adv - nominal_w)))
        ext_metrics.append((adv, round(b[0])))
        ext_box.append(b)
    glyph_of = {n: keep + i for i, n in enumerate(names)}
    any_glyph = glyph_of[kk.kenney_name(-1)]
    key_glyph = {vk: glyph_of.get(kk.kenney_name(vk), any_glyph) for vk in range(256)}
    new_cff, _, _ = bg.rebuild_cff(cff, keep, extra)

    slot_glyphs = {cp: key_glyph[DEFAULT_KEY[name]] for name, cp, _ in bg.SWITCH}
    # (each key's own code point, KEY_BASE + its virtual-key code: Auto's texts are rewritten to them while the keyboard is
    # in use, host/prompts.c text_rewrite; codes the game's glyph cache has never seen with another icon)
    keys = {kk.KEY_BASE + vk: key_glyph[vk] for vk in range(256)}
    new_cmap, before, slots = bg.rebuild_cmap(t["cmap"], slot_glyphs, extra=keys)
    if any(c in before for c in keys):
        raise bg.Unfit("External already maps a code point of KEY_BASE's range")

    all_metrics = metrics[:keep] + ext_metrics
    n = len(all_metrics)
    new_hmtx = b"".join(struct.pack(">Hh", aw, lsb) for aw, lsb in all_metrics)
    maxp = bytearray(t["maxp"])
    struct.pack_into(">H", maxp, 4, n)
    hhea = bytearray(t["hhea"])
    struct.pack_into(">H", hhea, 34, n)
    aw_max, min_lsb, min_rsb, x_ext = struct.unpack_from(">Hhhh", hhea, 10)
    head = bytearray(t["head"])
    xmin, ymin, xmax, ymax = struct.unpack_from(">hhhh", head, 36)
    for (adv, lsb), b in zip(ext_metrics, ext_box):
        aw_max = max(aw_max, adv)
        min_lsb = min(min_lsb, lsb)
        min_rsb = min(min_rsb, adv - round(b[2]))
        x_ext = max(x_ext, round(b[2]))
        xmin, ymin = min(xmin, math.floor(b[0])), min(ymin, math.floor(b[1]))
        xmax, ymax = max(xmax, math.ceil(b[2])), max(ymax, math.ceil(b[3]))
    struct.pack_into(">Hhhh", hhea, 10, aw_max, min_lsb, min_rsb, x_ext)
    struct.pack_into(">hhhh", head, 36, xmin, ymin, xmax, ymax)
    struct.pack_into(">I", head, 8, 0)
    new = dict(t)
    new.update({"CFF ": new_cff, "cmap": new_cmap, "hmtx": new_hmtx, "maxp": bytes(maxp), "hhea": bytes(hhea),
                "head": bytes(head)})

    # (as button_glyphs.build, but the file may be longer than the game's: the size table is raised for it)
    order = [tag for tag, _, _, _ in sorted(dirs, key=lambda d: d[2])]
    out = bytearray(orig[:12 + 16 * len(dirs)])
    at = {}
    for tag in order:
        out += b"\0" * (-len(out) % 4)
        at[tag] = len(out)
        out += new[tag]
    out += b"\0" * (-len(out) % 4)
    dir_at = {}
    for i, (tag, _, _, _) in enumerate(dirs):
        struct.pack_into(">4sIII", out, 12 + 16 * i, tag.encode("latin-1"), bg.checksum(new[tag]), at[tag], len(new[tag]))
        dir_at[tag] = 12 + 16 * i
    struct.pack_into(">I", out, at["head"] + 8, (0xB1B0AFBA - bg.checksum(bytes(out))) & 0xFFFFFFFF)
    info = {"slots": {cp: at["cmap"] + o for cp, o in slots.items()}, "keys": key_glyph,
            "cmap": (at["cmap"], len(new_cmap), dir_at["cmap"] + 4), "head": at["head"] + 8, "switch": switch_glyph}
    return bytes(out), info


def size_table(romfs, dictionary, game_size, font_size):
    """(Hookshot nx2/prompt_assets.py size_table, GPL-3.0) the game's resource size table ("RESTBL", u32 version, u32 name
    field's size, u32 hashed entries, u32 named entries; a hashed entry: u32 CRC-32 of the path, u32 size, sorted by hash)
    with the External font's entry raised from the game's font (game_size bytes decompressed) to fit font_size: the game
    drops a file larger than its entry. (name, bytes); bytes None when the font fits already"""
    folder = os.path.join(romfs, "System", "Resource")
    name = next((n for n in sorted(os.listdir(folder)) if n.startswith("ResourceSizeTable.") and n.endswith(".rsizetable.zs")),
                None)
    if not name:
        raise bg.Unfit("no System/Resource/ResourceSizeTable.*.rsizetable.zs")
    b = bytearray(pa.read_zs(romfs, f"System/Resource/{name}", dictionary))
    if b[:6] != b"RESTBL":
        raise bg.Unfit(f"{name} is not a RESTBL table")
    hashed, = struct.unpack_from("<I", b, 14)
    want = zlib.crc32(bg.FONT[:-3].encode())
    for i in range(hashed):
        at = 22 + 8 * i
        h, size = struct.unpack_from("<II", b, at)
        if h == want:
            fit = font_size + size - game_size   # (the entry's allowance over the file kept)
            if fit <= size:
                return name, None
            struct.pack_into("<I", b, at + 4, fit)
            return name, bytes(b)
    raise bg.Unfit(f"{name} has no entry for {bg.FONT[:-3]}")


def zstd_raw(data):
    """a zstd frame (RFC 8878) of raw blocks, single segment, the content size in the header (as host/prompts.c writes)"""
    n = len(data)
    if n < 256:
        head = bytes([0x28, 0xB5, 0x2F, 0xFD, 0x20, n])
    elif n < 65536 + 256:
        head = bytes([0x28, 0xB5, 0x2F, 0xFD, 0x60]) + struct.pack("<H", n - 256)
    else:
        head = bytes([0x28, 0xB5, 0x2F, 0xFD, 0xA0]) + struct.pack("<I", n)
    out = bytearray(head)
    done = 0
    while True:
        part = min(n - done, 128 << 10)
        last = done + part == n
        out += struct.pack("<I", part << 3 | int(last))[:3] + data[done:done + part]
        done += part
        if last:
            return bytes(out)


def write_sidecar(path, orig, info, wrap, font, table_name):
    lines = [
        "# The keyboard button prompts' font, made by nx2/keyboard_prompts.py from the game's own Font2/Scalable/External font:",
        "# keyboard.otf is that font, decoded, with a glyph for each key added. Numbers are decimal, code points hex.",
        "# size <bytes>: keyboard.otf's length (longer than the game's font: rsizetable.zs raises its entry).",
        "# original_sha256 <hex>: of the original decoded font.",
        "# slot <code point> <offset>: the file offset of that code point's glyph id (2 bytes, big-endian).",
        "# key <virtual-key code> <glyph id>: the glyph shown for that key (Kenney's ANY key for one it has none of).",
        "# switch <code point> <glyph id>: the game's own glyph for that Switch button, still in the font.",
        "# cmap, head, wrapper: as prompts.txt's; wrapper's length is the wrapped keyboard font's.",
        "# table <name>: the size table rsizetable.zs replaces (System/Resource/<name>).",
        "# font keyboard <hex>: the 64-bit FNV-1a hash of keyboard.otf as written here.",
        f"size {len(font)}",
        f"original_sha256 {hashlib.sha256(orig).hexdigest()}",
    ]
    lines += [f"slot {cp:04X} {info['slots'][cp]}" for _, cp, _ in bg.SWITCH]
    lines += [f"key {vk} {g}" for vk, g in sorted(info["keys"].items())]
    lines += [f"switch {cp:04X} {info['switch'][name]}" for name, cp, _ in bg.SWITCH]
    lines += ["cmap %d %d %d" % info["cmap"], f"head {info['head']}"]
    lines += ["wrapper %s %s %d %s" % (wrap["magic"].hex(), wrap["key"].hex(), 8 + len(font) + len(wrap["after"]),
                                       wrap["after"].hex() if wrap["after"] else "-")]
    lines += [f"table {table_name}", "font keyboard %016x" % bg.fnv1a64(font)]
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def make(romfs, out, orig, wrap, dictionary):
    """keyboard.otf, keyboard.txt and rsizetable.zs into out (prompts/); raises on any failure (the caller removes them)"""
    font, info = build(orig)
    table_name, table = size_table(romfs, dictionary, len(orig), len(font))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "keyboard.otf"), "wb") as f:
        f.write(font)
    rs = os.path.join(out, "rsizetable.zs")
    if table is not None:
        with open(rs, "wb") as f:
            f.write(zstd_raw(table))
    elif os.path.exists(rs):
        os.remove(rs)
    write_sidecar(os.path.join(out, "keyboard.txt"), orig, info, wrap, font, table_name)
    return len(font), len(orig), table is not None


FILES = ("keyboard.otf", "keyboard.txt", "rsizetable.zs", "keytex_keys.bin")


# ---- (ReLink-R 0.0.14) The HUD cross's faded letters for the keyboard: the key bound to Switch A, B, X and Y --------------
KEY_CAP = 1.55   # (a keycap's height against the game's letters' cap height: its letter then reads about as large as theirs)


def keytex_key_mask(name, target):
    """Kenney's glyph name as a 64 x 64 coverage mask, its ink box centred on the game's letters' (button_glyphs.keytex_target)
    and KEY_CAP times their cap height tall"""
    cx, cy, cap, _ = target
    _, cs = keyboard_glyphs.GLYPHS[name]
    b = bg.bbox(cs)
    s = cap * KEY_CAP / max(b[3] - b[1], 1)
    s = min(s, (bg.KEYTEX_SIZE - 4) / max(b[2] - b[0], 1))   # (a wide key, Space or Shift: no wider than the texture)
    mx, my = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    cov = bg.raster(cs, bg.KEYTEX_SIZE, bg.KEYTEX_SIZE, lambda q: (cx + (q[0] - mx) * s, cy - (q[1] - my) * s))
    return outlined(cov, max(2, round(target[3] * 0.6)))


def outlined(cov, ring):
    """a solid keycap's coverage (64 x 64, its letter cut out) as the game's letters are drawn, strokes on nothing: the key's
    outline, ring pixels thick, and its letter or symbol (what the keycap cuts out of itself)"""
    n = bg.KEYTEX_SIZE
    solid = [c >= 128 for c in cov]
    outside = [False] * (n * n)   # (reached from the texture's edge through the keycap's background)
    stack = [i for i in range(n * n) if (i < n or i >= n * (n - 1) or i % n in (0, n - 1)) and not solid[i]]
    for i in stack:
        outside[i] = True
    while stack:
        i = stack.pop()
        x = i % n
        for j in ((i - 1) if x else -1, (i + 1) if x < n - 1 else -1, i - n, i + n):
            if 0 <= j < n * n and not outside[j] and not solid[j]:
                outside[j] = True
                stack.append(j)
    dist = [0 if o else 10 ** 6 for o in outside]   # (steps from the outside, up to ring)
    for _ in range(ring):
        nd = dist[:]
        for i in range(n * n):
            if dist[i]:
                x, y = i % n, i // n
                m = min(dist[(i - 1) if x else i], dist[(i + 1) if x < n - 1 else i], dist[i - n if y else i],
                        dist[i + n if y < n - 1 else i])
                nd[i] = min(dist[i], m + 1)
        dist = nd
    out = bytearray(n * n)
    for i in range(n * n):
        if outside[i]:
            continue
        out[i] = cov[i] if dist[i] <= ring else 255 - cov[i]   # (the outline: the keycap's edge; inside it, its letter)
    return bytes(out)


def write_keytex_keys(path, masks, index):
    """keytex_keys.bin, little-endian: "RLKK", u16 version 1, u16 masks n, u16 width 64, u16 height 64; then 256 bytes, the
    mask of each virtual-key code (0..255; every code has one: Kenney's ANY key for a key it has no picture of); then the n
    masks, 2,048 bytes of BC4 blocks each (rows of 4 x 4 blocks, top down, as keytex.bin's); then the 64-bit FNV-1a hash of
    all the bytes before it (gpu/vk/prompt_tex.h KeyTable)"""
    out = bytearray(b"RLKK" + struct.pack("<4H", 1, len(masks), bg.KEYTEX_SIZE, bg.KEYTEX_SIZE))
    out += bytes(index)
    for m in masks:
        if len(m) != bg.KEYTEX_SIZE * bg.KEYTEX_SIZE // 2:
            raise bg.Unfit("a key mask of the wrong size")
        out += m
    out += struct.pack("<Q", bg.fnv1a64(bytes(out)))
    with open(path, "wb") as f:
        f.write(out)


def make_keytex_keys(romfs, dictionary, out):
    """keytex_keys.bin into out: (path, masks); raises on any failure"""
    target = bg.keytex_target(bg.game_keytex(pa.read_zs(romfs, bg.BNTX, dictionary)))
    names = sorted(keyboard_glyphs.GLYPHS)
    if len(names) > 255:
        raise bg.Unfit("more key pictures than an index of a byte")
    pos = {n: i for i, n in enumerate(names)}
    masks = [bg.bc4_encode(keytex_key_mask(n, target), bg.KEYTEX_SIZE, bg.KEYTEX_SIZE) for n in names]
    anyi = pos[kk.kenney_name(-1)]
    index = [pos.get(kk.kenney_name(vk), anyi) for vk in range(256)]
    path = os.path.join(out, "keytex_keys.bin")
    write_keytex_keys(path, masks, index)
    return path, len(masks)
