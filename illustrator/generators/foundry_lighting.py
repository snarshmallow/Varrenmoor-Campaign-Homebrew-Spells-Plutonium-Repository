"""Map the Illustrator lighting config (lighting.py / panel_state.json "lighting": sun azimuth + altitude, colour, ambient, point lights)
onto Foundry scenes, so the 2D map shadows, the skybox sun and the 3D Canvas sun agree. No Foundry calls here.

Conventions: azimuth = compass bearing OF the sun, clockwise from north (0 N, 90 E, 180 S, 225 SW); altitude = degrees above the horizon; map x = east, y = south (feet).

3D Canvas sun rig (globalIllumination.js, read-only): the directional light sits at (0, -sunDistance, 0), the rig is rotated by Euler(tilt*pi/2, 0, angle(time)) about the
x (east) and z axes, 3D y is up and 3D z is scene-south. So the sun position is d*(sin t, -cos t * cos f, -cos t * sin f) with t = angle(time), f = tilt*pi/2.
Solving for a wanted direction (E, U, S): f = atan2(S, U), t = atan2(E, -U / cos f); `time` is the flag `sunPosition` (hours 0..24) found by inverting the module's
time -> angle spline (sampled below from the running module). Sun colour -> `sceneTint`, intensity -> `exposure` (the module sets the sun intensity = exposure).
The skybox image is lit by the same sun: skybox.py generate --sun-bearing/--sun-alt (use sun_for_skybox()).
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
# module's getAngleAt(hour) for hour 0..24 (radians), read from the live module (3D Canvas 9.0.29)
ANGLE_AT = [0, 0.262, 0.525, 0.787, 1.05, 1.312, 1.574, 1.843, 2.118, 2.393, 2.66, 2.912, 3.147, 3.36, 3.554, 3.739, 3.922, 4.107, 4.3, 4.51, 4.754, 5.06, 5.43, 5.851, 6.283]


def hour_for_angle(t):
    t = t % (2 * math.pi)
    for h in range(24):
        a, b = ANGLE_AT[h], ANGLE_AT[h + 1]
        if a <= t <= b:
            return round(h + (t - a) / (b - a), 2)
    return 12.0


def sun_to_3d(azimuth, altitude):
    """-> {"sunPosition": hours, "sunTilt": tilt}. Altitude <= 0 (night) returns sunPosition 0 with tilt 0 (sun far below)."""
    az, el = math.radians(azimuth), math.radians(max(altitude, 0.5))
    E, S, U = math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)
    f = math.atan2(S, U)
    t = math.atan2(E, -U / math.cos(f))
    return {"sunPosition": hour_for_angle(t), "sunTilt": round(f / (math.pi / 2), 3)}


def angle_for_hour(h):
    """Inverse of hour_for_angle: the module's sun angle (radians) at `sunPosition` hours."""
    h = float(h) % 24.0
    i = min(int(h), 23)
    return ANGLE_AT[i] + (h - i) * (ANGLE_AT[i + 1] - ANGLE_AT[i])


def sun_from_3d(sun_position, sun_tilt):
    """Inverse of sun_to_3d: (compass bearing 0..360, altitude deg) of the light that 3D Canvas casts for the flags sunPosition (hours) and sunTilt."""
    t, f = angle_for_hour(sun_position), float(sun_tilt) * math.pi / 2
    E, U, S = math.sin(t), -math.cos(t) * math.cos(f), -math.cos(t) * math.sin(f)
    return (math.degrees(math.atan2(E, -S)) % 360.0, math.degrees(math.asin(max(-1.0, min(1.0, U)))))


def sun_for_skybox(azimuth, altitude):
    """skybox.py convention: sun_az from east clockwise (image centre = east), sun_el degrees."""
    return {"sun_az": azimuth - 90.0, "sun_el": altitude}


def load_lighting(src):
    """src = a place id (world/<place>/panel_state.json "lighting"), a lighting JSON file ({"sun":..} or {"lights":[{"type":"sun"}..]}), or a dict -> normalised cfg."""
    cfg = src
    if isinstance(src, str):
        p = src if os.path.exists(src) else os.path.join(REPO, "world", src, "panel_state.json")
        with open(p, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg = cfg.get("lighting", cfg)
    sun = dict(cfg.get("sun") or {})
    pts = []
    for l in cfg.get("lights", []):
        if l.get("type") == "sun":
            sun = {**sun, **l}
        elif l.get("enabled", True) and "x" in l:
            pts.append(l)
    sun = {"azimuth": 225.0, "altitude": 30.0, "color": "#fff1d0", "intensity": 1.0, **sun}
    return {"sun": sun, "ambient": float(cfg.get("ambient", 0.35)), "points": pts, "enabled": cfg.get("enabled", True)}


def scene_light_flags(cfg):
    """levels-3d-preview scene flags that reproduce the config's sun and ambient."""
    s = cfg["sun"]
    f = sun_to_3d(float(s["azimuth"]), float(s["altitude"]))
    return {**f, "sunDistance": 10, "timeSync": "off", "sceneTint": s.get("color", "#ffffff"), "exposure": round(float(s.get("intensity", 1.0)), 3),
            "ambientLightIntensity": round(cfg["ambient"], 3)}


def flat_environment(cfg):
    """Scene.environment for a flat (2D) scene whose map image already carries the baked shadows/glow: bright global light, no darkness."""
    return {"darknessLevel": 0.0, "globalLight": {"enabled": True, "darkness": {"min": 0.0, "max": 1.0}}}


def point_light_docs(cfg, origin_ft, ppf, scene_xy=(0, 0), x0=0.0, y0=0.0, place="x"):
    """Config point lights (place frame, ft) -> AmbientLight items for upsert_many; origin_ft = child frame origin in the config's frame (e.g. [730, 710])."""
    out = []
    for i, l in enumerate(cfg["points"]):
        fx, fy = float(l["x"]) - origin_ft[0], float(l["y"]) - origin_ft[1]
        r = float(l.get("radius", l.get("radius_ft", 30.0)))
        out.append({"id": f"light:{place}:2d_{l.get('id', i)}", "data": {
            "x": round(scene_xy[0] + (fx - x0) * ppf), "y": round(scene_xy[1] + (fy - y0) * ppf), "elevation": float(l.get("height", 6.0)), "walls": True, "vision": False,
            "config": {"dim": r, "bright": r * 0.4, "color": l.get("color", "#fff1d0"), "alpha": min(0.9, 0.2 + 0.5 * float(l.get("intensity", 1.0))), "luminosity": 0.5,
                       "animation": {"type": None}},
            "flags": {"levels-3d-preview": {"enableParticle": False}, "varrenmoor": {"lightId": f"2d_{l.get('id', i)}", "type": "point2d"}}}})
    return out
