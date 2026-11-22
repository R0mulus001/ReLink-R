// NVIDIA DLSS Super Resolution, or (relink) AMD FSR 3.1, in place of OoT's gameplay upscale network (vk_dlss.cpp). DLSS is
// built in only with NVIDIA's NGX SDK (RELINK_NGX, scripts/ngx_sdk.py: Linux and Windows); without it these say DLSS is not
// there. FSR is in every build, where AMD's runtime loads (vk_fsr.h). The names say dlss for either.
#pragma once

#include <vector>

#include "vk_internal.h"

namespace mkwvk {

struct Texture;

/// Whether this build has DLSS in it (RELINK_NGX)
bool dlss_built();
/// Why DLSS cannot be chosen here (the Insert menu's Upscaler row says it), DLSS_OK when it can or is not known yet
enum DlssWhy { DLSS_OK, DLSS_NOT_BUILT, DLSS_ENV_OFF, DLSS_NEEDS_RTX, DLSS_NEEDS_DRIVER, DLSS_NO_RUNTIME, DLSS_WHY_COUNT };
DlssWhy dlss_why();
/// Asks NGX once whether DLSS runs on this device, so dlss_why knows before the first upscale (the menu, when it opens).
/// Nothing off an NVIDIA device with NGX's extensions, or in a build without DLSS
void dlss_probe();
/// What is asked for: 0 off, 1 DLSS (in place of the game's gameplay upscale, at any render share), 2 DLAA (anti-aliasing at the render size, the 3D at full scale),
/// 3 AMD FSR (as DLSS), 4 AMD FSR native AA (as DLAA): the Insert menu's Upscaler row (opts.dlss), or RX_VK_DLSS=0 to 4 over
/// it. 0 when dlss_why() (DLSS, DLAA) or fsr_why() (FSR) says it cannot run
int dlss_mode();
bool dlss_wanted();   // (dlss_mode() != 0)
/// DLAA or FSR native AA: the 3D drawn at full scale, whatever the Render resolution row says (rx_option 2 and 3)
bool dlss_full_scale();
/// The instance's extensions DLSS needs, added to `want` when the loader has them (all: what it has)
void dlss_instance_extensions(std::vector<const char*>& want, const std::vector<VkExtensionProperties>& all);
/// The device's extensions DLSS needs, added to `want` when the device has them
void dlss_device_extensions(std::vector<const char*>& want, const std::vector<VkExtensionProperties>& all);
/// A draw into a scene-sized target (colour target 0 and the depth target), with the vertex stage's uniform buffer 3 at
/// `camera` (its size): the camera of the frame, when that buffer holds one
void dlss_note_scene_draw(const Texture* color0, uint32_t width, uint32_t height, Texture* depth, uint64_t camera,
                          uint64_t camera_size);
/// A skinned draw into a scene-sized target (vk_draw.cpp finds them by their vertex layout): what DLSS's motion needs to draw
/// it again with this frame's bones and the frame before's (actor motion: Link, the others, what moves by itself)
struct DlssSkin {
    const Texture* depth = nullptr;   // (its depth target: only the scene's are taken)
    uint64_t vbuf = 0, vsize = 0;     // (vertex stream 0)
    uint32_t stride = 0;
    uint32_t pos = 0;                 // (byte offsets in a vertex: the position, RGB32F or RGBA16F)
    uint32_t joints[2]{}, weights[2]{};   // (RGBA16UI or RGBA8UI joints and RGBA8 weights, four a set; sets: 1 or 2)
    int sets = 0;
    uint32_t formats = 0;             // (dlss_actor::Push::formats)
    uint64_t ibuf = 0;
    int itype = 0, count = 0, base_vertex = 0;
    uint64_t bones = 0, bones_size = 0;   // (the palette: 3 x 4 row-major matrices, model space to the camera's world)
    uint64_t object = 0, object_size = 0; // (the object's buffer: its origin at 0x40)
    uint64_t program = 0;
};
void dlss_note_skinned_draw(const DlssSkin& k);
/// (0.7.9.3) A rigid draw into a scene-sized target: no joints, the object's buffer (k.object) starting with its 3 x 4 world
/// matrix. Where that matrix moved since the frame before, the draw is drawn again with both (vk_dlss.cpp actor_motion)
void dlss_note_rigid_draw(const DlssSkin& k);
/// (relink, 0.7.9.3) The see-through mask (vk_dlss.cpp; RX_VK_DLSS_MASK=0: none): vk_draw.cpp's draw before a blended draw into a
/// scene-like target (B10G11R11 with a depth: color0, its view and size), outside a pass (it ends the open one); and end_pass
/// as a pass into such a target ends
void dlss_scene_blended(VkCommandBuffer cmd, Texture* color0, VkImageView view, uint32_t w, uint32_t h);
/// (relink, 0.7.9.3) A draw of the game's post chain (vk_draw.cpp, program key and its first target): the composite (scene,
/// bloom, exposure, ACES) is noted, so the upscalers can take the picture before the game's SMAA
struct NvnState;
void dlss_note_post_draw(VkCommandBuffer cmd, uint64_t key, Texture* color0, uint32_t w, uint32_t h, const NvnState& st);
void dlss_scene_pass_end(VkCommandBuffer cmd, Texture* color0, VkImageView view, uint32_t w, uint32_t h);

/// A gameplay upscale's dispatch (program `key`; vk_draw.cpp's dlss_stand_in finds them: the 4/3 network fd029a317a9a4b94 at
/// the game's usual 3/4, the same-size pass 9dc98871eb7fc101 at full size, and one network of its own for each other share): its input as it samples it (in, in_view) and its output's storage
/// view (out at level 0). known: one of the gameplay networks by its key (the 4/3 one, the full-size pass); else a network of
/// that shape (the fixed shares' own), taken only when its input is this frame's scene and its output the picture, and left
/// to run without a word otherwise. true: DLSS wrote the output (the dispatch is left out); false: the network runs, the
/// reason logged
bool dlss_upscale(VkCommandBuffer cmd, uint64_t key, bool known, Texture* in, VkImageView in_view, Texture* out,
                  VkImageView out_view, uint32_t out_level);

/// Once a frame (the game's present): after 120 frames without DLSS (off, or the upscale not taken) its feature, images and
/// deferred frees are let go, so its video memory comes back. Nothing to do costs one atomic load
void dlss_idle();
/// (relink, 0.7.9.3) the Sharpness row sharpened the upscaler's 3D picture under the HUD in the last frames: the window's pass
/// leaves its own sharpening out
bool upscaler_sharpens();

/// For the renderer's status line (vk_replay.cpp status_tick): while an upscaler draws, its details since the last call
/// into b ("; DLSS: jitter ..., actor motion ..., its images ... MB") and its dlss_mode() (1 to 4); else 0 and b left alone
int dlss_status(char* b, size_t n);

/// The scene's width (axis 0) or height (1) for the host's camera jitter (nx2/oot_jitter.py, HOS_OPT_DLSS_JITTER_W and _H): 0 when
/// there is to be none (DLSS or FSR not drawing, or RX_VK_DLSS_JITTER=0). Axis 2: the jitter sequence's length for DLSS's
/// scale (dlss_jitter_phases, HOS_OPT_DLSS_JITTER_PHASES), or FSR's (FFX's own count)
uint32_t dlss_jitter_size(int axis);

/// (relink, 0.7.9.3) NVIDIA DLSS Frame Generation (NGX, RTX 40 series and later; Windows), in place of ReLink's own frame
/// interpolation (vk_framegen.cpp) when the Frame generator row asks for it (opts.fg_kind 1; RX_VK_DLSSG=0 / 1 over it). It
/// takes what DLSS, DLAA or FSR were given for the frame (the depth, the motion, the camera), so it runs only while one of
/// them is the Upscaler; else, and wherever it cannot run, ReLink's own makes the frames.
enum DlssgWhy { DLSSG_OK, DLSSG_UNKNOWN, DLSSG_NOT_BUILT, DLSSG_NEEDS_RTX40, DLSSG_NEEDS_DRIVER, DLSSG_NO_RUNTIME, DLSSG_FAILED,
                DLSSG_WHY_COUNT };
DlssgWhy dlssg_why();
/// The most frames it makes between two of the game's (1 on the RTX 40 series, up to 3 on the RTX 50), when it runs here
int dlssg_max_frames();
/// The Frame generator row (or RX_VK_DLSSG) asks for DLSS Frame Generation
bool dlssg_asked();
/// Records DLSS Frame Generation's frames between the last picture it was given and this one (back: RGBA8, w x h, GENERAL),
/// n of them into out[0..n) (the same format and size, GENERAL), the first one the earliest. reset: the frame before is not
/// this one's (a gap, a first frame). Returns the frames recorded: 0 when it does not run for this frame (not asked, not here,
/// no upscale of ours with this frame's inputs), and the caller makes its own
int dlssg_generate(VkCommandBuffer cmd, VkImage back, VkImageView back_view, const VkImage* out, const VkImageView* out_views,
                   int n, uint32_t w, uint32_t h, bool reset);
/// For the status line: what it made since the last call into b, or nothing
void dlssg_status(char* b, size_t n);

/// (relink) The mip bias the game's mipmapped textures are sampled with while DLSS or FSR scales the 3D up (0 otherwise):
/// log2(render width / output width) - 1, in quarter steps (vk_draw.cpp sampler_make)
float upscaler_lod_bias();

} // namespace mkwvk
