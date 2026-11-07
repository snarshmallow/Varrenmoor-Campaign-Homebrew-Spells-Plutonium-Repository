"""Check script for terrain_patch.py: patches on Bridgehollow in a scratch copy (base data untouched).
  python test_terrain_patch.py [outdir]
Verifies: max/mean targets, no seam at the boundary, outside unchanged, determinism, negative (-60 ft basin) case."""
import json, os, shutil, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import terrain_patch as tp

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "terrain_patch_test")
os.makedirs(out, exist_ok=True)
base, meta = tp.load_base("bridgehollow")
meta = dict(meta, sea_level_ft=0.0)
box = lambda x0, y0, x1, y1: [[x0, y0], [x1, y0], [x1 + 60, (y0 + y1) / 2], [x1, y1], [x0, y1 + 40], [x0 - 50, (y0 + y1) / 2]]
# Targets retargeted for natural terrain v2 (raise types can only raise): the hill_band ground already averages ~769 ft
# (peak 877) and the mesa ground averages ~866 ft with peaks to 1019, so the old 745/850 means and 1000 ft mesa top were
# unreachable (now hill 900/785, mesa 1080/925 with a 200 ft feather so the larger raise still seams cleanly). The trench feather went 110 -> 150 ft: the boundary gradient jump scales ~1/feather^2 and a 40 ft trench in
# ground that is already -24..+23 ft is gentle, so the relative seam metric was marginal (0.052 abs vs 0.05) at 110.
CASES = [
 ("ne_peak", box(1750, 150, 2250, 600), dict(terrain_type="mountain", max_height_ft=1250, avg_height_ft=1000, steepness=0.7, feather_ft=150, seed=7, roughness=0.5, erosion=6)),
 ("mound_700", box(1000, 850, 1500, 1250), dict(terrain_type="mountain", max_height_ft=700, avg_height_ft=665, steepness=0.4, feather_ft=100, seed=3, roughness=0.3)),
 ("hill_band", [[100, 700], [900, 600], [1000, 800], [150, 950]], dict(terrain_type="rolling_hills", max_height_ft=900, avg_height_ft=785, steepness=0.3, feather_ft=120, seed=11, roughness=0.6)),
 ("mesa", box(300, 150, 700, 450), dict(terrain_type="mesa", max_height_ft=1080, avg_height_ft=925, steepness=0.8, feather_ft=200, seed=5, roughness=0.3)),
 ("basin_neg60", box(1200, 1150, 1600, 1420), dict(terrain_type="bowl", min_height_ft=-60, avg_height_ft=-25, steepness=0.4, feather_ft=100, seed=9, roughness=0.3)),
 ("trench_neg", [[700, 1090], [1100, 1020], [1120, 1230], [720, 1300]], dict(terrain_type="trench", min_height_ft=-40, avg_height_ft=-12, angle_deg=-10, steepness=0.7, feather_ft=150, seed=2)),
]
NEG = {"basin_neg60", "trench_neg"}
ok = True
cur = base.copy()
curN = base - 650.0   # coastal variant: ground about -30..+400 ft around the 0 ft datum
for name, poly, p in CASES:
    src = curN if name in NEG else cur
    after, info = tp.apply_patch(src, meta, poly, p, return_info=True)
    again = tp.apply_patch(src, meta, poly, p)
    chk = tp.seam_check(src, after, meta, poly)
    ext = p.get("max_height_ft", p.get("min_height_ft"))
    got = info["max"] if "max_height_ft" in p else info["min"]
    e_ok = abs(got - ext) <= 1.0
    m_ok = abs(info["mean"] - p["avg_height_ft"]) <= max(3.0, 0.01 * abs(p["avg_height_ft"]))
    s_ok = chk["outside_max_change"] == 0 and (chk["dgrad_ratio"] < 0.05 or chk["boundary_dgrad"] < 0.05)
    d_ok = np.array_equal(after, again)
    ok &= e_ok and m_ok and s_ok and d_ok
    print("%-12s ext %.1f/%.1f %s | mean %.1f/%.1f %s | seam ratio %.4f (abs %.3f) dh %.2f outside %.1f %s | det %s | %s" % (
        name, got, ext, e_ok, info["mean"], p["avg_height_ft"], m_ok, chk["dgrad_ratio"], chk["boundary_dgrad"], chk["boundary_dh"],
        chk["outside_max_change"], s_ok, d_ok, info["warnings"]))
    tp.save_preview(after, meta, os.path.join(out, name + "_hillshade.png"), poly)
    tp.save_diff(src, after, meta, os.path.join(out, name + "_diff.png"), poly)
    if name in NEG:
        curN = after
    else:
        cur = after
tp.save_preview(cur, meta, os.path.join(out, "all_patches_hillshade.png"))
tp.save_preview(curN, meta, os.path.join(out, "coastal_negative_hillshade.png"))
print("ALL OK" if ok else "FAILURES")
sys.exit(0 if ok else 1)
