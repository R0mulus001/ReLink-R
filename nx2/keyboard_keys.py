"""(ReLink-R 0.0.14) The keyboard button prompts: which of Kenney's glyphs each key shows. Data only, standard library.

After Hookshot nx2/prompt_keys.py (b2456c66, #2435, J; co-authored by Needicla and Claude Opus 5.5) as HeyListen took it
(433c43a0), GPL-3.0: the same key table. ReLink-R's bindings are Windows virtual-key codes (relink_options.ini key_<button>=<first>,
<second>; host/nn_hid.c), as Hookshot's are. nx2/button_glyphs.py puts each key's glyph in the keyboard font at KEY_BASE + its
code, and host/prompts.c points each Switch button's code point at the glyph of the first key bound to it.
"""

KEY_BASE = 0xF7C0   # (U+F7C0..U+F8BF: a Private Use range none of the game's fonts uses; one code a virtual-key code 0..255)

# Windows virtual-key codes (learn.microsoft.com/windows/win32/inputdev/virtual-key-codes) -> Kenney's glyph name after
# "keyboard_" ("/name": the whole name)
KEYS = {
    0x01: "/mouse_left", 0x02: "/mouse_right", 0x04: "/mouse_scroll", 0x05: "/mouse_side_back", 0x06: "/mouse_side_forward",
    0x08: "backspace_icon", 0x09: "tab_icon", 0x0D: "return", 0x10: "shift_icon", 0x11: "ctrl", 0x12: "alt", 0x13: "pause",
    0x14: "capslock_icon", 0x1B: "escape", 0x20: "space_icon", 0x21: "page_up", 0x22: "page_down", 0x23: "end", 0x24: "home",
    0x25: "arrow_left", 0x26: "arrow_up", 0x27: "arrow_right", 0x28: "arrow_down", 0x2C: "printscreen", 0x2D: "insert",
    0x2E: "delete", 0x5B: "win", 0x5C: "win", 0x6A: "asterisk", 0x6B: "numpad_plus", 0x6D: "minus", 0x6E: "period",
    0x6F: "slash_forward", 0x90: "numlock", 0x91: "scroll_lock", 0xA0: "shift_icon", 0xA1: "shift_icon", 0xA2: "ctrl",
    0xA3: "ctrl", 0xA4: "alt", 0xA5: "alt", 0xBA: "semicolon", 0xBB: "equals", 0xBC: "comma", 0xBD: "minus", 0xBE: "period",
    0xBF: "slash_forward", 0xC0: "tilde", 0xDB: "bracket_open", 0xDC: "slash_back", 0xDD: "bracket_close", 0xDE: "apostrophe",
}
KEYS.update({0x30 + i: str(i) for i in range(10)})   # the digits
KEYS.update({0x60 + i: str(i) for i in range(10)})   # (the numpad's digits: Kenney has none of their own)
KEYS.update({0x41 + i: chr(0x61 + i) for i in range(26)})   # the letters
KEYS.update({0x70 + i: f"f{i + 1}" for i in range(12)})
UNKNOWN = "any"   # (a key code Kenney has no key for: its "ANY" key)


def kenney_name(code):
    n = KEYS.get(code, UNKNOWN)
    return n[1:] if n.startswith("/") else "keyboard_" + n
