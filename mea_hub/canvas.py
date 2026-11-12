"""Split a 'master canvas' draw.io page (many independently titled flows drawn on one sheet) into one
diagram per flow.  Titles are the large text labels above each flow; shapes are grouped by their connectors,
loose annotations are attached to the nearest flow, and nothing is dropped silently (leftovers are returned)."""
import collections
import copy
import re

from lxml import etree

from . import drawio

TITLE_FONT = "20"
STRAY_LABEL = 600        # label offsets beyond this (diagram units) are leftovers of the canvas, not a deliberate position


def _dist(a, b):
    dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return (dx * dx + dy * dy) ** 0.5


def _bbox(us):
    return (min(u["x"] for u in us), min(u["y"] for u in us), max(u["x"] + u["w"] for u in us), max(u["y"] + u["h"] for u in us))


def _ubb(u):
    return (u["x"], u["y"], u["x"] + u["w"], u["y"] + u["h"])


def is_canvas(xml: str) -> bool:
    """True when a single page carries several independently titled flows."""
    try:
        sc = drawio.scene(xml)
    except Exception:
        return False
    titles = [b for b in sc["boxes"].values() if b["style"]["_first"] == "text" and b["style"].get("fontSize") == TITLE_FONT and b["label"].strip()]
    return len(titles) >= 5 and len(sc["boxes"]) > 150


def segment(xml: str, grow: float = 110, attach: float = 150):
    """Return (flows, leftovers). Each flow: dict(title, title_id, unit_ids, bbox)."""
    root = drawio._parse(xml.encode("utf-8"))
    model = root.find("diagram").find("mxGraphModel")
    edge_ids = {c.get("id") for c in model.iter("mxCell") if c.get("edge") == "1"}
    sc = drawio.scene(xml)
    B = sc["boxes"]

    def top(i):
        while i in B and B[i]["parent"] in B:
            i = B[i]["parent"]
        return i
    titles = [b for b in B.values() if b["style"]["_first"] == "text" and b["style"].get("fontSize") == TITLE_FONT and b["label"].strip()]
    headers = [b for b in B.values() if b["style"]["_first"] == "text" and b["style"].get("fontStyle") == "1" and b["w"] >= 480]
    skip = {b["id"] for b in titles} | {b["id"] for b in headers}
    units = [b for b in B.values() if b["parent"] not in B and b["parent"] not in edge_ids and b["id"] not in skip]
    par = {u["id"]: u["id"] for u in units}

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for e in sc["edges"]:
        s, t = (top(e["source"]) if e["source"] else None), (top(e["target"]) if e["target"] else None)
        if s in par and t in par:
            par[find(s)] = find(t)
    comps = collections.defaultdict(list)
    for u in units:
        comps[find(u["id"])].append(u)
    cbb = {r: _bbox(v) for r, v in comps.items()}
    bigs = [r for r, v in comps.items() if len(v) >= 3]
    smalls = [r for r, v in comps.items() if len(v) < 3]
    assign = {}
    for r in bigs:
        bb, best = cbb[r], None
        for t in titles:
            if t["y"] - 30 <= bb[1] <= t["y"] + 320 and bb[0] - 200 <= t["x"] + t["w"] / 2 <= bb[2] + 200:
                d = abs((bb[0] + bb[2]) / 2 - (t["x"] + t["w"] / 2)) * 0.5 + abs(bb[1] - t["y"])
                if best is None or d < best[0]:
                    best = (d, t["id"])
        if best:
            assign[r] = best[1]
    changed = True
    while changed:
        changed = False
        for r in bigs:
            if r in assign:
                continue
            best = min(((_dist(cbb[r], cbb[q]), assign[q]) for q in bigs if q in assign), default=(1e9, None))
            if best[0] <= grow:
                assign[r] = best[1]
                changed = True
    aunits = [(_ubb(u), assign[r]) for r in bigs if r in assign for u in comps[r] if u["w"] < 1500]
    for r in smalls:
        best = min(((_dist(cbb[r], ub), t) for ub, t in aunits), default=(1e9, None))
        if best[0] <= attach:
            assign[r] = best[1]
    left = [r for r in comps if r not in assign]
    lp = {r: r for r in left}

    def lf(a):
        while lp[a] != a:
            lp[a] = lp[lp[a]]
            a = lp[a]
        return a
    for i, a in enumerate(left):
        for b in left[i + 1:]:
            if _dist(cbb[a], cbb[b]) <= 150:
                lp[lf(a)] = lf(b)
    groups = collections.defaultdict(list)
    for r in comps:
        groups[assign.get(r) or ("U:" + lf(r))] += comps[r]
    tname = {t["id"]: " ".join(t["label"].split()) for t in titles}
    flows, leftovers = [], []
    for key, us in groups.items():
        rec = dict(title=tname.get(key), title_id=key if key in tname else None, unit_ids=[u["id"] for u in us], bbox=_bbox(us), n=len(us))
        if rec["title"]:
            flows.append(rec)
        else:
            biggest = max(us, key=lambda u: (float(u["style"].get("fontSize", 10) or 10), len(u["label"])))
            rec["hint"] = " ".join(biggest["label"].split())[:60]
            leftovers.append(rec)
    flows.sort(key=lambda f: (round(f["bbox"][1] / 900), f["bbox"][0]))
    leftovers.sort(key=lambda f: -f["n"])
    return flows, leftovers


