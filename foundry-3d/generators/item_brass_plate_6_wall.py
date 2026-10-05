"""Loot item model: Brass Plate '6' as an upright wall plate (separate file name from the earlier flat version so cached copies are not reused)."""
from _items import build_item

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange/Items"


def build(k):
    build_item(k, "brass_plate_6")
