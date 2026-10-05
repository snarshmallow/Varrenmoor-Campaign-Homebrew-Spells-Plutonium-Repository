"""Shop sign textures: wooden board, shop name and a small tagline, with an optional icon from textures/icons/<kind>.png (light-on-transparent)
placed on the left. Re-run after adding icons:  python make_signs.py  ->  sign_<kind>.png"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SIGNS = {
    "inn": ("MOTTLE'S MUGS", "The Last Respite Before Further Administrative Action"),
    "forge": ("BROKKA'S FORGE", "Smithing - Essences - Appraisals"),
    "clinic": ("DR. PIMM'S CLINIC", "Adaptations by Appointment"),
    "rune": ("SCRATCH & CO.", "Rune Repair - Glyph Copying"),
}
# small utility plates (not shops): plain iron plates with stencilled text
UTIL = {
    "tube": "TUBE STATION 4", "dock": "WAREHOUSE 7 - REAR DOCK", "lodge": "LODGINGS BY THE NIGHT", "cart": "BONE CARTAGE", "tallow": "TALLOW & LAMP OIL",
    "resid": "RESIDENTS ONLY", "trolley": "MIND THE TROLLEYS", "notice": "NOTICES EXPIRE WITHOUT NOTICE", "intake": "INTAKE 3", "wash": "WASH & FOLD", "ledger": "LEDGERS - 2ND FLOOR",
}
W, H = 2048, 700
FONT = "C:/Windows/Fonts/georgiab.ttf"


def fit(draw, text, size, maxw):
    while size > 20:
        f = ImageFont.truetype(FONT, size)
        if draw.textlength(text, font=f) <= maxw:
            return f
        size -= 4
    return ImageFont.truetype(FONT, 20)


for kind, (title, sub) in SIGNS.items():
    img = Image.new("RGB", (W, H), (58, 38, 24))
    d = ImageDraw.Draw(img)
    d.rectangle([14, 14, W - 14, H - 14], outline=(176, 140, 60), width=14)
    d.rectangle([44, 44, W - 44, H - 44], outline=(110, 84, 40), width=5)
    x0 = 90
    icon = HERE / "icons" / f"{kind}.png"
    if icon.exists():
        ic = Image.open(icon).convert("L")                  # white glyph on black: use it as the mask
        s = H - 190
        ic = ic.resize((s, s))
        img.paste(Image.new("RGB", ic.size, (232, 214, 170)), (90, 95), ic)
        x0 = 90 + s + 60
    maxw = W - x0 - 90
    f1 = fit(d, title, 190, maxw)
    f2 = fit(d, sub, 90, maxw)
    d.text((x0 + maxw / 2, H * 0.40), title, font=f1, fill=(236, 218, 170), anchor="mm")
    d.line([(x0 + 40, H * 0.60), (x0 + maxw - 40, H * 0.60)], fill=(176, 140, 60), width=5)
    d.text((x0 + maxw / 2, H * 0.74), sub, font=f2, fill=(200, 180, 140), anchor="mm")
    img.save(HERE / f"sign_{kind}.png")
print("ok")


for key, text in UTIL.items():
    img = Image.new("RGB", (1024, 300), (46, 48, 52))
    d = ImageDraw.Draw(img)
    d.rectangle([8, 8, 1016, 292], outline=(120, 124, 130), width=8)
    f = fit(d, text, 120, 900)
    d.text((512, 150), text, font=f, fill=(206, 208, 200), anchor="mm")
    img.save(HERE / f"plate_{key}.png")
