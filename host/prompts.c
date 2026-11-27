/* (relink, issues 34, 63, 68, 20) Button prompts for Xbox and PlayStation controllers.

   The game draws almost every button prompt with one font, External (Font2/Scalable/External.Nin_Ounce_NVN2.bfotf.zs),
   opened once during the start. Each build makes two copies of the player's own font with ReLink's own labels added
   (nx2/button_glyphs.py): <game folder>/prompts/xbox.otf and playstation.otf, and prompts.txt, which says where the
   glyph id of each Switch button's code point is in those files and which glyph is each family's label for each pad
   position.

   When the game opens that font and the player chose Xbox or PlayStation prompts (the Insert menu's Controls tab, ini key
   button_prompts: 0 the game's own, 1 Xbox, 2 PlayStation, 3 Keyboard, 4 Auto; HOS_BUTTON_PROMPTS=0|xbox|playstation|
   keyboard|auto wins over it. ReLink-R 0.0.14: Keyboard is the keys bound on the Controls page, from prompts/keyboard.otf
   and keyboard.txt (nx2/keyboard_prompts.py), whose font is longer than the game's: the resource size table is served
   from prompts/rsizetable.zs with its entry raised; Auto is Keyboard when no controller is connected at the start), the host
   writes each Switch button's slot with the label of the pad position that button is bound to (hos_binding: the
   defaults, the Layout preset, the player's own bindings), fixes the cmap's and the file's checksums, wraps the font as
   the game's file is wrapped (prompts.txt's wrapper record) inside a zstd frame of raw blocks (no compression, no
   dictionary), writes that to <game folder>/prompts/cache/External.<family>.bfotf.zs and the game reads that file
   instead. A Switch button bound to an input without a label (a D-pad direction, nothing) keeps the game's own glyph.

   A player's mod that gives this file wins. A missing or inconsistent prompts.txt or font leaves the game's font, with
   one log line that says why.

   The font-building core (prompts_make and what it calls) takes its paths and bindings as arguments and uses nothing
   else of the host: built with -DPROMPTS_CORE_ONLY it is that core alone, for a test program. */
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../gpu/vk/vk_api.h"   /* (the controls' names: HOS_SW_*, HOS_PAD_*) */
#include "prompts.h"

/* ---- the core ------------------------------------------------------------------------------------------------- */

#define PR_MAX_FONT (4u << 20)          /* (the game's font is 14,560 bytes: anything this big is not the font) */
#define PR_MAX_SIDECAR (64u << 10)
#define PR_MAX_AFTER 4096u
#define PR_BUTTONS 12
#define PR_POSITIONS 12

/* The Switch buttons whose glyphs follow the bindings (nx2/button_glyphs.py SWITCH): the HOS_SW_* button, its code point
   in the font, its name in the log */
static const struct { int sw; unsigned cp; const char *name; } buttons[PR_BUTTONS] = {
    {HOS_SW_A, 0xE040, "A"},     {HOS_SW_B, 0xE041, "B"},       {HOS_SW_X, 0xE042, "X"},  {HOS_SW_Y, 0xE043, "Y"},
    {HOS_SW_L, 0xE044, "L"},     {HOS_SW_R, 0xE045, "R"},       {HOS_SW_ZL, 0xE046, "ZL"}, {HOS_SW_ZR, 0xE047, "ZR"},
    {HOS_SW_PLUS, 0xE04B, "+"},  {HOS_SW_MINUS, 0xE04C, "-"},   {HOS_SW_LS, 0xE056, "LS"}, {HOS_SW_RS, 0xE057, "RS"}};
/* The pad positions a label is drawn for, as prompts.txt names them, the HOS_PAD_* input at each, and each family's
   name for that label in the log */
