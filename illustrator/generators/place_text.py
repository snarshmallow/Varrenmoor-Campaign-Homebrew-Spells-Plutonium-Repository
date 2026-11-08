"""Deterministic keyword parser: plain words -> place spec (place_create.py from-text).

This is a lookup table, not language understanding: it finds known words and numbers and fills the matching spec fields; everything it does not
recognise is ignored (and listed in the notes it returns). For anything subtle ("a town like a smaller Bruges, but built on a bog") ask Claude to write
the spec JSON from `place_create.py prompt-help` instead.

Vocabulary (case-insensitive, whole words):
  population   "800 people / souls / inhabitants / residents / folk", "population 800", "of 800", or a size word: hamlet 90, village 300, small town 450,
               town 900, large town 1800, big town 1800, city 4500, "tiny" x0.5, "small" x0.7, "big|large" x1.6, "huge" x2.2 (applied to the base word)
  layout       walled|fortified|fortress -> walled; grid|gridded|planned|chessboard -> grid; radial|circular|concentric|round|market town|market square|crossroads|spokes
               -> radial (market-town template: square, spokes, ring lanes); linear|ribbon|strung out|along the road|one street|main street|river village|along the river|
               roadside -> linear (linear / river-village template); otherwise organic
  numbers      "1.2k people", "two thousand people", "five hundred souls", "pop 800", "population of 800", thousands separators
  terrain      island | fjord | coastal/coast/seaside/harbour/port/fishing/sea/bay | mountain pass/pass/gap/col | mountain(s)/alpine | bowl/hollow/basin/
               ringed by hills | valley/dale/glen | hills/hilly/downs/uplands | rolling/gentle/farmland | flat/plain/marsh/fen/lowland
  sea side     "north|south|east|west coast/shore" (default south)
  water        "no river", "two rivers", "river|stream|creek|brook", big/wide/great river (wide), small/little river (narrow), winding/lazy river,
               straight river, lake(s)/mere/pond (one lake; "two lakes")
  relief       very hilly/steep/rugged/craggy -> bigger relief; gentle/low/slightly -> smaller
  culture      Danish|German|Hanseatic|Hanse|Saxon-German|Dutch|Baltic -> danish_german; Norse|Viking|Scandinavian|Norwegian|Swedish|Icelandic|Nordic -> scandinavian;
               English|Tudor|medieval English|Saxon|Anglo -> english; else fantasy_generic
  features     church|temple|cathedral|minster|abbey -> central_feature temple; castle|keep|fortress|citadel -> castle; green|common -> green; market -> market
  climate      cold|snowy|northern|arctic -> cold; dry|arid|hot|desert|dusty -> dry; coastal wording -> coastal; else temperate; winter / snow -> season winter; autumn|fall -> autumn
  name         "called X" / "named X" / "X (the name)" with a capitalised name
  draft        "draft|quick|sketch" -> limits.draft
Limits: one town per spec; no street-by-street instructions; no named streets or buildings (add them by editing the spec); contradictions resolve to the
first rule that matches in the order above (e.g. 'island' wins over 'hills').
"""
import re

CULT = [("danish_german", r"danish|german|hanseatic|hanse|dutch|baltic|low countries|schleswig"), ("scandinavian", r"norse|viking|scandinavian|norwegian|swedish|icelandic|nordic|fjord folk"),
        ("english", r"english|tudor|anglo|saxon|yorkshire|cotswold")]
TERR = [("island", r"island|isle"), ("fjord", r"fjord|fjordland"), ("pass", r"mountain pass|\bpass\b|\bgap\b|\bcol\b"),
        ("coastal", r"coastal|coast\b|seaside|harbou?r|\bport\b|fishing|\bsea\b|\bbay\b|\bshore\b|seafront"),
        ("mountain", r"mountain|mountains|alpine|highland"), ("bowl", r"\bbowl\b|hollow|basin|ringed by hills|surrounded by hills|encircled"),
        ("valley", r"valley|\bdale\b|\bglen\b"), ("hills", r"\bhills\b|hilly|downs|uplands|\bfells?\b"),
        ("rolling", r"rolling|farmland|farming|pasture"), ("flat", r"\bflat\b|plain|marsh|\bfen\b|lowland|polder")]
