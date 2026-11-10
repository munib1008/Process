"""Shrink the draw.io-rendered flow previews (palette PNG, max 2600 px wide). Run after tools/render_flow_previews.js."""
import glob
import os
import sys

from PIL import Image

folder = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "source_documents", "flows")
before = after = 0
for f in glob.glob(os.path.join(folder, "*.png")):
    before += os.path.getsize(f)
    im = Image.open(f).convert("RGB")
    if im.width > 2600:
        im = im.resize((2600, int(im.height * 2600 / im.width)), Image.LANCZOS)
    im.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(f, "PNG", optimize=True)
    after += os.path.getsize(f)
print(f"{before / 1e6:.1f} MB -> {after / 1e6:.1f} MB")
