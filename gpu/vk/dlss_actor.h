// (relink) NVIDIA DLSS's actor motion (vk_dlss.cpp): what is worked out on the CPU for a skinned draw drawn again, kept
// apart so tests/test_dlss_actor.cpp checks it without a GPU. Header only, no Vulkan.
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <vector>

namespace dlss_actor {

/// A draw's name across frames: its model (vertex and index buffers, count, base vertex, program) and which of the frame's
/// draws of that model it is (the same model drawn twice: the n-th draw of it is matched with the n-th the frame before)
inline uint64_t key(uint64_t vbuf, uint64_t ibuf, int count, int base_vertex, uint64_t program, int nth) {
    uint64_t h = 0x5bd1e995;
    for (uint64_t v : {vbuf, ibuf, (uint64_t)(uint32_t)count, (uint64_t)(uint32_t)base_vertex, program}) {
        h ^= v + 0x9e3779b97f4a7c15ull + (h << 6) + (h >> 2);
        h *= 0xff51afd7ed558ccdull;
    }
    return (h & ~0xffull) | (uint64_t)std::clamp(nth, 0, 255);
}
inline bool same_model(uint64_t a, uint64_t b) { return a >> 8 == b >> 8; }

/// shaders/dlss_actor.vert's push constants (the fragment stage's the same)
struct Push {
    uint64_t vertices;   // (the vertex stream's device address)
    uint64_t indices;    // (the index buffer's, 4-aligned down: first says where the draw's indices start in it)
    uint64_t origins[2]; // (the draw's origin, xyz: this frame's and the frame before's, copied into the pose buffers)
    uint64_t bones[2];   // (its palettes: 3 x 4 row-major matrices, 12 floats a bone)
    uint32_t nbones;
    uint32_t stride;     // (in words)
    uint32_t count;      // (the vertices in the stream: an index past them draws nothing)
    uint32_t first;      // (in indices, from the address)
    uint32_t itype;      // (0: 8-bit, 1: 16-bit, 2: 32-bit indices)
    int32_t base_vertex;
    uint32_t pos, sets;  // (bytes in a vertex: the position; the joint and weight sets, 1 or 2)
    uint32_t joints[2], weights[2];
    uint32_t formats;    // (kHalfPosition, kByteJoints << set, kOneJoint)
    uint32_t tolerance;  // (depth steps from the scene's within which a pixel is the draw's)
};
static_assert(sizeof(Push) == 6 * 8 + 14 * 4 && sizeof(Push) <= 128, "dlss_actor.vert's push constants");

/// Where a draw's indices are for the shader: the address 4-aligned down, and its first index from there
inline void index_start(uint64_t address, int itype, uint64_t* aligned, uint32_t* first) {
    *aligned = address & ~3ull;
    *first = (uint32_t)((address & 3) >> (itype < 0 ? 0 : itype > 2 ? 2 : itype));
}

/// Push::formats: the position is RGBA16F (else RGB32F); a set's joints are RGBA8UI (else RGBA16UI); kOneJoint: the first
/// set is one R8UI joint a vertex and no weights (each vertex wholly on one bone: the models the game skins rigidly)
constexpr uint32_t kHalfPosition = 1, kByteJoints = 2, kOneJoint = 8;
/// (a diagnostic, RX_VK_DLSS_ACTOR_MARK) the draw writes a fixed motion of 48 px to the right where it would write its own:
/// with RX_VK_DLSS_DEBUG=motion the picture then shows which pixels the draw was found to cover
constexpr uint32_t kMark = 16;
/// (0.7.9.3) A rigid draw: no joints in its vertices, its one "bone" is the object's 3 x 4 world matrix (the object buffer's
/// first 48 bytes) and its origin is none (the matrix holds the move). Each vertex wholly on that matrix
constexpr uint32_t kRigid = 32;

/// A rigid draw's world matrix (3 x 4, row major) against the frame before's of the same model: whether it is the identity
/// (the scene's fixed geometry, drawn in world space: its motion is the camera's), how far its translation moved, whether
/// any of its 12 words changed
inline bool identity_3x4(const float* m, float eps = 1e-5f) {
    for (int r = 0; r < 3; r++)
        for (int c = 0; c < 4; c++)
            if (std::fabs(m[r * 4 + c] - (r == c ? 1.0f : 0.0f)) > eps) return false;
    return true;
}
inline float moved_by(const float* a, const float* b) {
    const float dx = a[3] - b[3], dy = a[7] - b[7], dz = a[11] - b[11];
    return std::sqrt(dx * dx + dy * dy + dz * dz);
}
inline bool same_3x4(const float* a, const float* b) { return std::memcmp(a, b, 48) == 0; }
/// The index of the frame before's matrix (of n, 12 floats each) nearest a, by translation, within reach; -1: none (a model
/// first seen, or every one of them too far to be this object)
inline int nearest(const float* a, const float* before, size_t n, float reach) {
    int best = -1;
    float bd = reach;
    for (size_t i = 0; i < n; i++) {
        const float d = moved_by(a, before + i * 12);
        if (d <= bd) bd = d, best = (int)i;
    }
    return best;
}

/// The cameras' buffer, 36 words: this frame's camera (as drawn, jittered), the frame before's (its jitter taken off), this
/// frame's jitter in clip space, the render size
constexpr uint32_t kHeadWords = 36;

} // namespace dlss_actor
