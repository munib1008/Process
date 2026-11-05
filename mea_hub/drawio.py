"""draw.io (mxGraph) XML helpers: safe validation, templates, node metadata, fallback SVG preview."""
import base64
import re
import urllib.parse
import zlib
from html import escape

from lxml import etree

from .security import strip_tags, unsafe_xml

PARSER = dict(resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False, huge_tree=False)


class DiagramError(ValueError):
    pass


def _parse(xml_bytes: bytes):
    if unsafe_xml(xml_bytes):
        raise DiagramError("DOCTYPE/ENTITY declarations are not allowed in diagram XML.")
    try:
        return etree.fromstring(xml_bytes, etree.XMLParser(**PARSER))
    except etree.XMLSyntaxError as e:
        raise DiagramError(f"Diagram XML is not well-formed: {e}")


def _inflate(text: str) -> bytes:
    raw = base64.b64decode(text.strip())
    return zlib.decompress(raw, -15)


def normalize(xml: str) -> str:
    """Validate and return an *uncompressed* <mxfile> document. Rejects unsafe/invalid XML."""
    if not xml or len(xml) > 30_000_000:
        raise DiagramError("Empty or oversized diagram.")
    root = _parse(xml.encode("utf-8"))
    if root.tag == "mxGraphModel":
        wrap = etree.Element("mxfile")
        d = etree.SubElement(wrap, "diagram", name="Page-1", id="p1")
        d.append(root)
        root = wrap
    if root.tag != "mxfile":
        raise DiagramError("Not a draw.io document (expected <mxfile> or <mxGraphModel>).")
    diagrams = root.findall("diagram")
    if not diagrams:
        raise DiagramError("The draw.io file contains no pages.")
    for d in diagrams:
        if d.find("mxGraphModel") is None:
            txt = (d.text or "").strip()
            if not txt:
                raise DiagramError("Empty diagram page.")
            try:
                inner = urllib.parse.unquote(_inflate(txt).decode("utf-8"))
            except Exception:
                raise DiagramError("Could not decode compressed diagram page.")
            d.text = None
            d.append(_parse(inner.encode("utf-8")))
        model = d.find("mxGraphModel")
        if model.find("root") is None:
            raise DiagramError("Diagram page has no <root> element.")
    return etree.tostring(root, encoding="unicode")


def esc_attr(s: str) -> str:
    return escape(s, quote=True)


def reference_diagram(title: str, chart_id: str, png_b64: str, w: int, h: int, note: str) -> str:
    """Editable diagram that carries the original image as a *locked* reference layer,
    plus a validation banner. Users trace/redraw on top and then delete the reference."""
    scale = min(1.0, 900.0 / max(w, 1))
    iw, ih = int(w * scale), int(h * scale)
    img_style = f"shape=image;verticalLabelPosition=bottom;labelBackgroundColor=default;verticalAlign=top;aspect=fixed;imageAspect=0;image=data:image/png,{png_b64};locked=1;"
    banner = (f'<mxCell id="banner" value="{esc_attr(note)}" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;'
              f'strokeColor=#d6b656;fontSize=12;align=left;spacingLeft=8;" vertex="1" parent="1">'
              f'<mxGeometry x="0" y="-70" width="{max(iw, 420)}" height="56" as="geometry"/></mxCell>')
    return (f'<mxfile host="MEA Process Hub"><diagram id="{esc_attr(chart_id or "d1")}" name="{esc_attr(title[:60])}">'
            f'<mxGraphModel dx="1000" dy="700" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
            f'fold="1" page="1" pageScale="1" pageWidth="1169" pageHeight="827" math="0" shadow="0"><root>'
            f'<mxCell id="0"/><mxCell id="1" parent="0"/>'
            f'<mxCell id="ref_img" value="Source reference (locked) - {esc_attr(chart_id or "")}" style="{img_style}" vertex="1" parent="1">'
            f'<mxGeometry x="0" y="0" width="{iw}" height="{ih}" as="geometry"/></mxCell>{banner}'
            f'</root></mxGraphModel></diagram></mxfile>')


