"""Document pictures of a flow.

The stored preview of a diagram is the whole draw.io sheet: titled frame, flow, master legend. Documents show the
flow only. Two rules decide what is cut out of the sheet picture:

  1. "Export area" shapes drawn in Flow Studio (style key meaExport=1): every area becomes one picture, in reading
     order (top to bottom, then left to right). Only what lies inside an area goes into the document.
  2. No export area: the flow without frame, title bar and master legend, white margins trimmed.

Nothing is redrawn - a document picture is always a cut of what draw.io rendered, so it cannot differ from the flow."""
import hashlib
import io
import math

from . import drawio

BORDER = 10.0        # border (diagram units) of the draw.io PNG export used by Flow Studio and tools/render_flow_previews.js
INSET = 3.0          # cut this far inside an export area / the frame, so that their outlines are not part of the picture
MARGIN_PX = 14       # white margin kept around a trimmed flow
AREA_LABEL = "Export area – only this part goes into the document"
AREA_STYLE = ("rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#E4002B;strokeWidth=2;dashed=1;dashPattern=8 4;pointerEvents=0;connectable=0;"
              "fontFamily=Arial;fontSize=11;fontStyle=1;fontColor=#E4002B;align=left;verticalAlign=bottom;labelPosition=center;verticalLabelPosition=top;meaExport=1;")


def _rect(b):
    x, y, w, h = b["x"], b["y"], b["w"], b["h"]
    rot = drawio._num(b["style"].get("rotation"))
    if rot % 180:
        a = math.radians(rot)
        cx, cy = x + w / 2, y + h / 2
        hw = (abs(w * math.cos(a)) + abs(h * math.sin(a))) / 2
        hh = (abs(w * math.sin(a)) + abs(h * math.cos(a))) / 2
        return (cx - hw, cy - hh, cx + hw, cy + hh)
    return (x, y, x + w, y + h)


def _union(rects):
    rects = [r for r in rects if r]
    if not rects:
        return None
    return (min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects))


def is_area(style: dict) -> bool:
    return bool(style.get("meaExport"))


def layout(xml: str, page: int = 0) -> dict:
    """Rectangles (x0, y0, x1, y1 in diagram units) of the sheet, the frame, its title bar, the legend, the flow and the export areas."""
    sc = drawio.scene(xml, page)
    frame, title_h, legend, areas, rest = None, 0.0, [], [], []
    for b in sc["boxes"].values():
        st = b["style"]
        k = st.get("meaKind")
        if is_area(st):
            areas.append(dict(box=_rect(b), label=(b["label"] or "").strip()))
        elif b["id"] == "mea_frame" or k == "frame":
            frame, title_h = _rect(b), drawio._num(st.get("startSize"), 23)
        elif k == "legend" or b["id"].startswith(("mea_lg", "mea_legend")):
            legend.append(_rect(b))
        else:
            rest.append(_rect(b))
    pts = [(p[0], p[1], p[0], p[1]) for e in sc["edges"] if e["style"].get("meaKind") != "legend" for p in e["points"]]
    flow = _union(rest + pts)
    everything = _union(rest + pts + legend + [a["box"] for a in areas] + ([frame] if frame else []))
    sheet = frame or everything                              # the frame is drawn around everything else
    if sheet and everything:
        sheet = _union([sheet, everything])
    areas.sort(key=lambda a: (round(a["box"][1] / 40.0), a["box"][0]))
    return dict(sheet=sheet, frame=frame, title_h=title_h, legend=_union(legend), flow=flow, areas=areas, shapes=rest)


