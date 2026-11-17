"""Fit check for the hand-written README diagrams.

For every line of text in an SVG: measure it in the widest of the fonts a
reader may get (SF Pro, Helvetica, Arial for sans; SF Mono, Menlo for mono),
then check that it

  - stays MARGIN units inside the innermost box that contains it,
  - does not overlap another line of text,
  - does not spill into a box it is not inside,
  - is not crossed by a line or path segment drawn on top of it.

Usage: python3.12 check_svg.py file.svg [file.svg ...]
"""

import re
import sys
import xml.etree.ElementTree as ET

from PIL import ImageFont

MARGIN = 12
NS = "{http://www.w3.org/2000/svg}"
FONT_DIR = "/System/Library/Fonts/"


def _load(path, size, index=0, bold=False):
    try:
        font = ImageFont.truetype(path, size=100, index=index)
    except OSError:
        return None
    if bold:
        try:
            font.set_variation_by_name("Bold")
        except Exception:
            try:
                axes = font.get_variation_axes()
                values = [700 if a.get("name") in (b"Weight", "Weight") else a["default"] for a in axes]
                font.set_variation_by_axes(values)
            except Exception:
                return None
    return font


FONTS = {
    ("sans", False): [f for f in (
        _load(FONT_DIR + "SFNS.ttf", 100),
        _load(FONT_DIR + "Helvetica.ttc", 100, 0),
        _load(FONT_DIR + "Supplemental/Arial.ttf", 100),
    ) if f],
    ("sans", True): [f for f in (
        _load(FONT_DIR + "SFNS.ttf", 100, bold=True),
        _load(FONT_DIR + "Helvetica.ttc", 100, 1),
        _load(FONT_DIR + "Supplemental/Arial Bold.ttf", 100),
    ) if f],
    ("mono", False): [f for f in (
        _load(FONT_DIR + "SFNSMono.ttf", 100),
        _load(FONT_DIR + "Menlo.ttc", 100, 0),
    ) if f],
    ("mono", True): [f for f in (
        _load(FONT_DIR + "SFNSMono.ttf", 100, bold=True),
        _load(FONT_DIR + "Menlo.ttc", 100, 1),
    ) if f],
}


def width(text, size, mono, bold, spacing):
    fonts = FONTS[("mono" if mono else "sans", bold)]
    widest = max(font.getlength(text) for font in fonts) * size / 100.0
    return widest + spacing * len(text)


def style_of(el, parent):
    s = dict(parent)
    if el.get("font-size"):
        s["size"] = float(el.get("font-size"))
    if el.get("font-family"):
        s["mono"] = "mono" in el.get("font-family").lower()
    if el.get("font-weight"):
        s["bold"] = el.get("font-weight") in ("600", "700", "bold")
    if el.get("letter-spacing"):
        s["spacing"] = float(el.get("letter-spacing"))
    if el.get("text-anchor"):
        s["anchor"] = el.get("text-anchor")
    return s


class Line:
    def __init__(self, x, y, anchor, order):
        self.x, self.y, self.anchor, self.order = x, y, anchor, order
        self.runs = []

    def add(self, text, s):
        if text and text.strip("\n"):
            text = re.sub(r"\s+", " ", text)
            self.runs.append((text, s))

    @property
    def text(self):
        return "".join(t for t, _ in self.runs).strip()

    def box(self):
        runs = list(self.runs)
        if not runs:
            return None
        runs[0] = (runs[0][0].lstrip(), runs[0][1])
        runs[-1] = (runs[-1][0].rstrip(), runs[-1][1])
        w = sum(width(t, s["size"], s["mono"], s["bold"], s["spacing"]) for t, s in runs)
        size = max(s["size"] for _, s in runs)
        if self.anchor == "middle":
            x0 = self.x - w / 2
        elif self.anchor == "end":
            x0 = self.x - w
        else:
            x0 = self.x
        return (x0, self.y - 0.76 * size, x0 + w, self.y + 0.22 * size)