TEMPLATES = {
    "blank": ("Blank process", []),
    "department_workflow": ("Department workflow", ["Start|ellipse", "Activity 1|rect", "Decision?|rhombus", "Activity 2|rect", "End|ellipse"]),
    "approval_workflow": ("Approval workflow", ["Request|ellipse", "Prepare|rect", "Review?|rhombus", "Approve|rect", "Rejected / Rework|rect", "Done|ellipse"]),
    "sap_process_flow": ("SAP process flow", ["Trigger|ellipse", "SAP transaction (e.g. ME51N)|rect", "Check|rhombus", "Post / Release|rect", "End|ellipse"]),
    "exception_handling": ("Exception handling", ["Exception raised|ellipse", "Assess|rect", "Escalate?|rhombus", "Escalate to manager|rect", "Resolve & record|rect", "Closed|ellipse"]),
    "cross_functional_swimlane": ("Cross-functional swimlane", ["Start|ellipse", "Dept A activity|rect", "Dept B activity|rect", "Decision?|rhombus", "End|ellipse"]),
}
for _k, _t in (("enterprise_e2e", "Enterprise E2E workflow"), ("raci_workflow", "RACI-related workflow"),
               ("material_master_lifecycle", "Material master lifecycle"), ("procurement_workflow", "Procurement workflow"),
               ("production_workflow", "Production workflow"), ("logistics_workflow", "Logistics workflow"),
               ("service_workflow", "Service workflow")):
    TEMPLATES[_k] = (_t, ["Start|ellipse", "Step 1|rect", "Step 2|rect", "Decision?|rhombus", "Step 3|rect", "End|ellipse"])