def plan(xml: str, mode: str = "flow") -> dict:
    """What a document shows: dict(kind = areas | flow | sheet, boxes, labels, trim, note)."""
    try:
        L = layout(xml)
    except Exception:
        return dict(kind="sheet", boxes=[], labels=[], trim=False, note="")
    if mode == "sheet" or not L["sheet"]:
        return dict(kind="sheet", boxes=[], labels=[], trim=False, note="")
    if L["areas"]:
        boxes = [(a["box"][0] + INSET, a["box"][1] + INSET, a["box"][2] - INSET, a["box"][3] - INSET) for a in L["areas"]]
        labels = ["" if a["label"] == AREA_LABEL else a["label"] for a in L["areas"]]
        return dict(kind="areas", boxes=boxes, labels=labels, trim=False, note="")
    if not L["flow"] or not (L["frame"] or L["legend"]):
        return dict(kind="sheet", boxes=[], labels=[], trim=False, note="")          # nothing to leave out
    x0, y0, x1, y1 = L["sheet"]
    if L["frame"]:
        fx0, fy0, fx1, fy1 = L["frame"]
        x0, y0, x1, y1 = fx0 + INSET, fy0 + L["title_h"] + INSET, fx1 - INSET, fy1 - INSET
    note = ""
    if L["legend"]:
        lx0, ly0, lx1, ly1 = L["legend"]
        gx0, gy0, gx1, gy1 = L["flow"]
        if gy1 <= ly0:
            y1 = min(y1, ly0 - INSET)
        elif gy0 >= ly1:
            y0 = max(y0, ly1 + INSET)
        elif gx1 <= lx0:
            x1 = min(x1, lx0 - INSET)
        elif gx0 >= lx1:
            x0 = max(x0, lx1 + INSET)
        else:
            note = "Shapes overlap the master legend, so the legend stays in the document picture. Move them clear of the legend or draw an export area."
    return dict(kind="flow", boxes=[(x0, y0, x1, y1)], labels=[""], trim=True, note=note)


def describe(xml: str) -> dict:
    """Short statement for the user interface (no picture is cut)."""
    p = plan(xml)
    n = len(p["boxes"])
    text = {"areas": f"{n} export area{'s' if n != 1 else ''} – only the part inside goes into documents",
            "flow": "flow only – frame, title bar and master legend are left out of documents",
            "sheet": "whole sheet"}[p["kind"]]
    return dict(kind=p["kind"], count=max(n, 1), text=text, note=p["note"])


def cover_of(model_bounds):
    """Diagram rectangle covered by a draw.io PNG whose graph bounds (model units) are known."""
    try:
        x, y, w, h = [float(v) for v in model_bounds]
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return (x - BORDER, y - BORDER, w + 2 * BORDER, h + 2 * BORDER)


def _rgb(im):
    from PIL import Image
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.split()[-1])
        return bg
    return im.convert("RGB")


def _trim(im):
    """Cut the white margins (the picture keeps its colour mode, so a small palette PNG stays small). -> (picture, (left, top) cut off)."""
    from PIL import Image, ImageChops
    rgb = _rgb(im)
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, "white")).convert("L").point(lambda v: 255 if v > 14 else 0)
    bb = diff.getbbox()
    if not bb:
        return im, (0, 0)
    box = (max(0, bb[0] - MARGIN_PX), max(0, bb[1] - MARGIN_PX), min(im.width, bb[2] + MARGIN_PX), min(im.height, bb[3] + MARGIN_PX))
    return im.crop(box), (box[0], box[1])


PAGE_CM = (16.0, 20.0)     # room for a flow picture on an A4 page of the exports (width, height)
SPLIT_GAIN = 1.4           # split a tall flow only when its parts print at least this much larger


