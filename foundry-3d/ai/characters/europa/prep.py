"""Step 2: hand-edit the matte into a standing, staff-free paste-up plus an inpaint mask for SDXL.
All coordinates are in the 1024x1024 source frame; the result is placed on a 768x1152 canvas (source x 136..904, shifted down 24 px).
  python prep.py  ->  europa_pasteup.png (RGB on grey), europa_pasteup_rgba.png, europa_mask.png (white = SDXL repaints)
Edits: staff and its top behind the shoulder removed; pangolin removed; billowing cape cut back and repainted hanging down;
her right hand (viewer's left) replaced by a mirrored copy of her relaxed left hand; walking back leg replaced by a copy of the
front leg so she stands with both feet down; boots extended to soles (the source crops them).
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
GREY = (200, 200, 200)
X0, DY, W, H = 136, 24, 768, 1152

m = Image.open(HERE / "europa_matte.png").convert("RGBA")
src = m.copy()
mask = Image.new("L", m.size, 0)            # SDXL repaint mask in source frame
md = ImageDraw.Draw(mask)


def erase(poly):
    a = m.getchannel("A")
    ImageDraw.Draw(a).polygon(poly, fill=0)
    m.putalpha(a)
    md.polygon(poly, fill=255)


def paint(poly, rgb, to_mask=True):
    ImageDraw.Draw(m).polygon(poly, fill=rgb + (255,))
    if to_mask:
        md.polygon(poly, fill=255)


# staff: shaft from the bottom-left end up through her hand, and the top poking out behind her left shoulder
erase([(40, 915), (90, 960), (352, 600), (312, 572)])
erase([(570, 200), (632, 214), (622, 268), (580, 262)])
# pangolin (body, head, tail) and the walking back leg below the skirt
erase([(0, 800), (420, 690), (440, 700), (492, 785), (492, 1024), (0, 1024)])
erase([(592, 930), (720, 930), (720, 1024), (592, 1024)])
erase([(566, 885), (640, 885), (640, 975), (566, 975)])       # dark boot-heel blob (back leg / pangolin) right of the front boot
# billowing cape: cut everything right of a line from the shoulder down, then paint it hanging
erase([(688, 300), (1024, 300), (1024, 1024), (772, 1024), (772, 830)])
erase([(700, 830), (1024, 830), (1024, 1024), (600, 1024), (600, 930)])
cape = Image.new("RGBA", m.size, (0, 0, 0, 0))           # painted on a layer BEHIND her (arm and hand stay in front)
cpoly = [(650, 300), (688, 300), (722, 470), (748, 640), (764, 800), (752, 836), (700, 846), (668, 800), (672, 640), (660, 470)]
ImageDraw.Draw(cape).polygon(cpoly, fill=(32, 72, 58, 255))
ImageDraw.Draw(cape).line([(688, 300), (722, 470), (748, 640), (764, 800), (752, 836)], fill=(170, 130, 40, 255), width=5)
cape.alpha_composite(m)
m = cape
md.polygon([(690, 300), (730, 300), (790, 840), (700, 860), (690, 700)], fill=255)

# right hand (viewer's left): mirrored copy of her relaxed left hand
erase([(268, 548), (352, 548), (352, 648), (268, 648)])
hpoly = [(637, 522), (682, 527), (697, 567), (696, 592), (690, 617), (662, 616), (652, 595), (635, 594), (632, 572), (637, 542)]
ha = Image.new("L", m.size, 0)
ImageDraw.Draw(ha).polygon(hpoly, fill=255)
hand = src.crop((626, 515, 702, 622))
hand.putalpha(ha.crop((626, 515, 702, 622)))
m.alpha_composite(hand.transpose(Image.FLIP_LEFT_RIGHT), (272, 540))
md.rectangle((262, 540, 360, 656), fill=255)

# back leg: copy of the front leg (trouser + boot), shifted left, pasted behind the front leg
leg = m.crop((488, 770, 588, 1024)).resize((100, 324), Image.LANCZOS)   # front leg, stretched up to reach under the skirt
legl = Image.new("RGBA", m.size, (0, 0, 0, 0))
legl.alpha_composite(leg, (386, 700))
legl.alpha_composite(m)                          # skirt, tassels and the real front leg stay in front of the copy
m = legl
md.rectangle((386, 724, 486, 1000), fill=0)      # keep the copied leg as is (the pangolin erase had masked it)
md.rectangle((380, 684, 492, 724), fill=255)     # seam where the copy meets the skirt

# pangolin tail scales left around the boots (yellow, low blue) -> transparent
a = np.array(m)
yy, xx = np.mgrid[0:1024, 0:1024]
r, g, b = (a[..., i].astype(int) for i in range(3))
tail = (yy > 940) & (r > 90) & (g > 60) & (b < 0.45 * r)
a[tail, 3] = 0
m = Image.fromarray(a)
mask = Image.fromarray(np.maximum(np.array(mask), np.where(tail, 255, 0).astype(np.uint8)))
md = ImageDraw.Draw(mask)

# canvas: grey, taller, room for the soles
out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
out.alpha_composite(m.crop((X0, 0, X0 + W, 1024)), (0, DY))
mk = Image.new("L", (W, H), 0)
mk.paste(mask.crop((X0, 0, X0 + W, 1024)), (0, DY))
d, dm = ImageDraw.Draw(out), ImageDraw.Draw(mk)
for x0 in (392 - X0, 500 - X0):                 # boot toes down to the soles (the source crops them at y 1024)
    boot = [(x0 + 4, 1016 + DY), (x0 + 82, 1016 + DY), (x0 + 86, 1030 + DY), (x0 + 80, 1040 + DY), (x0 + 6, 1040 + DY), (x0, 1030 + DY)]
    d.polygon(boot, fill=(58, 44, 34, 255))
    d.rectangle((x0 + 2, 1038 + DY, x0 + 84, 1043 + DY), fill=(30, 24, 20, 255))
dm.rectangle((384 - X0 - 10, 1004 + DY, 596 - X0 + 10, 1056 + DY), fill=255)
mk = mk.filter(ImageFilter.MaxFilter(13)).filter(ImageFilter.GaussianBlur(4))

out.save(HERE / "europa_pasteup_rgba.png")
flat = Image.new("RGBA", (W, H), GREY + (255,))
flat.alpha_composite(out)
flat.convert("RGB").save(HERE / "europa_pasteup.png")
mk.save(HERE / "europa_mask.png")
print("wrote pasteup + mask", out.size)