static const struct { const char *name; int pad; const char *xbox, *playstation; } positions[PR_POSITIONS] = {
    {"south", HOS_PAD_SOUTH, "A", "Cross"},           {"east", HOS_PAD_EAST, "B", "Circle"},
    {"west", HOS_PAD_WEST, "X", "Square"},            {"north", HOS_PAD_NORTH, "Y", "Triangle"},
    {"l1", HOS_PAD_LSHOULDER, "LB", "L1"},            {"r1", HOS_PAD_RSHOULDER, "RB", "R1"},
    {"l2", HOS_PAD_LTRIGGER, "LT", "L2"},             {"r2", HOS_PAD_RTRIGGER, "RT", "R2"},
    {"start", HOS_PAD_START, "Menu", "Options"},      {"back", HOS_PAD_BACK, "View", "Create"},
    {"l3", HOS_PAD_LSTICK, "LS", "L3"},               {"r3", HOS_PAD_RSTICK, "RS", "R3"}};

int prompts_position_of_pad(int pad) {
    for (int i = 0; i < PR_POSITIONS; i++)
        if (positions[i].pad == pad) return i;
    return -1;
}

/* Why the game's own font stays, into note: returns 0 */
static int why(char *note, size_t cap, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    if (note && cap) vsnprintf(note, cap, fmt, ap);
    va_end(ap);
    return 0;
}

/* A whole file into memory (at most max bytes): its length, or -1 when it cannot be read or is longer */
static long read_all(const char *path, unsigned char **out, size_t max) {
    *out = NULL;
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    long n = -1;
    if (!fseek(f, 0, SEEK_END)) n = ftell(f);
    if (n < 0 || (size_t)n > max || fseek(f, 0, SEEK_SET)) {
        fclose(f);
        return n < 0 ? -1 : -2;
    }
    unsigned char *b = (unsigned char *)malloc((size_t)n + 1);
    if (b && fread(b, 1, (size_t)n, f) != (size_t)n) free(b), b = NULL;
    fclose(f);
    if (!b) return -1;
    b[n] = 0;
    *out = b;
    return n;
}

/* A number of the sidecar: decimal, or hexadecimal when hex; the whole word, at most max */
static int number(const char *w, int hex, unsigned long max, unsigned long *v) {
    if (!w || !*w) return 0;
    char *end;
    *v = strtoul(w, &end, hex ? 16 : 10);
    return *end == 0 && *w != '-' && *w != '+' && *v <= max;
}
/* An even number of hex digits into bytes: how many, or -1 */
static long hex_bytes(const char *w, unsigned char *out, size_t cap) {
    const size_t n = strlen(w);
    if (n % 2 || n / 2 > cap) return -1;
    for (size_t i = 0; i < n / 2; i++) {
        unsigned v = 0;
        for (int k = 0; k < 2; k++) {
            const char c = w[2 * i + k];
            const int d = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
            if (d < 0) return -1;
            v = v * 16 + (unsigned)d;
        }
        out[i] = (unsigned char)v;
    }
    return (long)(n / 2);
}

typedef struct {
    unsigned long size;
    unsigned long slot[PR_BUTTONS];          /* (the file offset of each button's glyph id; ULONG_MAX: not given) */
    unsigned long label[PR_POSITIONS];       /* (the chosen family's) */
    unsigned long own[PR_BUTTONS];           /* (the game's own glyph of each button: the switch records) */
    unsigned long cmap_off, cmap_len, cmap_sum, head;
    int have_size, have_cmap, have_head, have_wrapper, have_hash;
    uint64_t hash;                           /* (the chosen family's file as written: FNV-1a, 64 bits) */
    unsigned char magic[4], key[4];
    unsigned long wrapped_len;
    unsigned char after[PR_MAX_AFTER];
    long after_len;
    unsigned long keyg[256];                 /* (ReLink-R 0.0.14, keyboard.txt: the glyph of each virtual-key code; 0 none) */
    int have_keys;
    char table[160];                         /* (keyboard.txt: the size table rsizetable.zs replaces) */
} Sidecar;