SIZE_WORDS = [(r"large town|big town", 1800), (r"small town", 450), (r"\bcity\b|metropolis", 4500), (r"\bmarket town\b|market-town|\bborough\b", 1000), (r"\btown\b", 900),
              (r"\bvillage\b", 300), (r"\bhamlet\b", 90)]
NUM_WORDS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "one hundred": 100, "a hundred": 100, "two hundred": 200,
             "three hundred": 300, "four hundred": 400, "five hundred": 500, "six hundred": 600, "seven hundred": 700, "eight hundred": 800, "nine hundred": 900, "a thousand": 1000,
             "one thousand": 1000, "two thousand": 2000, "three thousand": 3000, "four thousand": 4000, "five thousand": 5000}


def parse(text):
    t = " " + text.lower().replace(",", " , ").replace(";", " ; ") + " "
    notes, spec = [], {"terrain": {}, "town": {}}
    used = []

    def has(pat):
        m = re.search(pat, t)
        if m:
            used.append(m.group(0).strip())
        return m

    # name
    m = re.search(r"(?:called|named)\s+([A-Z][\w'\-]*(?:\s+[A-Z][\w'\-]*){0,3})", text)
    if m:
        spec["name"] = m.group(1).strip()
        notes.append(f"name: {spec['name']}")
    # culture
    spec["culture"] = "fantasy_generic"
    for c, pat in CULT:
        if has(pat):
            spec["culture"] = c
            notes.append(f"culture: {c}")
            break
    # terrain
    rec = None
    for r, pat in TERR:
        if has(pat):
            rec = r
            break
    spec["terrain"]["recipe"] = rec or "rolling"
    notes.append(f"terrain recipe: {spec['terrain']['recipe']}" + ("" if rec else " (default, no terrain word found)"))
    m = re.search(r"\b(north|south|east|west)(?:ern)?\s+(?:coast|shore|sea|side)", t)
    if m and spec["terrain"]["recipe"] in ("coastal", "fjord"):
        spec["terrain"]["sea_side"] = m.group(1)
        used.append(m.group(0))
    if rec in ("coastal", "fjord", "island") and not m:
        notes.append("sea on the south edge (say 'east coast' etc. to move it)")
    # relief
    if has(r"very hilly|steep|rugged|craggy|dramatic|jagged"):
        spec["terrain"]["ruggedness"] = 0.85
        spec["terrain"]["relief_ft"] = None
        notes.append("rugged: ruggedness 0.85, relief x1.4")
        spec["_relief_mul"] = 1.4
    elif has(r"gentle|low\b|slightly|soft"):
        spec["terrain"]["ruggedness"] = 0.25
        spec["_relief_mul"] = 0.6
    # water
    if has(r"no river|without a river|riverless"):
        spec["terrain"]["rivers"] = 0
    else:
        n = 1 if has(r"\brivers?\b|\bstream\b|\bcreek\b|\bbrook\b|\bbeck\b") else (0 if rec in ("island", "fjord") else None)
        if has(r"two rivers|twin rivers|two streams"):
            n = 2
        if n is not None:
            spec["terrain"]["rivers"] = n
        if has(r"big river|wide river|great river|large river|broad river|mighty river"):
            spec["terrain"]["river_width_ft"] = 110
        elif has(r"small river|little river|narrow|\bstream\b|\bcreek\b|\bbrook\b|\bbeck\b"):
            spec["terrain"]["river_width_ft"] = 24
        if has(r"winding|meandering|lazy|snaking"):
            spec["terrain"]["river_meander"] = "lazy"
        elif has(r"straight river|canal"):
            spec["terrain"]["river_meander"] = "straight"
    if has(r"two lakes"):
        spec["terrain"]["lakes"] = 2
    elif has(r"\blake\b|\bmere\b|\bpond\b|\bloch\b|\btarn\b"):
        spec["terrain"]["lakes"] = 1
    # population
    pop = None
    m = re.search(r"(\d[\d,\.]*)\s*(?:people|souls|inhabitants|residents|folk|citizens|villagers|townsfolk|population)", t)
    m2 = re.search(r"population(?: of)?\s*(\d[\d,\.]*)", t)
    m3 = re.search(r"\bof\s+(\d[\d,]*)\b", t)
    mk = re.search(r"(\d+(?:\.\d+)?)\s*k\b", t)                                                                  # "1.2k people"
    mw = re.search(r"\b(" + "|".join(sorted(NUM_WORDS, key=len, reverse=True)) + r")\s+(?:people|souls|inhabitants|residents|folk|citizens|villagers|townsfolk)", t)
    for mm in (m, m2, mw, mk, m3):
        if mm:
            if mm is mk:
                pop = int(float(mm.group(1)) * 1000)
            elif mm is mw:
                pop = NUM_WORDS[mm.group(1)]
            else:
                pop = int(float(mm.group(1).replace(",", "")))
            used.append(mm.group(0).strip())
            break
    if pop is None:
        for pat, base in SIZE_WORDS:
            if has(pat):
                pop = base
                break
        if pop is not None:
            if has(r"\btiny\b"):
                pop = round(pop * 0.5)
            elif has(r"\bsmall\b") and "small town" not in used:
                pop = round(pop * 0.7)
            elif has(r"\bbig\b|\blarge\b|\bgreat\b|sprawling"):
                pop = round(pop * 1.6)
            elif has(r"\bhuge\b|\bvast\b"):
                pop = round(pop * 2.2)
        else:
            pop = 600
            notes.append("population: 600 (default, no number or size word found)")
    pop = max(20, min(pop, 12000))
    spec["town"]["population"] = pop
    notes.append(f"population: {pop}")
    # layout
    lay = "organic"
    for l, pat in (("walled", r"walled|fortified|fortress town|palisade|stockade"), ("grid", r"\bgrid|gridded|planned|chessboard|bastide"),
                   ("radial", r"radial|circular|concentric|\bround town|market town|market-town|market square|crossroads|hub and spoke|spokes"),
                   ("linear", r"linear|ribbon|strung out|along the road|one street|main street|street village|river village|riverside village|along the river|strung along|"
                              r"on both banks|either side of the river|riverside hamlet|roadside")):
        if has(pat):
            lay = l
            break
    spec["town"]["layout"] = lay
    notes.append(f"layout: {lay}")
    if lay == "walled":
        spec["town"]["wall"] = True
    # features
    if has(r"church|temple|cathedral|minster|abbey|chapel|monaster"):
        spec["town"]["central_feature"] = "temple"
    elif has(r"castle|\bkeep\b|citadel|\bfort\b|fortress"):
        spec["town"]["central_feature"] = "castle"
    elif has(r"\bgreen\b|\bcommon\b"):
        spec["town"]["central_feature"] = "green"
    elif has(r"market town|market-town|market square|\bmarket\b|crossroads"):
        spec["town"]["central_feature"] = "market"
    # climate / season
    if has(r"\bcold\b|snowy|northern|arctic|frozen|tundra"):
        spec["climate"] = "cold"
    elif has(r"\bdry\b|arid|\bhot\b|desert|dusty|parched"):
        spec["climate"] = "dry"
    if has(r"winter|snow\b|snowbound|snowed"):
        spec["season"] = "winter"
    elif has(r"autumn|\bfall\b|harvest"):
        spec["season"] = "autumn"
    if has(r"\bdraft\b|\bquick\b|sketch"):
        spec["limits"] = {"draft": True}
    # relief multiplier
    mul = spec.pop("_relief_mul", None)
    if mul:
        from place_terrain import RELIEF
        spec["terrain"]["relief_ft"] = round(RELIEF[spec["terrain"]["recipe"]] * mul)
    if spec["terrain"].get("relief_ft") is None:
        spec["terrain"].pop("relief_ft", None)
    spec["_note"] = "Written by place_create.py from-text: " + text.strip()[:200]
    if not spec.get("name"):
        spec["id"] = "from_text_" + re.sub(r"[^a-z0-9]+", "_", text.lower())[:24].strip("_")
    rest = [w for w in re.findall(r"[a-z']{4,}", t) if not any(w in u for u in used)]
    skip = {"with", "that", "this", "town", "people", "have", "from", "into", "about", "style", "built", "like", "around", "near", "and", "the", "which", "where", "very"}
    ign = sorted({w for w in rest if w not in skip})[:14]
    if ign:
        notes.append("ignored words: " + ", ".join(ign))
    return spec, notes
