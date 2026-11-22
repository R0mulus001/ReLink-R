/* (relink) The game's texture heap compaction, let through once in a while (nx2/oot_tex_compact.py).

   The texture data manager's per-frame step asks the heap's compaction thread for a round at every frame none runs. Each
   texture a round moves reaches the renderer as a new texture (upload, descriptors, sync: 3 to 5 ms in a busy place such
   as the market). nx2/oot_tex_compact.py has the step call hos_tex_compact_due just before it would ask; the answer is
   yes at most once every HOS_TEX_COMPACT_MS (default 1000). 0 is the game's own (every frame), "off" never asks.
   A round that has started still finishes: only the asking is spaced out. */
#include "hos.h"
#include <stdlib.h>
#include <string.h>

static int64_t tc_gap_ns = -2;       /* -2 not read yet, -1 never, 0 every frame */
static int64_t tc_last_ns;
static unsigned long tc_asked, tc_let;

static void tc_read(void) {
    const char *e = getenv("HOS_TEX_COMPACT_MS");
    int64_t ms = 1000;
    if (e && *e) {
        if (!strcmp(e, "off")) ms = -1;
        else ms = atoll(e);
    }
    tc_gap_ns = ms < 0 ? -1 : ms * 1000000;
    hos_log("tex: heap compaction round %s", ms < 0 ? "never asked for (HOS_TEX_COMPACT_MS=off)" : ms == 0 ? "asked for at every frame (the game's own)" : "asked for at most once per gap");
    if (ms > 0) hos_log("tex: the compaction gap is %lld ms (HOS_TEX_COMPACT_MS)", (long long)ms);
}

/* 1 when the step may ask for a round now. Only the game's step calls it, from its one thread. */
int hos_tex_compact_due(void) {
    if (tc_gap_ns == -2) tc_read();
    tc_asked++;
    int yes;
    if (tc_gap_ns == 0) {
        yes = 1;
    } else if (tc_gap_ns < 0) {
        yes = 0;
    } else {
        const int64_t now = hos_now_ns();
        yes = tc_last_ns == 0 || now - tc_last_ns >= tc_gap_ns;
        if (yes) tc_last_ns = now;
    }
    if (yes) tc_let++;
    if (tc_asked % 3600 == 0) hos_log("tex: heap compaction: %lu rounds let through in %lu asks", tc_let, tc_asked);
    return yes;
}

/* (relink, issues 47 and 72: the striped ground) nx2/oot_tex_move.py calls this right before each copy of the compaction: the
   texture stored at [from, from + size) is about to be copied to `to` with the CPU and made again there. What the GPU drew
   into textures of that range is only in the renderer's images: it is written back into their memory first (the back end's
   answer to a remapping of virtual pages, which is the same need), so the copy carries the texels. A range with no such
   texture costs one list lookup. HOS_TEX_MOVE_FLUSH=0: not told (the stripes come back), 2: the first 200 moves are logged. */
void rx_nvn_vmap_changing(uint64_t gpu, uint64_t size);   /* (host/rx_backend.c; a pool's GPU address is its memory's) */

static int tm_mode = -1;
static unsigned long tm_moves;
static uint64_t tm_bytes;

void hos_tex_moving(uint64_t from, uint64_t size, uint64_t to) {
    if (tm_mode < 0) {
        const char *e = getenv("HOS_TEX_MOVE_FLUSH");
        tm_mode = e && *e ? atoi(e) : 1;
        hos_log("tex: textures the heap's compaction moves are %s", tm_mode ? "written back from the GPU's images first" : "copied as their memory is (HOS_TEX_MOVE_FLUSH=0)");
    }
    tm_moves++, tm_bytes += size;
    if (tm_mode == 2 && tm_moves <= 200)
        hos_log("tex: move %#llx -> %#llx, %llu KB", (unsigned long long)from, (unsigned long long)to, (unsigned long long)(size >> 10));
    if (tm_moves % 2000 == 0)
        hos_log("tex: the heap's compaction has moved %lu textures (%llu MB)", tm_moves, (unsigned long long)(tm_bytes >> 20));
    if (tm_mode && from && size && size < (1ull << 31)) rx_nvn_vmap_changing(from, size);
}