/* prompts.txt (nx2/button_glyphs.py write_sidecar): 1, or 0 with why in note */
static int read_sidecar(const char *path, const char *family, Sidecar *s, char *note, size_t cap) {
    unsigned char *text;
    const long n = read_all(path, &text, PR_MAX_SIDECAR);
    if (n < 0) return why(note, cap, n == -1 ? "%s cannot be read" : "%s is too long to be the prompts' table", path);
    memset(s, 0, sizeof *s);
    for (int i = 0; i < PR_BUTTONS; i++) s->slot[i] = s->own[i] = (unsigned long)-1;
    for (int i = 0; i < PR_POSITIONS; i++) s->label[i] = (unsigned long)-1;
    int ok = 1;
    long line_no = 0;
    char *p = (char *)text;
    while (ok && *p) {
        char *line = p, *nl = strchr(p, '\n');
        p = nl ? nl + 1 : p + strlen(p);
        if (nl) *nl = 0;
        line_no++;
        char *hash = strchr(line, '#');
        if (hash) *hash = 0;
        char *w[8];
        int nw = 0;
        for (char *t = line; *t && nw < 8;) {
            while (*t == ' ' || *t == '\t' || *t == '\r') *t++ = 0;
            if (!*t) break;
            w[nw++] = t;
            while (*t && *t != ' ' && *t != '\t' && *t != '\r') t++;
        }
        if (!nw) continue;
        unsigned long a = 0, b = 0, c = 0;
        if (!strcmp(w[0], "size")) {
            ok = nw == 2 && number(w[1], 0, PR_MAX_FONT, &s->size) && s->size >= 64;
            s->have_size = 1;
        } else if (!strcmp(w[0], "slot") || !strcmp(w[0], "switch")) {
            const int is_slot = !strcmp(w[0], "slot");
            ok = nw == 3 && number(w[1], 1, 0xFFFF, &a) && number(w[2], 0, PR_MAX_FONT, &b);
            int i = 0;
            while (ok && i < PR_BUTTONS && buttons[i].cp != a) i++;
            if (ok && i < PR_BUTTONS && is_slot) s->slot[i] = b;
            if (ok && i < PR_BUTTONS && !is_slot) s->own[i] = b;
        } else if (!strcmp(w[0], "label")) {
            ok = nw == 4 && number(w[3], 0, 0xFFFF, &a) && a > 0;
            int i = 0;
            while (ok && i < PR_POSITIONS && strcmp(positions[i].name, w[2])) i++;
            if (ok && i < PR_POSITIONS && !strcmp(w[1], family)) s->label[i] = a;
        } else if (!strcmp(w[0], "key")) {   /* (ReLink-R 0.0.14, keyboard.txt) */
            ok = nw == 3 && number(w[1], 0, 255, &a) && number(w[2], 0, 0xFFFF, &b) && b > 0;
            if (ok) s->keyg[a] = b, s->have_keys = 1;
        } else if (!strcmp(w[0], "table")) {
            ok = nw == 2 && strlen(w[1]) < sizeof s->table && !strpbrk(w[1], "/\\:");
            if (ok) snprintf(s->table, sizeof s->table, "%s", w[1]);
        } else if (!strcmp(w[0], "cmap")) {
            ok = nw == 4 && number(w[1], 0, PR_MAX_FONT, &a) && number(w[2], 0, PR_MAX_FONT, &b) &&
                 number(w[3], 0, PR_MAX_FONT, &c);
            s->cmap_off = a, s->cmap_len = b, s->cmap_sum = c, s->have_cmap = 1;
        } else if (!strcmp(w[0], "head")) {
            ok = nw == 2 && number(w[1], 0, PR_MAX_FONT, &s->head);
            s->have_head = 1;
        } else if (!strcmp(w[0], "wrapper")) {
            ok = nw == 5 && hex_bytes(w[1], s->magic, 4) == 4 && hex_bytes(w[2], s->key, 4) == 4 &&
                 number(w[3], 0, PR_MAX_FONT + 8 + PR_MAX_AFTER, &s->wrapped_len);
            if (ok) s->after_len = strcmp(w[4], "-") ? hex_bytes(w[4], s->after, PR_MAX_AFTER) : 0;
            ok = ok && s->after_len >= 0;
            s->have_wrapper = 1;
        } else if (!strcmp(w[0], "font")) {
            unsigned char h[8];
            ok = nw == 3 && hex_bytes(w[2], h, 8) == 8;
            if (ok && !strcmp(w[1], family)) {
                s->hash = 0;
                for (int k = 0; k < 8; k++) s->hash = s->hash << 8 | h[k];
                s->have_hash = 1;
            }
        }   /* (other records: original_sha256, and any a later script adds) */
    }
    free(text);
    if (!ok) return why(note, cap, "line %ld of %s is not understood", line_no, path);
    if (!s->have_size || !s->have_cmap || !s->have_head || !s->have_wrapper || !s->have_hash)
        return why(note, cap, "%s has no %s record (made by an older build?)", path,
                   !s->have_size ? "size" : !s->have_cmap ? "cmap" : !s->have_head ? "head" : !s->have_wrapper ? "wrapper"
                   : "font");
    for (int i = 0; i < PR_BUTTONS; i++) {
        if (s->slot[i] == (unsigned long)-1 || s->own[i] == (unsigned long)-1 || s->own[i] == 0 || s->own[i] > 0xFFFF)
            return why(note, cap, "%s has no slot or switch record for Switch %s", path, buttons[i].name);
        if (s->slot[i] + 2 > s->size) return why(note, cap, "%s's slot for Switch %s is past the font's end", path, buttons[i].name);
    }
    if (!strcmp(family, "keyboard")) {   /* (ReLink-R 0.0.14: keys, not pad labels) */
        if (!s->have_keys || !s->table[0]) return why(note, cap, "%s has no key or table record", path);
    } else {
        for (int i = 0; i < PR_POSITIONS; i++)
            if (s->label[i] == (unsigned long)-1) return why(note, cap, "%s has no %s %s label", path, family, positions[i].name);
    }
    if (s->cmap_off + s->cmap_len > s->size || s->cmap_sum + 4 > s->size || s->head + 4 > s->size || !s->cmap_len)
        return why(note, cap, "%s's cmap or head record is past the font's end", path);
    if (s->wrapped_len != 8 + s->size + (unsigned long)s->after_len)
        return why(note, cap, "%s's wrapper length is not 8 bytes, the font and the bytes after it", path);
    return 1;
}