def template_xml(key: str, title: str, swimlanes: bool = False) -> str:
    name, steps = TEMPLATES.get(key, TEMPLATES["blank"])
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    styles = {"rect": "rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;",
              "ellipse": "ellipse;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;",
              "rhombus": "rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;"}
    x = 40
    prev = None
    for i, s in enumerate(steps):
        label, shape = s.split("|")
        w, h = (120, 60) if shape != "rhombus" else (130, 80)
        cid = f"n{i+1}"
        cells.append(f'<mxCell id="{cid}" value="{esc_attr(label)}" style="{styles[shape]}" vertex="1" parent="1">'
                     f'<mxGeometry x="{x}" y="{120 - (h-60)//2}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        if prev:
            cells.append(f'<mxCell id="e{i}" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;" edge="1" parent="1" '
                         f'source="{prev}" target="{cid}"><mxGeometry relative="1" as="geometry"/></mxCell>')
        prev = cid
        x += w + 50
    return (f'<mxfile host="MEA Process Hub"><diagram id="d1" name="{esc_attr(title[:60] or name)}"><mxGraphModel dx="1000" dy="700" '
            f'grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
            f'pageWidth="1169" pageHeight="827"><root>{"".join(cells)}</root></mxGraphModel></diagram></mxfile>')


def nodes(xml: str):
    """Return [(id, label)] for every vertex/edge cell with text (all pages)."""
    out = []
    root = _parse(xml.encode("utf-8"))
    for cell in root.iter("mxCell", "object"):
        cid = cell.get("id")
        if cell.tag == "object":
            label = cell.get("label", "")
            inner = cell.find("mxCell")
            if inner is None or not (inner.get("vertex") or inner.get("edge")):
                continue
        else:
            label = cell.get("value", "")
            if not (cell.get("vertex") or cell.get("edge")) or cell.get("id") in ("0", "1"):
                continue
            if "image=data:" in (cell.get("style") or ""):
                label = label or ""
        out.append((cid, strip_tags(label)))
    return out


def labels_text(xml: str) -> str:
    try:
        return " ".join(l for _, l in nodes(xml) if l)
    except DiagramError:
        return ""


# ------------------------------------------------------------------ scene model + renderers
def _style(st: str) -> dict:
    d = {}
    for part in (st or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            d[k] = v
        elif part:
            d[part] = "1"
    d["_first"] = (st or "").split(";")[0]
    return d


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def scene(xml: str, page: int = 0) -> dict:
    """Parse one page into absolute-coordinate boxes and edges (children are relative to their parent)."""
    root = _parse(xml.encode("utf-8"))
    pages = root.findall("diagram")
    model = pages[min(page, len(pages) - 1)].find("mxGraphModel")
    raw = {}
    for c in model.iter("mxCell", "object"):
        node = c if c.tag == "mxCell" else c.find("mxCell")
        if node is None:
            continue
        label = c.get("label") if c.tag == "object" else c.get("value")
        raw[c.get("id")] = dict(node=node, label=label or "", parent=node.get("parent"))
    cache = {}

    def origin(cid):
        """Absolute top-left of cell `cid` (own geometry + all ancestors)."""
        if cid in cache:
            return cache[cid]
        r = raw.get(cid)
        if not r:
            return (0.0, 0.0)
        g = r["node"].find("mxGeometry")
        gx, gy = (_num(g.get("x")), _num(g.get("y"))) if g is not None else (0.0, 0.0)
        if r["parent"] in (None, "0", "1") or r["parent"] not in raw:
            cache[cid] = (gx, gy)
        else:
            px, py = origin(r["parent"])
            cache[cid] = (px + gx, py + gy)
        return cache[cid]

    boxes, edges = {}, []
    for cid, r in raw.items():
        n = r["node"]
        g = n.find("mxGeometry")
        if n.get("vertex") == "1" and g is not None:
            x, y = origin(cid)
            boxes[cid] = dict(id=cid, x=x, y=y, w=_num(g.get("width"), 60), h=_num(g.get("height"), 40), label=strip_tags(r["label"]), raw_label=r["label"],
                              style=_style(n.get("style")), parent=r["parent"], depth=0)
    for b in boxes.values():
        d, p = 0, b["parent"]
        while p in raw:
            d += 1
            p = raw[p]["parent"]
        b["depth"] = d
    for cid, r in raw.items():
        n = r["node"]
        if n.get("edge") == "1":
            ox, oy = origin(r["parent"]) if r["parent"] in raw and r["parent"] not in ("0", "1") else (0.0, 0.0)
            pts = []
            g = n.find("mxGeometry")
            if g is not None:
                arr = g.find("Array")
                if arr is not None:
                    pts = [(ox + _num(p.get("x")), oy + _num(p.get("y"))) for p in arr.findall("mxPoint")]
            edges.append(dict(id=cid, source=n.get("source"), target=n.get("target"), label=strip_tags(r["label"]), style=_style(n.get("style")), points=pts))
    return dict(boxes=boxes, edges=edges)


def _anchor(b, st, prefix, toward):
    fx, fy = st.get(prefix + "X"), st.get(prefix + "Y")
    if fx is not None and fy is not None:
        return b["x"] + _num(fx) * b["w"], b["y"] + _num(fy) * b["h"], None
    cx, cy = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
    dx, dy = toward[0] - cx, toward[1] - cy
    if abs(dx) * b["h"] >= abs(dy) * b["w"]:
        return (b["x"] + b["w"] if dx > 0 else b["x"]), cy, "h"
    return cx, (b["y"] + b["h"] if dy > 0 else b["y"]), "v"


def route(sc, e):
    bx = sc["boxes"]
    s, t = bx.get(e["source"]), bx.get(e["target"])
    if not s or not t:
        return None
    sc_c = (s["x"] + s["w"] / 2, s["y"] + s["h"] / 2)
    tc_c = (t["x"] + t["w"] / 2, t["y"] + t["h"] / 2)
    first = e["points"][0] if e["points"] else tc_c
    last = e["points"][-1] if e["points"] else sc_c
    x1, y1, o1 = _anchor(s, e["style"], "exit", first)
    x2, y2, o2 = _anchor(t, e["style"], "entry", last)
    pts = [(x1, y1)]
    if e["points"]:
        for p in e["points"]:
            pts.append((pts[-1][0], p[1]) if abs(p[0] - pts[-1][0]) > abs(p[1] - pts[-1][1]) and False else p)
        pts.append((x2, y2))
        return pts
    if "orthogonal" in e["style"].get("edgeStyle", "") or "orthogonalLoop" in e["style"]:
        if abs(x2 - x1) < 2 or abs(y2 - y1) < 2:
            pts.append((x2, y2))
        elif (o1 or "h") == "h":
            mx = (x1 + x2) / 2
            pts += [(mx, y1), (mx, y2), (x2, y2)]
        else:
            my = (y1 + y2) / 2
            pts += [(x1, my), (x2, my), (x2, y2)]
    else:
        pts.append((x2, y2))
    return pts


def _bounds(sc):
    xs = [b["x"] for b in sc["boxes"].values()] + [b["x"] + b["w"] for b in sc["boxes"].values()]
    ys = [b["y"] for b in sc["boxes"].values()] + [b["y"] + b["h"] for b in sc["boxes"].values()]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 100, 100)


def _color(v, default):
    if not v or v in ("none", "default"):
        return default
    return v if v.startswith("#") and len(v) in (4, 7) else default


def _wrap(text, width_px, fs):
    maxc = max(4, int(width_px / (fs * 0.55)))
    lines = []
    for para in text.split("\n"):
        cur = ""
        for w in para.split():
            if len(cur) + len(w) + 1 > maxc and cur:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        lines.append(cur)
    return lines


def to_svg(xml: str, links: dict | None = None, page: int = 0) -> str:
    sc = scene(xml, page)
    minx, miny, maxx, maxy = _bounds(sc)
    pad = 20
    vb = f"{minx - pad} {miny - pad} {maxx - minx + 2 * pad} {maxy - miny + 2 * pad}"
    parts = ['<defs><marker id="a" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="#333"/></marker></defs>']
    for b in sorted(sc["boxes"].values(), key=lambda b: b["depth"]):
        st, x, y, w, h = b["style"], b["x"], b["y"], b["w"], b["h"]
        fill, stroke = _color(st.get("fillColor"), "#ffffff"), _color(st.get("strokeColor"), "#333333")
        fs = _num(st.get("fontSize"), 12)
        fcol = _color(st.get("fontColor"), "#222222")
        bold = " font-weight=\"bold\"" if _num(st.get("fontStyle")) % 2 == 1 else ""
        if "image=" in (b["style"].get("image") and "image=" or ""):
            pass
        if st.get("shape") == "image":
            href = st.get("image", "")
            if href.startswith("data:image/png,"):
                href = href.replace("data:image/png,", "data:image/png;base64,")
            parts.append(f'<image x="{x}" y="{y}" width="{w}" height="{h}" href="{escape(href, quote=True)}"/>')
            continue
        first = st["_first"]
        txt_parts = []
        if first == "swimlane" or st.get("swimlane"):
            sz = _num(st.get("startSize"), 30)
            parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{stroke}"/>')
            if st.get("horizontal") == "0":
                parts.append(f'<rect x="{x}" y="{y}" width="{sz}" height="{h}" fill="{fill}" stroke="{stroke}"/>')
                if b["label"]:
                    parts.append(f'<text transform="translate({x + sz / 2 + fs * 0.35},{y + h / 2}) rotate(-90)" text-anchor="middle" font-size="{min(fs, 16)}" font-family="Arial" fill="{fcol}"{bold}>{escape(b["label"][:60])}</text>')
            else:
                parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{sz}" fill="{fill}" stroke="{stroke}"/>')
                if b["label"]:
                    parts.append(f'<text x="{x + w / 2}" y="{y + sz / 2 + fs * 0.35}" text-anchor="middle" font-size="{min(fs, 16)}" font-family="Arial" fill="{fcol}"{bold}>{escape(b["label"][:90])}</text>')
            continue
        if first.startswith("ellipse") or st.get("shape") == "ellipse":
            shp = f'<ellipse cx="{x + w / 2}" cy="{y + h / 2}" rx="{w / 2}" ry="{h / 2}" fill="{fill}" stroke="{stroke}" stroke-width="{_num(st.get("strokeWidth"), 1)}"/>'
        elif first.startswith("rhombus"):
            shp = f'<polygon points="{x + w / 2},{y} {x + w},{y + h / 2} {x + w / 2},{y + h} {x},{y + h / 2}" fill="{fill}" stroke="{stroke}" stroke-width="{_num(st.get("strokeWidth"), 1)}"/>'
        elif st.get("shape") == "step":
            o = min(_num(st.get("size"), 0) or 30, w / 3)
            shp = f'<polygon points="{x},{y} {x + w - o},{y} {x + w},{y + h / 2} {x + w - o},{y + h} {x},{y + h} {x + o},{y + h / 2}" fill="{fill}" stroke="{stroke}"/>'
        elif first == "text":
            shp = ""
        else:
            rx = (min(w, h) * _num(st.get("arcSize"), 20) / 100) if st.get("rounded") == "1" else 0
            dash = ' stroke-dasharray="5 3"' if st.get("dashed") == "1" else ""
            shp = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{_num(st.get("strokeWidth"), 1)}"{dash}/>'
        if b["label"]:
            lines = _wrap(b["label"], w - 10, fs)
            left = st.get("align") == "left"
            top = st.get("verticalAlign") == "top"
            y0 = (y + 6 + fs) if top else (y + h / 2 - (len(lines) - 1) * fs * 0.6 + fs * 0.35)
            tx = (x + 6) if left else (x + w / 2)
            anchor = "start" if left else "middle"
            txt_parts = [f'<text x="{tx}" y="{y0 + i * fs * 1.2}" text-anchor="{anchor}" font-size="{fs}" font-family="Arial" fill="{fcol}"{bold}>{escape(l)}</text>' for i, l in enumerate(lines[:14])]
        grp = f"<g>{shp}{''.join(txt_parts)}</g>"
        if links and b["id"] in links:
            grp = f'<a href="{escape(links[b["id"]], quote=True)}">{grp}</a>'
        parts.append(grp)
    for e in sc["edges"]:
        pts = route(sc, e)
        if not pts:
            continue
        col = _color(e["style"].get("strokeColor"), "#333333")
        dash = ' stroke-dasharray="6 4"' if e["style"].get("dashed") == "1" else ""
        parts.append(f'<polyline points="{" ".join(f"{px},{py}" for px, py in pts)}" fill="none" stroke="{col}" stroke-width="{min(_num(e["style"].get("strokeWidth"), 1.5), 3)}"{dash} marker-end="url(#a)"/>')
        if e["label"]:
            mx, my = pts[len(pts) // 2]
            parts.append(f'<text x="{mx}" y="{my - 4}" text-anchor="middle" font-size="12" font-family="Arial" fill="#222" stroke="#fff" stroke-width="3" paint-order="stroke">{escape(e["label"])}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="{maxx - minx + 2 * pad}" height="{maxy - miny + 2 * pad}">'
            f'<rect x="{minx - pad}" y="{miny - pad}" width="100%" height="100%" fill="#fff"/>{"".join(parts)}</svg>')


def _font(bold, size):
    from PIL import ImageFont
    try:
        import reportlab, os
        f = os.path.join(os.path.dirname(reportlab.__file__), "fonts", "VeraBd.ttf" if bold else "Vera.ttf")
        return ImageFont.truetype(f, max(6, int(size)))
    except Exception:
        return ImageFont.load_default()


def to_png(xml: str, page: int = 0, max_px: int = 3000):
    """Approximate raster preview using Pillow (used only until the draw.io editor produces the authoritative PNG)."""
    from PIL import Image, ImageDraw
    import io, math
    sc = scene(xml, page)
    if not sc["boxes"]:
        return None
    minx, miny, maxx, maxy = _bounds(sc)
    pad = 20
    k = min(1.5, max_px / max(1.0, (maxx - minx + 2 * pad)))
    W, H = int((maxx - minx + 2 * pad) * k), int((maxy - miny + 2 * pad) * k)
    if W * H > 40_000_000:
        k *= 0.5
        W, H = int((maxx - minx + 2 * pad) * k), int((maxy - miny + 2 * pad) * k)
    img = Image.new("RGB", (max(W, 10), max(H, 10)), "white")
    dr = ImageDraw.Draw(img)
    T = lambda x, y: ((x - minx + pad) * k, (y - miny + pad) * k)
    for b in sorted(sc["boxes"].values(), key=lambda b: b["depth"]):
        st = b["style"]
        x0, y0 = T(b["x"], b["y"])
        x1, y1 = T(b["x"] + b["w"], b["y"] + b["h"])
        fill, stroke = _color(st.get("fillColor"), "#ffffff"), _color(st.get("strokeColor"), "#333333")
        fs = _num(st.get("fontSize"), 12) * k
        bold = _num(st.get("fontStyle")) % 2 == 1
        fcol = _color(st.get("fontColor"), "#222222")
        first = st["_first"]
        if st.get("shape") == "image":
            href = st.get("image", "")
            if href.startswith("data:image/png,"):
                import base64
                try:
                    im = Image.open(io.BytesIO(base64.b64decode(href.split(",", 1)[1]))).convert("RGB").resize((max(1, int(x1 - x0)), max(1, int(y1 - y0))))
                    img.paste(im, (int(x0), int(y0)))
                except Exception:
                    pass
            continue
        font = _font(bold, min(fs, 22 * k))
        if first == "swimlane" or st.get("swimlane"):
            sz = _num(st.get("startSize"), 30) * k
            dr.rectangle([x0, y0, x1, y1], outline=stroke)
            if st.get("horizontal") == "0":
                dr.rectangle([x0, y0, x0 + sz, y1], fill=fill, outline=stroke)
                if b["label"]:
                    f2 = _font(True, min(fs, 15 * k))
                    tw = int(dr.textlength(b["label"][:60], font=f2)) + 6
                    tmp = Image.new("RGBA", (max(tw, 10), int(sz)), (0, 0, 0, 0))
                    ImageDraw.Draw(tmp).text((3, 2), b["label"][:60], font=f2, fill=fcol)
                    tmp = tmp.rotate(90, expand=True)
                    img.paste(tmp, (int(x0), int(y0 + (y1 - y0) / 2 - tmp.height / 2)), tmp)
            else:
                dr.rectangle([x0, y0, x1, y0 + sz], fill=fill, outline=stroke)
                if b["label"]:
                    f2 = _font(True, min(fs, 16 * k))
                    dr.text(((x0 + x1) / 2, y0 + sz / 2), b["label"][:90], font=f2, fill=fcol, anchor="mm")
            continue
        lw = max(1, int(_num(st.get("strokeWidth"), 1) * k))
        if first.startswith("ellipse") or st.get("shape") == "ellipse":
            dr.ellipse([x0, y0, x1, y1], fill=fill, outline=stroke, width=lw)
        elif first.startswith("rhombus"):
            dr.polygon([((x0 + x1) / 2, y0), (x1, (y0 + y1) / 2), ((x0 + x1) / 2, y1), (x0, (y0 + y1) / 2)], fill=fill, outline=stroke)
        elif st.get("shape") == "step":
            o = min(_num(st.get("size"), 0) or 30, b["w"] / 3) * k
            dr.polygon([(x0, y0), (x1 - o, y0), (x1, (y0 + y1) / 2), (x1 - o, y1), (x0, y1), (x0 + o, (y0 + y1) / 2)], fill=fill, outline=stroke)
        elif first != "text":
            if st.get("rounded") == "1":
                dr.rounded_rectangle([x0, y0, x1, y1], radius=min(x1 - x0, y1 - y0) * _num(st.get("arcSize"), 20) / 100, fill=fill, outline=stroke, width=lw)
            else:
                dr.rectangle([x0, y0, x1, y1], fill=fill, outline=stroke, width=lw)
        if b["label"]:
            lines = _wrap(b["label"], (x1 - x0) / k - 10, fs / k)[:14]
            lh = fs * 1.2
            left, top = st.get("align") == "left", st.get("verticalAlign") == "top"
            ty = (y0 + 6) if top else ((y0 + y1) / 2 - lh * len(lines) / 2)
            for i, l in enumerate(lines):
                if left:
                    dr.text((x0 + 6, ty + i * lh), l, font=font, fill=fcol)
                else:
                    dr.text(((x0 + x1) / 2, ty + i * lh + lh / 2), l, font=font, fill=fcol, anchor="mm")
    for e in sc["edges"]:
        pts = route(sc, e)
        if not pts:
            continue
        col = _color(e["style"].get("strokeColor"), "#333333")
        tp = [T(*p) for p in pts]
        dr.line(tp, fill=col, width=max(1, int(min(_num(e["style"].get("strokeWidth"), 1.5), 3) * k)))
        (ax, ay), (bx_, by_) = tp[-2], tp[-1]
        ang = math.atan2(by_ - ay, bx_ - ax)
        sz = 9 * k
        dr.polygon([(bx_, by_), (bx_ - sz * math.cos(ang - 0.4), by_ - sz * math.sin(ang - 0.4)), (bx_ - sz * math.cos(ang + 0.4), by_ - sz * math.sin(ang + 0.4))], fill=col)
        if e["label"]:
            mx, my = tp[len(tp) // 2]
            f3 = _font(False, 11 * k)
            tw = dr.textlength(e["label"], font=f3)
            dr.rectangle([mx - tw / 2 - 2, my - 8 * k, mx + tw / 2 + 2, my + 6 * k], fill="white")
            dr.text((mx, my - k), e["label"], font=f3, fill="#222", anchor="mm")
    bio = io.BytesIO()
    img.save(bio, "PNG", optimize=True)
    return bio.getvalue()


def page_count(xml: str) -> int:
    return len(_parse(xml.encode("utf-8")).findall("diagram"))


def split_pages(xml: str):
    """Yield (name, single-page mxfile xml) for every page of a (possibly multi-page) draw.io file."""
    root = _parse(xml.encode("utf-8"))
    norm = etree.fromstring(normalize(xml).encode())
    for d in norm.findall("diagram"):
        one = etree.Element("mxfile", **{k: v for k, v in norm.attrib.items() if k != "pages"})
        one.append(d)
        yield d.get("name") or "Page", etree.tostring(one, encoding="unicode")