def extract(xml: str, unit_ids, margin=(60, 110)) -> str:
    """Build a stand-alone single-page mxfile holding the given top-level shapes, their children,
    the connectors between them and connector labels; coordinates are moved to the page origin."""
    root = drawio._parse(xml.encode("utf-8"))
    model = root.find("diagram").find("mxGraphModel")
    cells_root = model.find("root")
    wrap = {}                                    # id -> top-level element under <root> (mxCell or <object>)
    node = {}
    for el in cells_root:
        cid = el.get("id")
        wrap[cid] = el
        node[cid] = el if el.tag == "mxCell" else el.find("mxCell")
    keep = set(unit_ids)
    changed = True
    while changed:                               # descendants of kept vertices
        changed = False
        for cid, n in node.items():
            if n is not None and cid not in keep and n.get("parent") in keep:
                keep.add(cid)
                changed = True
    for cid, n in node.items():                  # connectors fully inside the flow (or dangling from it)
        if n is None or n.get("edge") != "1" or cid in keep:
            continue
        s, t = n.get("source"), n.get("target")
        if (s in keep or t in keep) and (s is None or s in keep) and (t is None or t in keep):
            keep.add(cid)
    changed = True
    while changed:                               # connector labels
        changed = False
        for cid, n in node.items():
            if n is not None and cid not in keep and n.get("parent") in keep:
                keep.add(cid)
                changed = True
    sc = drawio.scene(xml)
    tops = [sc["boxes"][i] for i in unit_ids if i in sc["boxes"]]
    bx, by = min(b["x"] for b in tops), min(b["y"] for b in tops)
    dx, dy = margin[0] - bx, margin[1] - by
    out_root = etree.Element("root")
    etree.SubElement(out_root, "mxCell", id="0")
    etree.SubElement(out_root, "mxCell", id="1", parent="0")
    for el in cells_root:
        cid = el.get("id")
        if cid in ("0", "1") or cid not in keep:
            continue
        c = copy.deepcopy(el)
        n = c if c.tag == "mxCell" else c.find("mxCell")
        if n.get("parent") not in keep:
            n.set("parent", "1")
            g = n.find("mxGeometry")
            if g is not None:
                if n.get("vertex") == "1":
                    g.set("x", str(round(float(g.get("x", 0) or 0) + dx, 2)))
                    g.set("y", str(round(float(g.get("y", 0) or 0) + dy, 2)))
                for pt in g.iter("mxPoint"):
                    if pt.get("x") is not None:
                        pt.set("x", str(round(float(pt.get("x")) + dx, 2)))
                    if pt.get("y") is not None:
                        pt.set("y", str(round(float(pt.get("y")) + dy, 2)))
        out_root.append(c)
    mx = etree.Element("mxfile", host="MEA Process Hub")
    d = etree.SubElement(mx, "diagram", id="flow", name="Flow")
    gm = etree.SubElement(d, "mxGraphModel", dx="1200", dy="800", grid="1", gridSize="10", guides="1", tooltips="1", connect="1",
                          arrows="1", fold="1", page="1", pageScale="1", pageWidth="1654", pageHeight="1169", math="0", shadow="0")
    gm.append(out_root)
    return etree.tostring(mx, encoding="unicode")