static uint32_t be32(const unsigned char *b) { return (uint32_t)b[0] << 24 | (uint32_t)b[1] << 16 | (uint32_t)b[2] << 8 | b[3]; }
static void put_be32(unsigned char *b, uint32_t v) { b[0] = (unsigned char)(v >> 24), b[1] = (unsigned char)(v >> 16), b[2] = (unsigned char)(v >> 8), b[3] = (unsigned char)v; }
/* The OpenType checksum of n bytes: their sum as big-endian 32-bit words, the last one padded with zeros */
static uint32_t ot_sum(const unsigned char *b, unsigned long n) {
    uint32_t s = 0;
    unsigned long i = 0;
    for (; i + 4 <= n; i += 4) s += be32(b + i);
    if (i < n) {
        unsigned char last[4] = {0, 0, 0, 0};
        memcpy(last, b + i, n - i);
        s += be32(last);
    }
    return s;
}

static uint64_t fnv1a64(const unsigned char *b, unsigned long n) {
    uint64_t h = 0xCBF29CE484222325ull;
    for (unsigned long i = 0; i < n; i++) h = (h ^ b[i]) * 0x100000001B3ull;
    return h;
}

int prompts_make(const char *dir, const char *family, const int binding[HOS_SW_N], const char *out_path, char *note,
                 size_t cap) {
    const int keyboard = !strcmp(family, "keyboard");   /* (ReLink-R 0.0.14: binding[] holds virtual-key codes, 0 none) */
    if (strcmp(family, "xbox") && strcmp(family, "playstation") && !keyboard)
        return why(note, cap, "no button font for the family %s", family);
    char path[1024];
    Sidecar *s = (Sidecar *)malloc(sizeof *s);
    if (!s) return why(note, cap, "out of memory");
    snprintf(path, sizeof path, "%s/%s", dir, keyboard ? "keyboard.txt" : "prompts.txt");
    if (!read_sidecar(path, family, s, note, cap)) return free(s), 0;

    snprintf(path, sizeof path, "%s/%s.otf", dir, family);
    unsigned char *font;
    const long n = read_all(path, &font, PR_MAX_FONT);
    if (n < 0) return free(s), why(note, cap, n == -1 ? "%s cannot be read" : "%s is too long to be the font", path);
    int ok = 0;
    if ((unsigned long)n != s->size) why(note, cap, "%s is %ld bytes, not prompts.txt's size (%lu)", path, n, s->size);
    else if (memcmp(font, "OTTO", 4)) why(note, cap, "%s is not an OpenType (CFF) font", path);
    else if (fnv1a64(font, s->size) != s->hash) why(note, cap, "%s is not the font prompts.txt was made with (its hash)", path);
    else if (ot_sum(font, s->size) != 0xB1B0AFBAu || ot_sum(font + s->cmap_off, s->cmap_len) != be32(font + s->cmap_sum))
        why(note, cap, "%s's checksums do not hold: not the font prompts.txt was made with", path);
    else ok = 1;
    for (int i = 0; ok && i < PR_BUTTONS; i++) {   /* (as made, each slot holds one of the family's labels, or keys) */
        const unsigned v = (unsigned)font[s->slot[i]] << 8 | font[s->slot[i] + 1];
        int k = 0;
        if (keyboard) {
            while (k < 256 && s->keyg[k] != v) k++;
            if (k == 256) ok = why(note, cap, "%s's slot for Switch %s holds none of keyboard.txt's keys", path, buttons[i].name);
            continue;
        }
        while (k < PR_POSITIONS && s->label[k] != v) k++;
        if (k == PR_POSITIONS) ok = why(note, cap, "%s's slot for Switch %s holds none of prompts.txt's labels", path, buttons[i].name);
    }
    if (!ok) return free(font), free(s), 0;
    if (keyboard) {   /* (ReLink-R 0.0.14) each Switch button's slot: the key bound to it, or the game's own glyph */
        char shows[600];
        size_t at = 0;
        shows[0] = 0;
        for (int i = 0; i < PR_BUTTONS; i++) {
            const int vk = binding[buttons[i].sw];
            const unsigned long g = vk > 0 && vk < 256 && s->keyg[vk] ? s->keyg[vk] : s->own[i];
            font[s->slot[i]] = (unsigned char)(g >> 8), font[s->slot[i] + 1] = (unsigned char)g;
            if (at < sizeof shows)
                at += (size_t)snprintf(shows + at, sizeof shows - at, vk > 0 ? "%s%s key 0x%02X" : "%s%s keeps the Switch's",
                                       i ? ", " : "", buttons[i].name, vk);
        }
        if (note && cap) snprintf(note, cap, "%s", shows);
    }

    /* each Switch button's slot: the label of the pad position it is bound to, or the game's own glyph */
    char shows[512];
    size_t at = 0;
    shows[0] = 0;
    for (int i = 0; !keyboard && i < PR_BUTTONS; i++) {
        const int pos = prompts_position_of_pad(binding[buttons[i].sw]);
        const unsigned long g = pos >= 0 ? s->label[pos] : s->own[i];
        font[s->slot[i]] = (unsigned char)(g >> 8), font[s->slot[i] + 1] = (unsigned char)g;
        const char *label = pos < 0 ? NULL : family[0] == 'x' ? positions[pos].xbox : positions[pos].playstation;
        if (at < sizeof shows)
            at += (size_t)snprintf(shows + at, sizeof shows - at, "%s%s %s%s", i ? ", " : "", buttons[i].name,
                                   label ? "shows " : "keeps the Switch's", label ? label : "");
    }
    put_be32(font + s->cmap_sum, ot_sum(font + s->cmap_off, s->cmap_len));
    put_be32(font + s->head, 0);
    put_be32(font + s->head, 0xB1B0AFBAu - ot_sum(font, s->size));

    /* the game's wrapping: magic, the length XOR the key, the font XOR the key, the bytes after it */
    const unsigned long len = s->wrapped_len;
    unsigned char *w = (unsigned char *)malloc(len);
    if (!w) return free(font), free(s), why(note, cap, "out of memory");
    memcpy(w, s->magic, 4);
    put_be32(w + 4, (uint32_t)s->size);
    for (int k = 0; k < 4; k++) w[4 + k] ^= s->key[k];
    for (unsigned long i = 0; i < s->size; i++) w[8 + i] = font[i] ^ s->key[i & 3];
    memcpy(w + 8 + s->size, s->after, (size_t)s->after_len);
    free(font);
    free(s);

    /* a zstd frame (RFC 8878) of raw blocks: magic; a single-segment descriptor with the content size (1, 2 or 4 bytes;
       the 2-byte form stores it minus 256), no checksum, no dictionary; then blocks of at most 128 KB, each a 3-byte
       little-endian header (size << 3 | raw type 0 | the last one's bit 0) and the bytes as they are */
    unsigned char head[9] = {0x28, 0xB5, 0x2F, 0xFD};
    size_t hn = 5;
    if (len < 256) head[4] = 0x20, head[hn++] = (unsigned char)len;
    else if (len < 65536 + 256) head[4] = 0x60, head[hn++] = (unsigned char)(len - 256), head[hn++] = (unsigned char)((len - 256) >> 8);
    else {
        head[4] = 0xA0;
        for (int k = 0; k < 4; k++) head[hn++] = (unsigned char)(len >> (8 * k));
    }
    FILE *f = fopen(out_path, "wb");
    if (!f) return free(w), why(note, cap, "%s cannot be written", out_path);
    ok = fwrite(head, 1, hn, f) == hn;
    unsigned long done = 0;
    do {
        const unsigned long part = len - done > (128u << 10) ? (128u << 10) : len - done;
        const uint32_t bh = (uint32_t)part << 3 | (done + part == len ? 1u : 0u);
        const unsigned char b3[3] = {(unsigned char)bh, (unsigned char)(bh >> 8), (unsigned char)(bh >> 16)};
        ok = ok && fwrite(b3, 1, 3, f) == 3 && fwrite(w + done, 1, part, f) == part;
        done += part;
    } while (done < len);
    ok = !fclose(f) && ok;
    free(w);
    if (!ok) {
        remove(out_path);
        return why(note, cap, "%s could not be written whole", out_path);
    }
    if (note && cap && !keyboard) snprintf(note, cap, "%s", shows);
    return 1;
}