def split_tall(im, scale, shapes=()):
    """A flow that is much taller than a page is cut into consecutive parts so that it stays readable. A cut runs between
    shapes (`shapes` = their top/bottom rows in this picture), across connectors only, as close to an even division as
    possible; where no such row exists nearby, the row with the least drawing is used. Nothing is redrawn."""
    from PIL import Image, ImageChops
    cw, ch = im.width / scale / 96 * 2.54, im.height / scale / 96 * 2.54
    now = min(1.0, PAGE_CM[0] / cw, PAGE_CM[1] / ch)                         # reduction when printed as one picture
    best = min(1.0, PAGE_CM[0] / cw)                                         # the width limits what splitting can gain
    n = math.ceil(ch * best / PAGE_CM[1])
    if n < 2 or n > 8 or best / now < SPLIT_GAIN:
        return [im]
    rgb = _rgb(im)
    ink = ImageChops.difference(rgb, Image.new("RGB", rgb.size, "white")).convert("L").point(lambda v: 255 if v > 14 else 0).resize((1, im.height), Image.BOX)
    rows = list(ink.tobytes())
    part = im.height / n
    cuts = [0]
    for k in range(1, n):
        ideal, win = int(k * part), int(part * 0.14)
        lo, hi = max(cuts[-1] + int(part * 0.5), ideal - win), min(im.height - 1, ideal + win)
        small = [(a - 4, b + 4) for a, b in shapes if b - a < part * 0.45]             # tall containers cannot be avoided
        free = [r for r in range(lo, hi + 1) if not any(a <= r <= b for a, b in small)]
        y = min(free or range(lo, hi + 1), key=lambda r: (rows[r] // 8, abs(r - ideal))) if lo <= hi else ideal
        cuts.append(y)
    cuts.append(im.height)
    return [im.crop((0, a, im.width, b)) for a, b in zip(cuts, cuts[1:]) if b - a > 20]


_CACHE = {}


def cut(png: bytes, xml: str, cover=None, mode: str = "flow") -> dict:
    """Document pictures of one diagram: dict(kind, pictures=[dict(png, label, scale)], note).

    `cover` is the diagram rectangle (x, y, w, h) the PNG shows. Without it the rectangle is derived from the frame
    (or from all shapes) and checked against the picture's proportions; when it does not fit, the whole sheet is used."""
    key = (hashlib.sha1(png).hexdigest(), hashlib.sha1(xml.encode()).hexdigest(), mode, tuple(cover) if cover else None)
    if key in _CACHE:
        return _CACHE[key]
    res = _cut(png, xml, cover, mode)
    if len(_CACHE) > 300:
        _CACHE.clear()
    _CACHE[key] = res
    return res


def _cut(png, xml, cover, mode):
    whole = dict(kind="sheet", pictures=[dict(png=png, label="", scale=None)], note="")
    p = plan(xml, mode)
    if p["kind"] == "sheet":
        return whole
    from PIL import Image
    im = Image.open(io.BytesIO(png))
    if im.mode not in ("P", "L", "RGB") or "transparency" in im.info:
        im = _rgb(im)
    if not cover:
        s = layout(xml)["sheet"]
        cover = (s[0] - 0.5 - BORDER, s[1] - 0.5 - BORDER, s[2] - s[0] + 1 + 2 * BORDER, s[3] - s[1] + 1 + 2 * BORDER)
    shapes = layout(xml)["shapes"]
    kx, ky = im.width / cover[2], im.height / cover[3]
    if not (0.1 < kx < 8) or abs(kx - ky) / kx > 0.03:
        return dict(whole, note="The document picture could not be located in this preview, so the whole sheet is used. Open and save the flow once in Flow Studio.")
    pics = []
    for (x0, y0, x1, y1), label in zip(p["boxes"], p["labels"]):
        px = (max(0, int(round((x0 - cover[0]) * kx))), max(0, int(round((y0 - cover[1]) * ky))),
              min(im.width, int(round((x1 - cover[0]) * kx))), min(im.height, int(round((y1 - cover[1]) * ky))))
        if px[2] - px[0] < 12 or px[3] - px[1] < 12:
            continue
        part = im.crop(px)
        parts = [part]
        if p["trim"]:                                                                 # automatic parts only where no export area was drawn
            piece, (ox, oy) = _trim(part)
            rows_ = [((r[1] - cover[1]) * ky - px[1] - oy, (r[3] - cover[1]) * ky - px[1] - oy) for r in shapes]
            parts = split_tall(piece, (kx + ky) / 2, rows_)
        for piece in parts:
            bio = io.BytesIO()
            piece.save(bio, "PNG", optimize=piece.mode == "P")
            pics.append(dict(png=bio.getvalue(), label=label, scale=(kx + ky) / 2, auto=len(parts) > 1))
    if not pics:
        return dict(whole, note="The export area lies outside the picture, so the whole sheet is used.")
    note = p["note"]
    if len(pics) > 1 and p["trim"]:
        note = (note + " " if note else "") + f"The flow is taller than a page and is printed in {len(pics)} consecutive parts. Draw export areas in Flow Studio to choose the parts yourself."
    return dict(kind=p["kind"], pictures=pics, note=note)