def collect(root):
    rects, segs, lines = [], [], []
    order = [0]

    def text_el(el, s, line):
        s = style_of(el, s)
        if el.tag == NS + "text" or el.get("x") is not None or el.get("y") is not None:
            x = float(el.get("x")) if el.get("x") is not None else (line.x if line else 0)
            y = float(el.get("y")) if el.get("y") is not None else (line.y if line else 0)
            y += float(el.get("dy") or 0)
            line = Line(x, y, s["anchor"], order[0])
            lines.append(line)
        line.add(el.text, s)
        for child in el:
            line = text_el(child, s, line)
            line.add(child.tail, s)
        return line

    def walk(el, s):
        order[0] += 1
        s = style_of(el, s)
        tag = el.tag.replace(NS, "")
        if tag == "rect":
            rects.append((float(el.get("x")), float(el.get("y")), float(el.get("width")),
                          float(el.get("height")), order[0],
                          el.get("fill") not in (None, "none")))
        elif tag == "line":
            segs.append((float(el.get("x1")), float(el.get("y1")), float(el.get("x2")), float(el.get("y2")), order[0]))
        elif tag == "path":
            x = y = 0.0
            for cmd, args in re.findall(r"([MLHV])\s*([-\d.,\s]*)", el.get("d", "")):
                nums = [float(n) for n in re.findall(r"-?\d+\.?\d*", args)]
                if cmd == "M":
                    x, y = nums[0], nums[1]
                elif cmd == "L":
                    segs.append((x, y, nums[0], nums[1], order[0])); x, y = nums[0], nums[1]
                elif cmd == "H":
                    segs.append((x, y, nums[0], y, order[0])); x = nums[0]
                elif cmd == "V":
                    segs.append((x, y, x, nums[0], order[0])); y = nums[0]
        elif tag == "text":
            text_el(el, s, None)
            return
        elif tag in ("defs", "title", "desc"):
            return
        for child in el:
            walk(child, s)

    walk(root, {"size": 16.0, "mono": False, "bold": False, "spacing": 0.0, "anchor": "start"})
    return rects, segs, lines


def inside(box, rect, pad=0.0):
    x0, y0, x1, y1 = box
    rx, ry, rw, rh = rect[:4]
    return x0 >= rx + pad and x1 <= rx + rw - pad and y0 >= ry - 2 and y1 <= ry + rh + 2


def overlap(a, b, pad=0.0):
    return a[0] < b[2] + pad and b[0] < a[2] + pad and a[1] < b[3] and b[1] < a[3]


def seg_hits(seg, box):
    x1, y1, x2, y2 = seg[:4]
    bx0, by0, bx1, by1 = box[0] - 4, box[1], box[2] + 4, box[3]
    if x1 == x2:
        return bx0 < x1 < bx1 and min(y1, y2) < by1 and max(y1, y2) > by0
    if y1 == y2:
        return by0 < y1 < by1 and min(x1, x2) < bx1 and max(x1, x2) > bx0
    return False


def check(path):
    root = ET.parse(path).getroot()
    rects, segs, lines = collect(root)
    problems, slack = [], []
    boxes = [(line, line.box()) for line in lines if line.box()]
    for line, box in boxes:
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        holders = [r for r in rects if r[0] <= cx <= r[0] + r[2] and r[1] <= cy <= r[1] + r[3]]
        holder = min(holders, key=lambda r: r[2] * r[3]) if holders else None
        if holder:
            left, right = box[0] - holder[0], holder[0] + holder[2] - box[2]
            slack.append((min(left, right), line.text))
            if not inside(box, holder, MARGIN):
                problems.append(f"too close to its box (left {left:.0f}, right {right:.0f}): {line.text!r}")
        for r in rects:
            if r is holder or (holder and r[2] * r[3] > holder[2] * holder[3] and inside((box[0], box[1], box[2], box[3]), r)):
                continue
            rbox = (r[0], r[1], r[0] + r[2], r[1] + r[3])
            if overlap(box, rbox) and not inside(box, r):
                problems.append(f"spills into a box at x={r[0]:.0f} y={r[1]:.0f}: {line.text!r}")
        for seg in segs:
            hidden = holder is not None and holder[5] and holder[4] > seg[4] and holder[2] * holder[3] < 600000
            if seg_hits(seg, box) and not hidden:
                problems.append(f"crossed by a line at ({seg[0]:.0f},{seg[1]:.0f})-({seg[2]:.0f},{seg[3]:.0f}): {line.text!r}")
    for i, (la, a) in enumerate(boxes):
        for lb, b in boxes[i + 1:]:
            if overlap(a, b, 4):
                problems.append(f"text overlaps: {la.text!r} / {lb.text!r}")
    small = sorted({s["size"] for line in lines for _, s in line.runs})
    tight = min(slack) if slack else (0, "")
    print(f"{path.split('/')[-1]}: {len(boxes)} text lines, font sizes {small}, "
          f"tightest slack {tight[0]:.0f} ({tight[1][:40]!r})")
    for p in problems:
        print("   PROBLEM", p)
    return not problems and (not small or small[0] >= 14)


if __name__ == "__main__":
    ok = [check(p) for p in sys.argv[1:]]
    sys.exit(0 if all(ok) else 1)