# ====================================================================== revamp: brand style, frame, master legend
ID_IN_TEXT = re.compile(r"\b([A-Z]{2,3})-([A-Z]{1,2})-([A-Z]{2,3})-\s?(\d)\s?(\d)\b")
ID_SPLIT_BY_MARKUP = re.compile(r"([A-Z]{2,3}-[A-Z]{1,2}-[A-Z]{2,3}-\d)((?:\s|<[^>]*>)+)(\d)(?!\d)")
TERMINATOR_WORDS = re.compile(r"^(start|start process|end|exit|complete|completed|return|finish|stop)\b", re.I)
NOTE_SHAPES = {"dataStorage", "note", "note2", "card", "tape", "callout", "document", "internalStorage"}
NEUTRAL = {"", "none", "default", "#000000", "#36393d", "#666666", "#ffffff", "#999999", "#484848", "#333333"}
FONT = "fontFamily=Arial;"


def _sd(style):
    d, order = {}, []
    for part in (style or "").split(";"):
        if not part:
            continue
        k, v = (part.split("=", 1) + [None])[:2] if "=" in part else (part, None)
        if k not in d:
            order.append(k)
        d[k] = v
    return d, order


def _ss(d, order):
    return ";".join(k if d[k] is None else f"{k}={d[k]}" for k in order if k in d) + ";"


def role_for(color, dept, legend):
    c = (color or "").lower()
    if c in NEUTRAL:
        return None
    ov = (legend.get("department_overrides") or {}).get(dept or "", {})
    return ov.get(c) or legend.get("aliases", {}).get(c) or legend.get("by_color", {}).get(c)