/* (ReLink-R 0.0.14) the size table keyboard.txt names (System/Resource/<name>), into name: 1, or 0 with why in note */
int prompts_keyboard_table(const char *dir, char *name, size_t cap, char *note, size_t note_cap) {
    char path[1024];
    Sidecar *s = (Sidecar *)malloc(sizeof *s);
    if (!s) return why(note, note_cap, "out of memory");
    snprintf(path, sizeof path, "%s/keyboard.txt", dir);
    const int ok = read_sidecar(path, "keyboard", s, note, note_cap);
    if (ok) snprintf(name, cap, "%s", s->table);
    free(s);
    return ok;
}

/* ---- the host's side: the setting, the bindings, the paths, the open -------------------------------------------- */
#ifndef PROMPTS_CORE_ONLY
#include "hos.h"
#include "hos_paths.h"
#include "../gpu/vk/prompt_tex.h"   /* (HOS_PROMPTS_TEX_ID: the HUD cross's letters, which the renderer replaces) */
#include <ctype.h>
#include <windows.h>

#define FONT_PATH "Font2/Scalable/External.Nin_Ounce_NVN2.bfotf.zs"
/* (ReLink-R 0.0.14) 3: the keyboard's keys (nx2/keyboard_prompts.py); 4 Auto: the keyboard's when no controller is
   connected at the start, the game's own when one is */
