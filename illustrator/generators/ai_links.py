"""List the linked-image paths recorded in saved .ai files (XMP manifest) and whether each file still exists.
Usage: python ai_links.py illustrator/out/*.ai    (offline; no Illustrator needed)"""
import os, re, sys

def links(path):
    with open(path, "rb") as f:
        b = f.read()
    return sorted({m.decode("utf8", "replace").strip() for m in re.findall(rb"stRef:filePath>([^<]+)", b)} - {""})

if __name__ == "__main__":
    bad = 0
    for ai in sys.argv[1:]:
        for p in links(ai):
            ok = os.path.exists(p); bad += not ok
            print(("OK   " if ok else "MISS ") + os.path.basename(ai) + "  " + p)
    sys.exit(1 if bad else 0)