def revamp(flow_xml: str, name: str, pid: str, dept: str, legend: dict, meta: dict | None = None) -> str:
    """Restyle one extracted flow to the dormakaba process-map style, keep role colours (normalised to the
    master legend), wrap it in a titled frame and add the master legend. Shapes are tagged with meaKind / meaRole
    so the tool can read activities and responsibilities back out of the diagram."""
    root = drawio._parse(flow_xml.encode("utf-8"))
    cells_root = root.find("diagram").find("mxGraphModel").find("root")
    node = {}
    for el in cells_root:
        node[el.get("id")] = (el, el if el.tag == "mxCell" else el.find("mxCell"))
    incoming, outgoing = collections.Counter(), collections.Counter()
    for cid, (el, n) in node.items():
        if n is not None and n.get("edge") == "1":
            if n.get("source"):
                outgoing[n.get("source")] += 1
            if n.get("target"):
                incoming[n.get("target")] += 1
    canon = {r["role"]: r["color"] for r in legend.get("roles", [])}
    used_roles = []
    for cid, (el, n) in node.items():
        if n is None or cid in ("0", "1"):
            continue
        label_attr = "value" if el.tag == "mxCell" else "label"
        raw = el.get(label_attr) or ""
        fixed = ID_IN_TEXT.sub(lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}{m.group(5)}", raw.replace("\xa0", " ").replace("&nbsp;", " "))
        fixed = ID_SPLIT_BY_MARKUP.sub(lambda m: m.group(1) + m.group(3) + m.group(2), fixed)      # "WL-S-QC-0</b> 1" -> "WL-S-QC-01</b> "
        if fixed != raw:
            el.set(label_attr, fixed)
        text = drawio.strip_tags(fixed)
        d, order = _sd(n.get("style"))

        def put(k, v):
            if k not in d:
                order.append(k)
            d[k] = v
        if n.get("edge") == "1":
            lab = text.strip().lower()
            if not lab:                                         # label may live in a child edgeLabel cell
                for cid2, (el2, n2) in node.items():
                    if n2 is not None and n2.get("parent") == cid and n2.get("vertex") == "1":
                        lab = drawio.strip_tags(el2.get("value") or "").strip().lower()
                        break
            col = "#009900" if lab in ("yes", "y", "approved", "ok") else ("#E4002B" if lab in ("no", "n", "rejected", "not ok") else "#484848")
            put("strokeColor", col); put("strokeWidth", "1.5"); put("fontColor", "#484848"); put("fontFamily", "Arial"); put("endArrow", d.get("endArrow") or "classic")
            n.set("style", _ss(d, order))
            g = n.find("mxGeometry")                            # a label dragged far off its connector on the canvas returns to the connector
            for off in (g.findall("mxPoint") if g is not None else []):
                if off.get("as") == "offset" and max(abs(drawio._num(off.get("x"))), abs(drawio._num(off.get("y")))) > STRAY_LABEL:
                    g.remove(off)
            continue
        if n.get("vertex") != "1":
            continue
        first = order[0] if order else ""
        shape = d.get("shape") or ""
        geom = n.find("mxGeometry")
        h = float(geom.get("height", 40) or 40) if geom is not None else 40
        if "swimlane" in d or shape in ("table", "tableRow", "partialRectangle", "image") or "group" in d or first in ("group", "edgeLabel"):
            if first == "edgeLabel":
                put("fontFamily", "Arial"); put("fontColor", "#484848"); n.set("style", _ss(d, order))
            elif "swimlane" in d and d.get("horizontal") == "0":
                put("fillColor", "#003594"); put("strokeColor", "#003594"); put("fontColor", "#FFFFFF"); put("fontFamily", "Arial"); n.set("style", _ss(d, order))
            continue
        role = role_for(d.get("strokeColor"), dept, legend)
        if first == "text" or (d.get("strokeColor") == "none" and d.get("fillColor") in (None, "none")):
            kind = "ref" if ID_IN_TEXT.search(text) else "text"
            put("fontFamily", "Arial")
            if kind == "ref":
                put("fontColor", "#003594")
            put("meaKind", kind)
            n.set("style", _ss(d, order))
            continue
        if shape in NOTE_SHAPES:
            kind = "note"
            d, order = {}, []
            for k, v in (("shape", "note"), ("size", "12"), ("whiteSpace", "wrap"), ("html", "1"), ("fillColor", "#FFFFE0"), ("strokeColor", "#BFBFBF"),
                         ("fontColor", "#484848"), ("fontFamily", "Arial"), ("fontSize", "9"), ("align", "left"), ("verticalAlign", "top"), ("spacingLeft", "4"), ("spacingRight", "10")):
                put(k, v)
        elif first == "rhombus" or shape == "rhombus":
            kind = "decision"
            keep_fs = d.get("fontSize") or "10"
            d, order = {}, []
            for k, v in (("rhombus", None), ("whiteSpace", "wrap"), ("html", "1"), ("fillColor", "#FFFFFF"), ("strokeColor", canon.get(role, "#E4002B")),
                         ("strokeWidth", "2"), ("fontColor", "#484848"), ("fontFamily", "Arial"), ("fontSize", keep_fs), ("fontStyle", "1")):
                put(k, v)
        elif ID_IN_TEXT.search(text) and re.search(r"\bRef\b|\[|\bS#", text):
            kind = "ref"
            keep_fs = d.get("fontSize") or "10"
            d, order = {}, []
            for k, v in (("shape", "process"), ("size", "0.06"), ("whiteSpace", "wrap"), ("html", "1"), ("fillColor", "#E6E6E6"), ("strokeColor", "#003594"),
                         ("fontColor", "#003594"), ("fontFamily", "Arial"), ("fontSize", keep_fs), ("fontStyle", "1")):
                put(k, v)
            role = None
        elif first == "ellipse" or (d.get("rounded") == "1" and float(d.get("arcSize") or 0) >= 40) or (TERMINATOR_WORDS.match(text.strip()) and h <= 50 and len(text) < 30) \
                or (incoming[cid] == 0 and outgoing[cid] >= 1 and d.get("rounded") == "1" and len(text) < 40 and h <= 45 and text.upper() == text):
            kind = "start" if incoming[cid] == 0 and outgoing[cid] >= 1 else ("end" if outgoing[cid] == 0 else "start")
            keep_fs = d.get("fontSize") or "10"
            d, order = {}, []
            for k, v in (("rounded", "1"), ("arcSize", "50"), ("whiteSpace", "wrap"), ("html", "1"), ("fillColor", "#FFFFFF"),
                         ("strokeColor", "#009900" if kind == "start" else "#000000"), ("strokeWidth", "2" if kind == "start" else "3"),
                         ("fontColor", "#484848"), ("fontFamily", "Arial"), ("fontSize", keep_fs), ("fontStyle", "1")):
                put(k, v)
            role = None
        else:
            kind = "activity"
            keep = {k: d.get(k) for k in ("fontSize", "align", "verticalAlign", "spacingLeft", "spacing") if d.get(k)}
            d, order = {}, []
            for k, v in (("rounded", "1"), ("arcSize", "12"), ("whiteSpace", "wrap"), ("html", "1"), ("fillColor", "#FFFFFF"),
                         ("strokeColor", canon.get(role, "#484848")), ("strokeWidth", "2" if role else "1.5"), ("fontColor", "#484848"), ("fontFamily", "Arial")):
                put(k, v)
            for k, v in keep.items():
                put(k, v)
        put("meaKind", kind)
        if role:
            put("meaRole", role)
            if role not in used_roles:
                used_roles.append(role)
        n.set("style", _ss(d, order))
    finish(root, cells_root, name, pid, dept, legend, used_roles, meta)
    return etree.tostring(root, encoding="unicode")


