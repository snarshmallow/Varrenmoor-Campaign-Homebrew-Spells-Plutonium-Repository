"""Text blocks around the map (title / status notes at the top, key at the bottom): word-wrapped to the map width and
placed OUTSIDE the map window (in the page margin above it, or in a band added below the page).

  tf = size_factor(pw_in, ph_in)                       text scales with the page (1 at 17x11 in), not with the map's feet
  lines, need_pt = top_block(paras, width_pt, tf)      [(id, text, size, bold, y_baseline)], margin height (pt) the block needs
  rows, w, h = key_band(entries, size, width_pt, title)  columns of numbered entries, each wrapped to its column; (dx, dy, text, bold)
Widths use label_offset.text_size (the same estimate the label placer uses), so the check in the tests matches the layout.
"""
import label_offset as lbo

LINE = 1.2


def size_factor(pw_in, ph_in):
    return max(1.0, min(float(pw_in) / 17.0, float(ph_in) / 11.0))


def text_w(s, size, bold=False):
    return lbo.text_size(s, size, bold)[0]


def wrap(s, size, width_pt, bold=False):
    """Greedy word wrap of s into lines no wider than width_pt (a single over-long word is split by characters)."""
    out, cur = [], ""
    for word in str(s).split():
        while text_w(word, size, bold) > width_pt and len(word) > 1:      # over-long word: break it
            n = len(word)
            while n > 1 and text_w(word[:n], size, bold) > width_pt:
                n -= 1
            if cur:
                out.append(cur); cur = ""
            out.append(word[:n]); word = word[n:]
        trial = (cur + " " + word).strip()
        if cur and text_w(trial, size, bold) > width_pt:
            out.append(cur); cur = word
        else:
            cur = trial
    if cur:
        out.append(cur)
    return out or [""]


def top_block(paras, width_pt, tf=1.0, avail_pt=None, top=3.0):
    """paras: [(id, text, base_size, bold)] -> (lines, need_pt). Each paragraph is wrapped to width_pt; sizes are base*tf, shrunk
    (down to 80 percent) when avail_pt (the margin height) is given and the block would not fit. need_pt = height the block occupies."""
    shrink = 1.0
    while True:
        lines, y = [], top
        for pid, txt, base, bold in paras:
            sz = base * tf * shrink
            for i, ln in enumerate(wrap(txt, sz, width_pt, bold)):
                y += sz * LINE if (lines or i) else sz * 0.95
                lines.append((pid if i == 0 else f"{pid}_{i + 1}", ln, round(sz, 2), bold, round(y, 2)))
        need = y + 3.0
        if avail_pt is None or need <= avail_pt or shrink <= 0.8:
            return lines, need
        shrink *= 0.9


def key_band(entries, size, width_pt, title=None, gap=14.0):
    """entries [(n, text)] -> (rows [(dx, dy, text, bold)], w, h) laid out in as many columns as fit width_pt."""
    nw = size * 2.1
    lh = size * LINE
    textw = max((text_w(t, size) for _, t in entries), default=0.0)
    colw = min(nw + textw, width_pt)
    ncols = max(1, int((width_pt + gap) // (colw + gap)))
    tw = max(size, colw - nw)
    items = [(n, wrap(t, size, tw)) for n, t in entries]
    per = -(-len(items) // ncols) if items else 1
    rows, y0 = [], 0.0
    if title:
        rows.append((0.0, size * 0.95, title, True))
        y0 = lh * 1.35
    hmax = 0.0
    for c in range(ncols):
        y = y0
        for n, ls in items[c * per:(c + 1) * per]:
            x = c * (colw + gap)
            rows.append((x, y + size * 0.95, str(n), True))
            for i, ln in enumerate(ls):
                rows.append((x + nw, y + size * 0.95 + i * lh, ln, False))
            y += lh * len(ls)
        hmax = max(hmax, y)
    return rows, min(width_pt, ncols * colw + (ncols - 1) * gap), hmax + size * 0.3
