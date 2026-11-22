// Game-free check of dlss_math::fg_camera (NVIDIA DLSS Frame Generation's camera, vk_dlss.cpp dlssg_generate): a camera built
// here from its place, axes and planes, its view-projections made the game's way (OpenGL clip space, row major, clip = M * p),
// and what fg_camera gives back compared with what that camera is, worked out independently below.
//   clang++ -std=c++20 -I.. dlssg_camera_test.cpp -o dlssg_camera_test && ./dlssg_camera_test
#include <algorithm>
#include <cmath>
#include <cstdio>

#include "../dlss_math.h"

namespace {
int failures = 0;

void near(const char* what, float got, float want, float tol = 1e-3f) {
    if (std::fabs(got - want) <= tol * std::max(1.0f, std::fabs(want))) return;
    std::fprintf(stderr, "%s: got %.6f, wanted %.6f\n", what, got, want);
    failures++;
}

// A right-handed OpenGL camera at eye looking at target: world to view, row major (column vectors)
void look_at(const float eye[3], const float target[3], float m[16]) {
    float f[3] = {target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]};
    float n = std::sqrt(f[0] * f[0] + f[1] * f[1] + f[2] * f[2]);
    for (float& v : f) v /= n;
    const float up[3] = {0, 1, 0};
    float s[3] = {f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0]};
    n = std::sqrt(s[0] * s[0] + s[1] * s[1] + s[2] * s[2]);
    for (float& v : s) v /= n;
    const float u[3] = {s[1] * f[2] - s[2] * f[1], s[2] * f[0] - s[0] * f[2], s[0] * f[1] - s[1] * f[0]};
    const float r[16] = {s[0], s[1], s[2], -(s[0] * eye[0] + s[1] * eye[1] + s[2] * eye[2]),
                         u[0], u[1], u[2], -(u[0] * eye[0] + u[1] * eye[1] + u[2] * eye[2]),
                         -f[0], -f[1], -f[2], f[0] * eye[0] + f[1] * eye[1] + f[2] * eye[2],
                         0, 0, 0, 1};
    for (int i = 0; i < 16; i++) m[i] = r[i];
}
// OpenGL's perspective (depth -1 to 1), row major
void perspective(float fovy, float aspect, float zn, float zf, float m[16]) {
    const float t = 1.0f / std::tan(fovy / 2);
    const float r[16] = {t / aspect, 0, 0, 0, 0, t, 0, 0, 0, 0, -(zf + zn) / (zf - zn), -2 * zf * zn / (zf - zn), 0, 0, -1, 0};
    for (int i = 0; i < 16; i++) m[i] = r[i];
}
void apply(const float* m, const float p[4], float o[4]) {
    for (int r = 0; r < 4; r++) o[r] = m[r * 4] * p[0] + m[r * 4 + 1] * p[1] + m[r * 4 + 2] * p[2] + m[r * 4 + 3] * p[3];
}
// A row vector times NGX's matrix (its layout: post-multiplication)
void apply_row(const float* m, const float p[4], float o[4]) {
    for (int c = 0; c < 4; c++) o[c] = p[0] * m[c] + p[1] * m[4 + c] + p[2] * m[8 + c] + p[3] * m[12 + c];
}
// The game's clip space to Vulkan's, done by hand: y down, depth (z + w) / 2
void to_vulkan(const float g[4], float v[4]) { v[0] = g[0], v[1] = -g[1], v[2] = (g[2] + g[3]) * 0.5f, v[3] = g[3]; }
}  // namespace

int main() {
    using namespace mkwvk::dlss_math;
    const float eye0[3] = {120, 40, 300}, eye1[3] = {125, 41, 296};      // (the camera moved and turned a little)
    const float at0[3] = {0, 30, 0}, at1[3] = {10, 28, -4};
    float view0[16], view1[16], proj[16], vp0[16], vp1[16];
    look_at(eye0, at0, view0), look_at(eye1, at1, view1);
    perspective(0.8f, 16.0f / 9.0f, 10.0f, 12800.0f, proj);
    mul4(proj, view0, vp0), mul4(proj, view1, vp1);   // (frame before: 0, this frame: 1)
    FgCamera f{};
    if (!fg_camera(vp1, vp0, proj, false, &f)) {
        std::fprintf(stderr, "fg_camera failed\n");
        return 1;
    }
    // (the camera's place and axes: this frame's camera, eye1 looking at at1)
    near("pos.x", f.pos[0], eye1[0]), near("pos.y", f.pos[1], eye1[1]), near("pos.z", f.pos[2], eye1[2]);
    float d[3] = {at1[0] - eye1[0], at1[1] - eye1[1], at1[2] - eye1[2]};
    const float dn = std::sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
    near("fwd.x", f.fwd[0], d[0] / dn), near("fwd.y", f.fwd[1], d[1] / dn), near("fwd.z", f.fwd[2], d[2] / dn);
    near("up.y > 0", f.up[1] > 0.9f ? 1.0f : 0.0f, 1.0f);
    near("right . fwd", f.right[0] * f.fwd[0] + f.right[1] * f.fwd[1] + f.right[2] * f.fwd[2], 0.0f);
    // (a world point: its Vulkan clip position this frame, through NGX's clip_to_prev, is where it was in the frame before)
    const float pts[3][4] = {{0, 30, 0, 1}, {40, 10, -60, 1}, {-30, 55, 120, 1}};
    for (const auto& p : pts) {
        float g0[4], g1[4], v0[4], v1[4], got[4], back[4];
        apply(vp0, p, g0), apply(vp1, p, g1), to_vulkan(g0, v0), to_vulkan(g1, v1);
        apply_row(f.clip_to_prev, v1, got);
        for (int i = 0; i < 3; i++) near("clip_to_prev", got[i] / got[3], v0[i] / v0[3]);
        apply_row(f.prev_to_clip, v0, back);
        for (int i = 0; i < 3; i++) near("prev_to_clip", back[i] / back[3], v1[i] / v1[3]);
        // (view space to Vulkan clip: the point in this frame's view, through view_to_clip; and back through clip_to_view)
        float vw[4], c[4], vb[4];
        apply(view1, p, vw);
        apply_row(f.view_to_clip, vw, c);
        for (int i = 0; i < 3; i++) near("view_to_clip", c[i] / c[3], v1[i] / v1[3]);
        apply_row(f.clip_to_view, v1, vb);
        for (int i = 0; i < 3; i++) near("clip_to_view", vb[i] / vb[3], vw[i] / vw[3]);
        // (Vulkan depth in 0..1: in front of the camera)
        near("depth in 0..1", (v1[2] / v1[3] >= 0 && v1[2] / v1[3] <= 1) ? 1.0f : 0.0f, 1.0f);
    }
    // (ours: the same matrices in our layout, column vectors)
    FgCamera g{};
    fg_camera(vp1, vp0, proj, true, &g);
    for (int i = 0; i < 4; i++)
        for (int j = 0; j < 4; j++) near("ours = transpose", g.clip_to_prev[i * 4 + j], f.clip_to_prev[j * 4 + i]);
    if (failures) {
        std::fprintf(stderr, "%d failures\n", failures);
        return 1;
    }
    std::printf("dlssg camera: all checks passed\n");
    return 0;
}