def finish(root, cells_root, name, pid, dept, legend, used_roles, meta=None):
    """Wrap the shapes of a flow in the titled frame, add the master legend and the file attributes (in place)."""
    tmp = etree.tostring(root, encoding="unicode")
    sc = drawio.scene(tmp)
    tops = [b for b in sc["boxes"].values() if b["parent"] in ("1", None)]
    x0, y0 = min(b["x"] for b in tops), min(b["y"] for b in tops)
    x1, y1 = max(b["x"] + b["w"] for b in tops), max(b["y"] + b["h"] for b in tops)
    legend_cells, lw, lh = legend_block(legend, used_roles, x0, y1 + 50)
    fx, fy = x0 - 40, y0 - 70
    fw, fh = max(x1 - x0, lw) + 80, (y1 - y0) + lh + 70 + 90
    title = f"Process Map – {name} – {pid}" if pid else f"Process Map – {name}"
    frame = etree.Element("mxCell", id="mea_frame", value=title, vertex="1", parent="1",
                          style="swimlane;whiteSpace=wrap;html=1;fillColor=#003594;fontColor=#FFFFFF;strokeColor=#003594;fontSize=14;fontStyle=1;fontFamily=Arial;startSize=34;swimlaneFillColor=#FFFFFF;connectable=0;meaKind=frame;")
    g = etree.SubElement(frame, "mxGeometry", x=str(round(fx, 1)), y=str(round(fy, 1)), width=str(round(fw, 1)), height=str(round(fh, 1)))
    g.set("as", "geometry")
    cells_root.insert(2, frame)                              # behind every shape
    for c in legend_cells:
        cells_root.append(c)
    root.set("host", "MEA Process Hub")
    for k, v in dict(meaProcessId=pid or "", meaName=name, meaDept=dept or "", **(meta or {})).items():
        root.set(k, str(v))
    d0 = root.find("diagram")
    d0.set("name", pid or name[:40])
    d0.set("id", re.sub(r"[^A-Za-z0-9]", "", pid or "") or "flow")