#define FAM_KEYBOARD 3
#define FAM_AUTO 4
static const char *const family_names[5] = {"nintendo", "xbox", "playstation", "keyboard", "auto"};

/* The family chosen: HOS_BUTTON_PROMPTS, else button_prompts= in relink_options.ini beside the game, else 0 (the game's
   own). *from says which */
static int chosen_family(const char *game_dir, char sep, const char **from) {
    const char *e = getenv("HOS_BUTTON_PROMPTS");
    if (e && *e) {
        *from = "HOS_BUTTON_PROMPTS";
        if (!strcmp(e, "1") || !_stricmp(e, "xbox")) return 1;
        if (!strcmp(e, "2") || !_stricmp(e, "playstation") || !_stricmp(e, "ps")) return 2;
        if (!strcmp(e, "0") || !_stricmp(e, "nintendo") || !_stricmp(e, "switch")) return 0;
        if (!strcmp(e, "3") || !_stricmp(e, "keyboard")) return FAM_KEYBOARD;
        if (!strcmp(e, "4") || !_stricmp(e, "auto")) return FAM_AUTO;
        hos_log("prompts: HOS_BUTTON_PROMPTS=%s is not 0, xbox, playstation, keyboard or auto: the ini's choice", e);
    }
    *from = "button_prompts in relink_options.ini";
    char path[MAX_PATH];
    snprintf(path, sizeof path, "%s%crelink_options.ini", game_dir, sep);
    FILE *f = fopen(path, "r");
    int v = 0;
    if (f) {
        char line[80];
        while (fgets(line, sizeof line, f))
            if (!strncmp(line, "button_prompts=", 15)) v = atoi(line + 15);
        fclose(f);
    }
    return v >= 0 && v <= FAM_AUTO ? v : 0;
}

