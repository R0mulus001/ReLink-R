// The game's start-up screen (gpu/vk/vk_startup_paint.h) at a few moments, into BMP files: for the Snapshots workflow
#include <windows.h>
#include <cstdio>
#include <string>
#include "vk_startup_paint.h"

static void save(const char* path, const uint32_t* bits, int w, int h) {
    BITMAPFILEHEADER fh{};
    BITMAPINFOHEADER ih{};
    ih.biSize = sizeof ih, ih.biWidth = w, ih.biHeight = -h, ih.biPlanes = 1, ih.biBitCount = 32, ih.biCompression = BI_RGB;
    fh.bfType = 0x4D42, fh.bfOffBits = sizeof fh + sizeof ih, fh.bfSize = fh.bfOffBits + (DWORD)w * h * 4;
    FILE* f = std::fopen(path, "wb");
    if (!f) return;
    std::fwrite(&fh, sizeof fh, 1, f), std::fwrite(&ih, sizeof ih, 1, f), std::fwrite(bits, 4, (size_t)w * h, f);
    std::fclose(f);
}

int main(int argc, char** argv) {
    const std::string dir = argc > 1 ? argv[1] : ".";
    const int w = 1280, h = 720;
    BITMAPINFO bi{};
    bi.bmiHeader.biSize = sizeof bi.bmiHeader, bi.bmiHeader.biWidth = w, bi.bmiHeader.biHeight = -h, bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 32, bi.bmiHeader.biCompression = BI_RGB;
    void* bits = nullptr;
    HDC dc = CreateCompatibleDC(nullptr);
    HBITMAP bmp = CreateDIBSection(dc, &bi, DIB_RGB_COLORS, &bits, nullptr, 0);
    SelectObject(dc, bmp);
    struct Moment { const char* name; double fraction; const char* pct; const char* right; const char* label; };
    const Moment moments[] = {{"start", 0.0, "0", "", "LOADING"}, {"half", 0.5, "50", "about 6 min left", "LOADING"},
                              {"late", 0.86, "86", "about 1 min left", "LOADING"}, {"out", 1.0, "", "", "STARTING"}};
    for (const Moment& m : moments) {
        mkwvk::StartupView v;
        v.version = "v0.0.3-dev", v.label = m.label, v.pct = m.pct, v.right = m.right, v.gpu = "NVIDIA GeForce RTX 3080";
        v.stage = 1, v.anim = 4.0;
        for (int i = 0; i < 40; i++) {   // (the sword slides to its number over a few frames)
            v.fraction = m.fraction;
            v.anim += 0.1;
            mkwvk::paint_startup_view(dc, w, h, 0, v, (uint32_t*)bits);
        }
        GdiFlush();
        save((dir + "\\startup-" + m.name + ".bmp").c_str(), (const uint32_t*)bits, w, h);
        std::printf("startup-%s.bmp\n", m.name);
    }
    return 0;
}