def legend_block(legend: dict, used_roles, x, y):
    """Master legend: shape key + role colour key (roles present in this flow are emphasised)."""
    cells = []

    def cell(cid, value, style, gx, gy, gw, gh, parent="mea_legend"):
        c = etree.Element("mxCell", id=cid, value=value, style=style + "meaKind=legend;", vertex="1", parent=parent)
        g = etree.SubElement(c, "mxGeometry", x=str(gx), y=str(gy), width=str(gw), height=str(gh))
        g.set("as", "geometry")
        cells.append(c)
    roles = legend.get("roles", [])
    cols = 5
    cw, ch = 168, 22
    rows = (len(roles) + cols - 1) // cols
    width = max(cols * (cw + 6) + 20, 700)
    height = 96 + (rows * (ch + 5) + 34 if roles else 0)
    cell("mea_legend", "", "group;connectable=0;rounded=0;fillColor=none;strokeColor=none;", x, y, width, height, parent="1")
    cell("mea_lg_bg", "", "rounded=0;whiteSpace=wrap;html=1;fillColor=#F7F7F7;strokeColor=#BFBFBF;dashed=1;connectable=0;", 0, 0, width, height)
    cell("mea_lg_t", "Master legend", "text;html=1;align=left;verticalAlign=middle;fontFamily=Arial;fontSize=12;fontStyle=1;fontColor=#003594;", 10, 6, 240, 20)
    key = [("Start", "rounded=1;arcSize=50;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#009900;strokeWidth=2;fontStyle=1;", 86),
           ("End", "rounded=1;arcSize=50;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#000000;strokeWidth=3;fontStyle=1;", 86),
           ("Activity (outline = role)", "rounded=1;arcSize=12;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#484848;strokeWidth=1.5;", 150),
           ("Decision", "rhombus;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#E4002B;strokeWidth=2;fontStyle=1;", 96),
           ("Linked process (Ref ID)", "shape=process;size=0.06;whiteSpace=wrap;html=1;fillColor=#E6E6E6;strokeColor=#003594;fontColor=#003594;fontStyle=1;", 150),
           ("Note / checklist", "shape=note;size=10;whiteSpace=wrap;html=1;fillColor=#FFFFE0;strokeColor=#BFBFBF;", 110)]
    kx = 10
    for i, (lab, st, w) in enumerate(key):
        cell(f"mea_lg_k{i}", lab, st + "fontFamily=Arial;fontSize=9;fontColor=#484848;", kx, 34, w, 40 if "rhombus" in st else 28)
        kx += w + 12
    for i, (lab, col) in enumerate((("Yes", "#009900"), ("No", "#E4002B"))):
        cell(f"mea_lg_y{i}", f"— {lab} →", f"text;html=1;align=left;verticalAlign=middle;fontFamily=Arial;fontSize=9;fontStyle=1;fontColor={col};", kx, 34 + i * 18, 110, 16)
    if roles:
        cell("mea_lg_r", "Responsible role = outline colour (bold = used in this flow)", "text;html=1;align=left;verticalAlign=middle;fontFamily=Arial;fontSize=10;fontStyle=1;fontColor=#484848;", 10, 82, 500, 18)
        for i, r in enumerate(roles):
            used = r["role"] in used_roles
            cell(f"mea_lg_c{i}", r["role"], f"rounded=1;arcSize=12;whiteSpace=wrap;html=1;fillColor={'#FFFFFF' if used else '#F7F7F7'};strokeColor={r['color']};strokeWidth={'3' if used else '1.5'};"
                 f"fontFamily=Arial;fontSize=8;fontColor=#484848;fontStyle={'1' if used else '0'};", 10 + (i % cols) * (cw + 6), 104 + (i // cols) * (ch + 5), cw, ch)
    return cells, width, height


def build_all(canvas_xml: str, mapping: dict):
    """Apply a mapping (title/hint -> process) to a master canvas. Returns (built, unmatched, fragments_xml)."""
    flows, leftovers = segment(canvas_xml)
    legend = dict(mapping.get("legend", {}))
    legend["by_color"] = {}
    for r in legend.get("roles", []):                      # first role listed for a colour is the default; later ones apply per department only
        legend["by_color"].setdefault(r["color"].lower(), r["role"])
    legend["aliases"] = {k.lower(): v for k, v in legend.get("aliases", {}).items()}
    legend["department_overrides"] = {d: {k.lower(): v for k, v in m.items()} for d, m in legend.get("department_overrides", {}).items()}
    pools = {"title": collections.defaultdict(list), "hint": []}
    for f in flows:
        pools["title"][f["title"]].append(f)
    for v in pools["title"].values():
        v.sort(key=lambda f: (round(f["bbox"][1] / 900), f["bbox"][0]))
    left_sorted = sorted(leftovers, key=lambda f: f["bbox"][0])
    used, built = set(), []
    for spec in mapping["flows"]:
        cand = None
        if "title" in spec:
            lst = pools["title"].get(spec["title"], [])
            cand = lst[spec.get("nth", 0)] if len(lst) > spec.get("nth", 0) else None
        else:
            lst = [f for f in left_sorted if f["hint"].startswith(spec["hint"])]
            cand = lst[spec.get("nth", 0)] if len(lst) > spec.get("nth", 0) else None
        if cand is None:
            built.append(dict(spec=spec, xml=None, error="not found on canvas"))
            continue
        used.add(id(cand))
        fx = extract(canvas_xml, cand["unit_ids"])
        meta = dict(meaKind=spec.get("kind", "sop"), meaAttach="1" if spec.get("attach") else "0", meaProvisional="1" if spec.get("provisional") else "0",
                    meaCanvasTitle=spec.get("title") or spec.get("hint"), meaNote=spec.get("note", ""), meaCategory=spec.get("category", ""))
        if spec.get("id_corrections"):
            import json as _json
            meta["meaIdCorrections"] = _json.dumps(spec["id_corrections"], ensure_ascii=False)
        built.append(dict(spec=spec, shapes=cand["n"], xml=revamp(fx, spec["name"], spec["id"], spec.get("dept", "E2E"), legend, meta)))
    rest = [f for f in flows + leftovers if id(f) not in used]
    frag = None
    if rest:
        ids = [i for f in rest for i in f["unit_ids"]]
        frag = extract(canvas_xml, ids)
    return built, rest, frag


if __name__ == "__main__":                                   # python -m mea_hub.canvas <canvas.drawio> <mapping.json> <outdir>
    import json
    import os
    import sys
    src, mp, out = sys.argv[1:4]
    with open(src, encoding="utf-8") as f:
        page = list(drawio.split_pages(f.read()))[0][1]
    with open(mp, encoding="utf-8") as f:
        mapping = json.load(f)
    os.makedirs(out, exist_ok=True)
    built, rest, frag = build_all(page, mapping)
    for b in built:
        if b["xml"] is None:
            print("NOT FOUND:", b["spec"].get("title") or b["spec"].get("hint"))
            continue
        fn = os.path.join(out, re.sub(r"[^A-Za-z0-9._-]+", "_", f"{b['spec']['id']}_{b['spec']['name']}")[:90] + ".drawio")
        with open(fn, "w", encoding="utf-8") as f:
            f.write(b["xml"])
    if frag and mapping.get("fragments"):
        fr = mapping["fragments"]
        legend = dict(mapping.get("legend", {}), by_color={}, aliases={}, department_overrides={}, roles=[])
        x = revamp(frag, fr["name"], fr["id"], fr.get("dept", "E2E"), legend, dict(meaKind="reference", meaAttach="0", meaProvisional="1", meaNote=fr.get("note", ""), meaCategory="Canvas remnants"))
        with open(os.path.join(out, re.sub(r"[^A-Za-z0-9._-]+", "_", f"{fr['id']}_{fr['name']}")[:90] + ".drawio"), "w", encoding="utf-8") as f:
            f.write(x)
    print(f"{sum(1 for b in built if b['xml'])} flow files written, {len(rest)} unmapped groups ({sum(f['n'] for f in rest)} shapes) -> fragments file")
    for f in rest:
        if f["n"] >= 6:
            print("  unmapped:", (f.get("title") or f.get("hint") or "")[:70], f["n"], flush=True)