int hos_mods_romfs(const char *rel, char *out, size_t cap);   /* mods.c */
int hos_binding(int set, int button, int slot);              /* nn_hid.c */
void rx_option_set(int id, int value);                       /* rx_backend.c */

/* What the font was given, for the renderer's HUD cross letters (gpu/vk/prompt_tex.h): HOS_PROMPTS_TEX_VALUE, -1 not
   decided yet */
static volatile LONG tex_value = -1;

/* The renderer told what the font was given (the family, 0 when the game's own font stays, and Switch A, B, X and Y's
   inputs); rx_backend.c rx_start calls it again once the renderer is there, for a font opened before that */
void hos_prompts_announce(void) {
    const LONG v = InterlockedCompareExchange(&tex_value, -1, -1);
    if (v >= 0) rx_option_set(HOS_PROMPTS_TEX_ID, (int)v);
}

int hos_pad_present(void);   /* nn_hid.c (ReLink-R 0.0.14: Auto) */

/* What was decided, once, at the first open of the font or of the resource size table (ReLink-R 0.0.14: the keyboard's
   font is longer than the game's, so the table, read at the boot, before the font, is served with its entry raised) */
static volatile LONG state;          /* 0 not decided, 1 being decided, 2 decided */
static char cache[MAX_PATH];         /* (the font made, empty: the game's own) */
static char table_rel[200];          /* (System/Resource/<the table keyboard.txt names>) */
static char table_path[MAX_PATH];    /* (prompts/rsizetable.zs, served for table_rel; empty: the game's own table) */

