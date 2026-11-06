"""Sample 11x17 landscape plan -> illustrator/out/test_guide.svg"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib_svg import LayeredSVG

OUT = os.path.join(os.path.dirname(__file__), "..", "out", "test_guide.svg")

s = LayeredSVG(17, 11)
W, H = s.w, s.h
m = 36  # margin
# 5-ft grid at 1 in = 10 ft  -> 36 pt cells
cell = 36
x = m
while x <= W - m:
    s.line("Grid", x, m, x, H - m, stroke_w=0.25)
    x += cell
y = m
while y <= H - m:
    s.line("Grid", m, y, W - m, y, stroke_w=0.25)
    y += cell
# Building outline, interior walls, door gaps
s.rect("Buildings", 144, 108, 432, 288, stroke_w=1.5)
s.line("Walls", 360, 108, 360, 220)
s.line("Walls", 360, 260, 360, 396)
s.line("Walls", 144, 252, 360, 252)
# Road and river
s.polyline("Roads", [(m, 450), (300, 430), (600, 450), (W - m, 420)], stroke_w=1)
s.polyline("Roads", [(m, 470), (300, 450), (600, 470), (W - m, 440)], stroke_w=1)
s.polyline("Water", [(700, m), (680, 200), (720, 400), (700, H - m)], stroke_w=1, dash="6 3")
s.text("Labels", 200, 150, "Main Hall")
s.text("Labels", 400, 150, "Kitchen")
s.text("Labels", 200, 290, "Cellar stair")
s.text("Notes", m, 24, "TEST GUIDE - 11x17 landscape, 1 in = 10 ft", size=10)
s.scale_bar(m + 4, H - 20, feet_per_inch=10, total_feet=50)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
s.write(OUT)
print("wrote", os.path.abspath(OUT))
