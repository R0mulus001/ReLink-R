# Kenney Input Prompts: Keyboard & Mouse

The keyboard and mouse font of Kenney's Input Prompts 1.5 (https://kenney.nl/assets/input-prompts), as released: CC0
(License.txt, the release's own). The same file Hookshot (third_party/kenney_input_keyboard, #2435) and HeyListen ship.

- kenney_input_keyboard_&_mouse.otf (Keyboard & Mouse/Fonts)

ReLink-R reads it only at development time (tools/prompts/kenney_contours.py writes nx2/keyboard_glyphs.py); a player's build
uses those outlines and never opens the font.