static void decide(void) {
    char game[MAX_PATH], mod[MAX_PATH];
    const DWORD n = hos_game_path_a(game, MAX_PATH);
    char *b = n ? strrchr(game, '\\') : NULL, *s = n ? strrchr(game, '/') : NULL;
    char *slash = b > s ? b : s;
    const char sep = slash ? *slash : '\\';
    if (slash) *slash = 0;
    const char *from = "";
    int fam = slash ? chosen_family(game, sep, &from) : 0;
    if (fam == FAM_AUTO) {   /* (SDL's controller thread may not have opened a pad yet: up to 1.5 s for one) */
        int present = 0;
        for (int k = 0; k < 30 && !(present = hos_pad_present()); k++) Sleep(50);
        fam = present ? 0 : FAM_KEYBOARD;
        hos_log("prompts: Auto: %s", present ? "a controller is connected: the game's own button font"
                                             : "no controller connected: the keyboard's keys");
    }
    const int keyboard = fam == FAM_KEYBOARD;
    int pad[HOS_SW_N], binding[HOS_SW_N];
    for (int i = 0; i < HOS_SW_N; i++) {
        pad[i] = hos_binding(HOS_BIND_PAD, i, 0);
        const int k0 = hos_binding(HOS_BIND_KEY, i, 0);   /* (the first key, or the second when the first is cleared) */
        binding[i] = keyboard ? (k0 ? k0 : hos_binding(HOS_BIND_KEY, i, 1)) : pad[i];
    }
    if (!slash) {
        hos_log("prompts: the game folder is not known: the game's own button font");
    } else if (fam == 0) {
        hos_log("prompts: the game's own button font (%s)", from);
    } else if (hos_mods_romfs(FONT_PATH, mod, sizeof mod)) {
        hos_log("prompts: a mod gives %s (%s): it is used, not the %s labels", FONT_PATH, mod, family_names[fam]);
    } else {
        char dir[MAX_PATH], path[MAX_PATH], note[700], tname[160];
        snprintf(dir, sizeof dir, "%s%cprompts", game, sep);
        snprintf(path, sizeof path, "%s%c%s", dir, sep, keyboard ? "keyboard.txt" : "prompts.txt");
        int go = 1;
        if (GetFileAttributesA(path) == INVALID_FILE_ATTRIBUTES) {
            hos_log("prompts: no %s (the build did not make the %s font): the game's own button font", path,
                    keyboard ? "keyboard's" : "button");
            go = 0;
        } else if (keyboard) {
            snprintf(path, sizeof path, "%s%crsizetable.zs", dir, sep);
            if (!prompts_keyboard_table(dir, tname, sizeof tname, note, sizeof note)) {
                hos_log("prompts: %s; the game's own button font", note);
                go = 0;
            } else if (GetFileAttributesA(path) != INVALID_FILE_ATTRIBUTES) {   /* (absent: the font fits the game's entry) */
                snprintf(table_rel, sizeof table_rel, "System/Resource/%s", tname);
                if (hos_mods_romfs(table_rel, mod, sizeof mod)) {
                    hos_log("prompts: a mod gives %s (%s): the keyboard's font would not fit it: the game's own button font",
                            table_rel, mod);
                    go = 0;
                } else {
                    snprintf(table_path, sizeof table_path, "%s", path);
                }
            }
        }
        if (go) {
            snprintf(path, sizeof path, "%s%ccache", dir, sep);
            CreateDirectoryA(path, NULL);
            snprintf(path, sizeof path, "%s%ccache%cExternal.%s.bfotf.zs", dir, sep, sep, family_names[fam]);
            if (prompts_make(dir, family_names[fam], binding, path, note, sizeof note)) {
                snprintf(cache, sizeof cache, "%s", path);
                hos_log("prompts: %s %s (%s): %s; the game reads %s%s%s", family_names[fam], keyboard ? "keys" : "labels",
                        from, note, path, table_path[0] ? ", and its size table " : "", table_path);
            } else {
                hos_log("prompts: %s; the game's own button font", note);
                table_path[0] = 0;   /* (no longer font: the game's own table) */
            }
        }
    }
    /* (the HUD cross's letters follow what the font was given: the pad family when its font was made, else the game's own;
       the keyboard's face keeps the game's letters there) */
    InterlockedExchange(&tex_value, HOS_PROMPTS_TEX_VALUE(cache[0] && !keyboard ? fam : 0, pad[HOS_SW_A], pad[HOS_SW_B],
                                                          pad[HOS_SW_X], pad[HOS_SW_Y]));
    hos_prompts_announce();
}

/* nn_fs.c OpenFile, for a read: the file to open instead of guest's, 1 when there is one. Decided at the first open of the
   font or the size table; a later open of either gets the same answer */
int hos_prompts_redirect(const char *guest, char *out, size_t cap) {
    const char *rel = strstr(guest, ":/");
    if (!rel) return 0;
    rel += 2;
    while (*rel == '/') rel++;
    const int is_font = !_stricmp(rel, FONT_PATH);
    const int is_table = !_strnicmp(rel, "System/Resource/ResourceSizeTable", 33);
    if (!is_font && !is_table) return 0;
    if (InterlockedCompareExchange(&state, 1, 0) != 0) {
        while (state != 2) Sleep(0);
    } else {
        decide();
        InterlockedExchange(&state, 2);
    }
    if (is_font && cache[0]) {
        snprintf(out, cap, "%s", cache);
        return 1;
    }
    if (is_table && table_path[0] && !_stricmp(rel, table_rel)) {
        snprintf(out, cap, "%s", table_path);
        return 1;
    }
    return 0;
}
#endif
