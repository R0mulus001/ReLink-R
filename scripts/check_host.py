"""(ReLink-R 0.0.5) Compile-checks the game's runtime (host/*.c) without game data, as a player's PC compiles it.

The runtime is compiled on the player's PC by nx2/build.py, after the lift, so a mistake in host/*.c used to show only
there, in the middle of an install. This generates the runtime's headers (nx2/rtgen.py), stands in empty files for the
headers the lift writes from the game, and runs the compiler in syntax-only mode on every file that needs no third-party
library.

    python -I scripts/check_host.py <clang> [extra clang flags...]

On Windows (CI) <clang> is llvm-mingw's x86_64-w64-mingw32-clang; elsewhere the plain clang with host/posix first.
Exit status 1 when a file does not compile.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOST = os.path.join(ROOT, "host")
SKIP = {"nn_codec.c", "nn_video.c"}   # (opus, ffmpeg: their headers come with the build's dependencies)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    clang, extra = sys.argv[1], sys.argv[2:]
    sys.path.insert(0, os.path.join(ROOT, "nx2"))
    import rtgen
    work = tempfile.mkdtemp(prefix="relink_host_check_")
    try:
        rt = rtgen.write(os.path.join(work, "rt64"))
        # (the headers a64.h includes: the repository's own where it has them, an empty stand-in for what the lift writes)
        with open(os.path.join(rt, "a64.h"), encoding="utf-8") as f:
            wanted = [line.split('"')[1] for line in f if line.startswith('#include "')]
        for h in wanted:
            if os.path.exists(os.path.join(rt, h)):
                continue
            found = None
            for d, _, files in os.walk(ROOT):
                if ".git" in d or "_deps" in d:
                    continue
                if h in files:
                    found = os.path.join(d, h)
                    break
            if found:
                shutil.copy(found, os.path.join(rt, h))
            else:
                open(os.path.join(rt, h), "w").close()
        posix = [] if os.name == "nt" or "mingw" in os.path.basename(clang) else ["-I" + os.path.join(HOST, "posix"), "-D_GNU_SOURCE"]
        target = ["-fms-extensions", "-D_CRT_SECURE_NO_WARNINGS"] if not posix else []
        flags = target + posix + ["-I" + HOST, "-I" + rt, "-fsyntax-only", "-Wno-everything", "-mcx16", "-DA64_POLLING"] + extra
        skip = SKIP | ({"display.c", "mf_av1.c"} if posix else set())   # (Windows-only: Linux builds take host/posix's)
        bad = 0
        for name in sorted(os.listdir(HOST)):
            if not name.endswith(".c") or name in skip:
                continue
            r = subprocess.run([clang] + flags + [os.path.join(HOST, name)], capture_output=True, text=True)
            if r.returncode:
                bad += 1
                print("FAILED %s\n%s" % (name, (r.stderr or r.stdout)[-3000:]), flush=True)
            else:
                print("ok     %s" % name, flush=True)
        print("%d file(s) did not compile" % bad if bad else "every host file compiles", flush=True)
        return 1 if bad else 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
