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


def _geom(cell):
    g = cell.find("mxGeometry")
    if g is None:
        return None
    try:
        return (float(g.get("x", 0)), float(g.get("y", 0)), float(g.get("width", 0)), float(g.get("height", 0)))
    except ValueError:
        return None


def to_svg(xml: str, links: dict | None = None) -> str:
    """Simplified server-side SVG rendering (fallback preview / 'Export SVG'). The draw.io editor's own
    export is authoritative; this renderer covers rectangles, rounded boxes, ellipses, rhombi, text,
    straight/orthogonal edges and embedded images."""
    root = _parse(xml.encode("utf-8"))
    d = root.find("diagram")
    model = d.find("mxGraphModel")
    cells = {}
    for c in model.iter("mxCell", "object"):
        node = c if c.tag == "mxCell" else c.find("mxCell")
        if node is None:
            continue
        cid = c.get("id")
        label = c.get("label") if c.tag == "object" else c.get("value")
        cells[cid] = (node, strip_tags(label or ""))
    parts, minx, miny, maxx, maxy = [], 1e9, 1e9, -1e9, -1e9
    boxes = {}
    for cid, (node, label) in cells.items():
        if node.get("vertex") == "1":
            g = _geom(node)
            if not g:
                continue
            x, y, w, h = g
            boxes[cid] = g
            minx, miny, maxx, maxy = min(minx, x), min(miny, y), max(maxx, x + w), max(maxy, y + h)
    for cid, (node, label) in cells.items():
        if node.get("vertex") != "1" or cid not in boxes:
            continue
        x, y, w, h = boxes[cid]
        st = node.get("style") or ""
        sd = dict(p.split("=", 1) for p in st.split(";") if "=" in p)
        fill, stroke = sd.get("fillColor", "#ffffff"), sd.get("strokeColor", "#333333")
        if st.startswith("shape=image") or "shape=image" in st:
            href = sd.get("image", "")
            if href.startswith("data:image/png,"):
                href = href.replace("data:image/png,", "data:image/png;base64,")
            parts.append(f'<image x="{x}" y="{y}" width="{w}" height="{h}" href="{escape(href, quote=True)}"/>')
            continue
        if "ellipse" in st.split(";")[0] or sd.get("shape") == "ellipse":
            shp = f'<ellipse cx="{x+w/2}" cy="{y+h/2}" rx="{w/2}" ry="{h/2}" fill="{fill}" stroke="{stroke}"/>'
        elif st.startswith("rhombus") or sd.get("shape") == "rhombus":
            shp = f'<polygon points="{x+w/2},{y} {x+w},{y+h/2} {x+w/2},{y+h} {x},{y+h/2}" fill="{fill}" stroke="{stroke}"/>'
        else:
            rx = 8 if "rounded=1" in st else 0
            shp = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}"/>'
        txt = ""
        if label:
            words, lines, cur = label.split(), [], ""
            for wd in words:
                if len(cur) + len(wd) + 1 > max(8, int(w / 7)):
                    lines.append(cur)
                    cur = wd
                else:
                    cur = (cur + " " + wd).strip()
            lines.append(cur)
            y0 = y + h / 2 - (len(lines) - 1) * 7
            txt = "".join(f'<text x="{x+w/2}" y="{y0+i*14+4}" text-anchor="middle" font-size="12" font-family="Arial">{escape(l)}</text>' for i, l in enumerate(lines))
        grp = f"<g>{shp}{txt}</g>"
        if links and cid in links:
            grp = f'<a href="{escape(links[cid], quote=True)}">{grp}</a>'
        parts.append(grp)
    for cid, (node, label) in cells.items():
        if node.get("edge") != "1":
            continue
        s, t = boxes.get(node.get("source")), boxes.get(node.get("target"))
        if not s or not t:
            continue
        x1, y1 = s[0] + s[2] / 2, s[1] + s[3] / 2
        x2, y2 = t[0] + t[2] / 2, t[1] + t[3] / 2
        if abs(x2 - x1) >= abs(y2 - y1):
            x1 += s[2] / 2 * (1 if x2 > x1 else -1)
            x2 -= t[2] / 2 * (1 if x2 > x1 else -1)
        else:
            y1 += s[3] / 2 * (1 if y2 > y1 else -1)
            y2 -= t[3] / 2 * (1 if y2 > y1 else -1)
        parts.insert(0, f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#333" stroke-width="1.5" marker-end="url(#a)"/>')
    if minx > maxx:
        minx = miny = 0
        maxx = maxy = 100
    pad = 20
    vb = f"{minx-pad} {miny-pad} {maxx-minx+2*pad} {maxy-miny+2*pad}"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="{maxx-minx+2*pad}" height="{maxy-miny+2*pad}">'
            f'<defs><marker id="a" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="#333"/></marker></defs>'
            f'{"".join(parts)}</svg>')
