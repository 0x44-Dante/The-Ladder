#!/usr/bin/env python3
# Builds preview.png, the GitHub social preview card for this repository.
#
# GitHub does not store the social preview in the repo; it is uploaded once
# under Settings -> Social preview. The generator lives here anyway, because
# an image whose source is missing cannot be corrected, only replaced -- and
# unlike the papers, this source is small enough to carry without noise.
#
# Layout follows the argus-lite card: 1280x640, dark terminal window, a
# command line, the name, two lines of what it is, the cascade as the row of
# terms, and the credo where argus-lite puts its tagline.
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "preview.png")

W, H = 1280, 640
BG = (13, 17, 23)              # page
CARD = (22, 27, 34)            # terminal window
BORDER = (48, 54, 61)
DOT_R, DOT_Y, DOT_G = (255, 95, 87), (254, 188, 46), (40, 200, 64)
GREEN = (63, 185, 80)          # prompt, and the closing half-line
WHITE = (230, 237, 243)
GREY = (139, 148, 158)         # second description line
BLUE = (88, 166, 255)          # the cascade
DIM = (110, 118, 129)          # the credo

# The card was drawn on Windows with these faces. Elsewhere the script
# falls back to whatever the system has, which changes the metrics: the
# published preview.png is the Windows rendering, and a rebuild on Linux
# will not reproduce it byte for byte. Said here rather than discovered.
F = os.environ.get("LADDER_FONT_DIR", "C:/Windows/Fonts/")


def _face(names, size):
    for n in names:
        try:
            return ImageFont.truetype(F + n, size)
        except OSError:
            pass
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            pass
    return ImageFont.load_default()


mono = lambda s: _face(["consola.ttf", "DejaVuSansMono.ttf"], s)
monob = lambda s: _face(["consolab.ttf", "DejaVuSansMono-Bold.ttf"], s)
sans = lambda s: _face(["segoeui.ttf", "DejaVuSans.ttf"], s)

im = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(im)

# The terminal window.
d.rounded_rectangle([70, 60, 1210, 580], radius=14, fill=CARD, outline=BORDER,
                    width=1)
for x, c in ((110, DOT_R), (144, DOT_Y), (178, DOT_G)):
    d.ellipse([x - 9, 89, x + 9, 107], fill=c)

# The command.
d.text((110, 146), "$ python ladder.py trial 2GB", font=mono(23), fill=GREEN)

# The name.
d.text((108, 202), "THE LADDER", font=monob(62), fill=WHITE)

# What it is.
d.text((110, 305), "A test rig for 64-bit mixers that does not saturate.",
       font=sans(27), fill=WHITE)
d.text((110, 350), "Counter streams in disguise. How far it gets is the "
                   "measurement.", font=sans(27), fill=GREY)

# The cascade.
# Drawn piece by piece so the separators stay dim and the stages stay blue.
x, y = 110, 414
for i, wort in enumerate(("gauntlet", "smoke", "depth", "diploma")):
    if i:
        d.text((x, y), "|", font=mono(24), fill=DIM)
        x += d.textlength("|", font=mono(24)) + 22
    d.text((x, y), wort, font=mono(24), fill=BLUE)
    x += d.textlength(wort, font=mono(24)) + 22

# The credo.
d.text((110, 464), "Measuring instruments that do not question themselves lie.",
       font=mono(19), fill=DIM)

# The signature.
d.text((110, 516), "0x44 Zero Systems", font=mono(21), fill=WHITE)
d.text((110 + d.textlength("0x44 Zero Systems  ", font=mono(21)), 516),
       "-- 256 streams x 1 TB, not one failure", font=mono(21), fill=GREEN)

im.save(TARGET, "PNG", optimize=True)
print(f"written: {TARGET}  ({os.path.getsize(TARGET) // 1024} KB, {W}x{H})")
