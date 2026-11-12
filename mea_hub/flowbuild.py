"""Build a standard dormakaba flow from plain text ("text-to-flow") and the shape library for Flow Studio.

One line per step:

    Sales: Receive customer purchase order            role from the master legend, then the activity
    Customer Service: Create sales order (VA01)
    Credit Controller: Credit limit sufficient?       a line ending with "?" is a decision
    No: Credit Controller: Block order, inform Sales  branch of the decision above (No: or Yes:), may be repeated
    No: End                                           ... and may finish at End
    Note: Check incoterms on the PO                   note attached to the step above
    Ref: WL-M-OB-01 Outbound delivery                 linked process
    Logistics: Create delivery (VL01N)

The result is tagged (meaKind / meaRole) exactly like the flows cut from the master canvas, carries the titled frame
and the master legend, and is therefore read back by flowread (activities, roles, SAP codes, notes).
Nothing is invented: a branch that is not continued in the text is left open and reported by the flow check."""
import base64
import difflib
import json
import math
import re
import zlib
from html import escape
from urllib.parse import quote

from lxml import etree

from . import canvas

FONT = "fontFamily=Arial;fontColor=#484848;"
ST = {
    "start": "rounded=1;arcSize=50;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#009900;strokeWidth=2;fontSize=11;fontStyle=1;" + FONT + "meaKind=start;",
    "end": "rounded=1;arcSize=50;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#000000;strokeWidth=3;fontSize=11;fontStyle=1;" + FONT + "meaKind=end;",
    "activity": "rounded=1;arcSize=12;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor={color};strokeWidth={sw};fontSize=11;" + FONT + "meaKind=activity;",
    "decision": "rhombus;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor={color};strokeWidth=2;fontSize=11;fontStyle=1;" + FONT + "meaKind=decision;",
    "ref": "shape=process;size=0.06;whiteSpace=wrap;html=1;fillColor=#E6E6E6;strokeColor=#003594;fontColor=#003594;fontFamily=Arial;fontSize=11;fontStyle=1;meaKind=ref;",
    "note": "shape=note;size=12;whiteSpace=wrap;html=1;fillColor=#FFFFE0;strokeColor=#BFBFBF;fontSize=9;align=left;verticalAlign=top;spacingLeft=4;spacingRight=10;" + FONT + "meaKind=note;",
    "edge": "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;strokeColor={color};strokeWidth=1.5;endArrow=classic;fontSize=10;fontStyle=1;fontFamily=Arial;fontColor={color};",
    "note_edge": "endArrow=none;dashed=1;html=1;strokeColor=#BFBFBF;strokeWidth=1;",
}
YES, NO, GREY = "#009900", "#E4002B", "#484848"
ID_RE = re.compile(r"\b[A-Z]{2,3}-[A-Z]{1,2}-[A-Z]{2,3}-\d{2}(?:\.\d+)?\b")
MAX_STEPS, MAX_LINE = 120, 400


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def role_index(legend):
    roles = {}
    for r in (legend or {}).get("roles", []):
        roles.setdefault(_norm(r["role"]).lower(), (r["role"], r["color"]))
    return roles


def _split_role(text, roles, warnings, line_no):
    """'Role: activity' -> (role, activity) when the prefix is a role of the master legend."""
    m = re.match(r"^([^:]{2,60}):\s*(\S.*)$", text)
    if not m:
        return "", text
    key = _norm(m.group(1)).lower()
    if key in roles:
        return roles[key][0], _norm(m.group(2))
    near = difflib.get_close_matches(key, list(roles), n=1, cutoff=0.75)
    if near:
        warnings.append(f"Line {line_no}: “{_norm(m.group(1))}” is not a role of the master legend (did you mean “{roles[near[0]][0]}”?). The line was kept as plain text without a role.")
    return "", text


def parse(text, legend):
    """-> (steps, start_label, end_label, warnings). A step: kind, text, role, notes, branch{label, steps, to_end}."""
    roles = role_index(legend)
    steps, warnings, start, end = [], [], "Start", "End"
    last = None                                              # the step a following Note:/branch line belongs to
    for line_no, raw in enumerate((text or "").splitlines(), 1):
        line = _norm(re.sub(r"^\s*(?:[-*•■]|\d+[.)])\s+", "", raw))
        if not line or line.startswith("#"):
            continue
        if len(line) > MAX_LINE:
            warnings.append(f"Line {line_no}: text shortened to {MAX_LINE} characters.")
            line = line[:MAX_LINE]
        m = re.match(r"^(start|end)\s*:\s*(\S.*)$", line, re.I)
        if m:
            if m.group(1).lower() == "start":
                start = m.group(2)
            else:
                end = m.group(2)
            continue
        m = re.match(r"^note\s*:\s*(\S.*)$", line, re.I)
        if m:
            if last is None:
                warnings.append(f"Line {line_no}: the note has no step above it and was skipped.")
            else:
                last["notes"].append(m.group(1))
            continue
        m = re.match(r"^(yes|no)\s*:\s*(\S.*)$", line, re.I)
        if m:
            dec = next((s for s in reversed(steps) if s["kind"] == "decision"), None)
            lab = m.group(1).capitalize()
            if dec is None or (steps[-1] is not dec):
                warnings.append(f"Line {line_no}: “{lab}:” must follow a decision (a line ending with “?”) directly. The line was added as a normal step.")
                line = m.group(2)
            else:
                br = dec["branch"]
                if br and br["label"] != lab:
                    warnings.append(f"Line {line_no}: the decision already has a “{br['label']}:” branch; write the other answer as the next normal line. The line was added as a normal step.")
                    line = m.group(2)
                else:
                    if not br:
                        br = dec["branch"] = dict(label=lab, steps=[], to_end=False)
                    if br["to_end"]:
                        warnings.append(f"Line {line_no}: the “{lab}:” branch already ends; the line was skipped.")
                    elif m.group(2).strip().lower() in ("end", "end.", "stop"):
                        br["to_end"] = True
                    else:
                        role, body = _split_role(m.group(2), roles, warnings, line_no)
                        st = _step(body, role)
                        if st["kind"] == "decision":
                            warnings.append(f"Line {line_no}: a decision inside a branch is drawn as a decision without branches – complete it in Flow Studio.")
                        br["steps"].append(st)
                        last = st
                    continue
        role, body = _split_role(line, roles, warnings, line_no)
        st = _step(body, role)
        steps.append(st)
        last = st
        if len(steps) > MAX_STEPS:
            warnings.append(f"Only the first {MAX_STEPS} steps were used.")
            steps.pop()
            break
    return steps, start, end, warnings


def _step(body, role):
    m = re.match(r"^(?:ref|link|linked process)\s*:\s*(\S.*)$", body, re.I)
    if m:
        return dict(kind="ref", text=m.group(1), role="", notes=[], branch=None)
    return dict(kind="decision" if body.rstrip().endswith("?") else "activity", text=body, role=role, notes=[], branch=None)


def _lines(text, per_line):
    return max(1, sum(math.ceil(max(1, len(p)) / per_line) for p in text.split("\n")))


def build(title, pid, dept, text, legend, meta=None):
    """-> (xml, warnings). Raises ValueError when the text contains no step."""
    steps, start_label, end_label, warnings = parse(text, legend)
    if not steps:
        raise ValueError("Write at least one step (one line per step).")
    colours = {name: col for name, col in role_index(legend).values()}
    root = etree.Element("mxfile", host="MEA Process Hub")
    diagram = etree.SubElement(root, "diagram", id="flow", name=(pid or title or "Flow")[:40])
    model = etree.SubElement(diagram, "mxGraphModel", dx="1200", dy="800", grid="1", gridSize="10", guides="1", tooltips="1", connect="1", arrows="1",
                             fold="1", page="0", pageScale="1", pageWidth="1654", pageHeight="1169", math="0", shadow="0")
    cells = etree.SubElement(model, "root")
    etree.SubElement(cells, "mxCell", id="0")
    etree.SubElement(cells, "mxCell", id="1", parent="0")
    used_roles, n_edge, n_note = [], [0], [0]
    has_branch = any(s["branch"] and (s["branch"]["steps"]) for s in steps)
    MAIN_X, MAIN_W, BR_X, BR_W = 240, 240, 570, 220
    NOTE_X = BR_X + (BR_W + 60 if has_branch else 0)
    notes_bottom = [0]

    def vertex(cid, label, style, x, y, w, h):
        c = etree.SubElement(cells, "mxCell", id=cid, value=escape(label, quote=False), style=style, vertex="1", parent="1")
        g = etree.SubElement(c, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h))
        g.set("as", "geometry")
        return cid

    def edge(src, dst, label="", colour=GREY, extra="", style=None, points=None):
        n_edge[0] += 1
        c = etree.SubElement(cells, "mxCell", id=f"e{n_edge[0]}", value=label, style=(style or ST["edge"].format(color=colour)) + extra, edge="1", parent="1", source=src, target=dst)
        g = etree.SubElement(c, "mxGeometry", relative="1")
        g.set("as", "geometry")
        if points:
            arr = etree.SubElement(g, "Array")
            arr.set("as", "points")
            for px, py in points:
                etree.SubElement(arr, "mxPoint", x=str(round(px, 1)), y=str(round(py, 1)))

    def shape(st, cid, x, w, y):
        """-> height. Draws the step and its notes."""
        role = st["role"]
        if role and role not in used_roles:
            used_roles.append(role)
        tag = f"meaRole={role};" if role else ""
        if st["kind"] == "decision":
            dw = 200 if len(st["text"]) <= 60 else 250
            hgt = 96 if len(st["text"]) <= 60 else 126
            vertex(cid, st["text"], ST["decision"].format(color=colours.get(role, NO)) + tag, x + (w - dw) / 2, y, dw, hgt)
        elif st["kind"] == "ref":
            hgt = 44 + 14 * max(0, _lines(st["text"], 34) - 2)
            vertex(cid, st["text"], ST["ref"], x, y, w, hgt)
        else:
            hgt = 46 + 14 * max(0, _lines(st["text"], 36) - 2)
            vertex(cid, st["text"], ST["activity"].format(color=colours.get(role, GREY), sw="2" if role else "1.5") + tag, x, y, w, hgt)
        for t in st["notes"]:
            n_note[0] += 1
            nh = 34 + 12 * max(0, _lines(t, 42) - 2)
            ny = max(y, notes_bottom[0] + 10)
            nid = vertex(f"nt{n_note[0]}", t, ST["note"], NOTE_X, ny, 230, nh)
            edge(cid, nid, style=ST["note_edge"])
            notes_bottom[0] = ny + nh
        return hgt

    y = 100
    vertex("mea_start", start_label, ST["start"], MAIN_X + (MAIN_W - 130) / 2, y, 130, 38)
    prev, prev_label, prev_colour = "mea_start", "", GREY
    y += 38 + 40
    branch_bottom = 0
    to_end = []                                              # (source id, label, colour) connected to End at the very end
    for i, st in enumerate(steps, 1):
        cid = f"s{i}"
        if st["kind"] == "decision" and st["branch"]:
            y = max(y, branch_bottom + 30)
        hgt = shape(st, cid, MAIN_X, MAIN_W, y)
        edge(prev, cid, prev_label, prev_colour, "exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;")
        prev, prev_label, prev_colour = cid, "", GREY
        if st["kind"] == "decision":
            br = st["branch"]
            if br:
                side, main = br["label"], ("Yes" if br["label"] == "No" else "No")
                side_col = NO if side == "No" else YES
                prev_label, prev_colour = main, (YES if main == "Yes" else NO)
                by, bprev, blabel = y + hgt / 2 - 23, cid, side
                for k, bs in enumerate(br["steps"], 1):
                    bid = f"{cid}b{k}"
                    bh = shape(bs, bid, BR_X, BR_W, by)
                    edge(bprev, bid, blabel, side_col if blabel else GREY,
                         "exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;" if bprev == cid else "exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;")
                    bprev, blabel = bid, ""
                    by += bh + 34
                    branch_bottom = by - 34
                if br["to_end"]:                             # (source, label, colour, from the decision itself, y of the source's middle)
                    to_end.append((bprev, blabel, side_col if blabel else GREY, bprev == cid, (y + hgt / 2) if bprev == cid else (by - 34 - bh / 2)))
            else:
                prev_label, prev_colour = "Yes", YES         # the other answer is left open on purpose (flow check reports it)
        y += hgt + 40
    y = max(y, branch_bottom + 30)
    vertex("mea_end", end_label, ST["end"], MAIN_X + (MAIN_W - 130) / 2, y, 130, 38)
    edge(prev, "mea_end", prev_label, prev_colour, "exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;")
    for k, (src, label, colour, from_decision, mid_y) in enumerate(to_end):
        # run down a free corridor: between the columns when it leaves the decision, right of the branch column otherwise
        cx = (MAIN_X + MAIN_W + 30 + 6 * (k % 4)) if from_decision else (BR_X + BR_W + 20 + 6 * (k % 5))
        edge(src, "mea_end", label, colour, "exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=1;entryY=0.5;entryDx=0;entryDy=0;", points=[(cx, mid_y), (cx, y + 19)])
    canvas.finish(root, cells, title, pid, dept, legend, used_roles, dict(meaBuilt="steps", **(meta or {})))
    return etree.tostring(root, encoding="unicode"), warnings


def steps_from_activities(activities):
    """Activity table of a process -> text for the builder (used to redraw a picture as a standard flow)."""
    out = []
    for a in activities or []:
        t = _norm(a.get("activity"))
        if not t:
            continue
        role = _norm(a.get("role")).split(" / ")[0]
        if t.startswith("Decision:"):
            t = _norm(t[9:])
            t = t if t.endswith("?") else t + "?"
        elif t.startswith("Linked process:"):
            out.append("Ref: " + _norm(t[15:]))
            continue
        out.append((role + ": " if role else "") + t)
    return "\n".join(out)


def template_steps(key):
    from . import drawio
    name, steps = drawio.TEMPLATES.get(key, drawio.TEMPLATES["blank"])
    lines = [lab for lab, shp in (s.split("|") for s in steps) if shp != "ellipse"]
    return "\n".join(lines) or "First activity"


# ---------------------------------------------------------------------------------------------- shape library
def _compress(xml):
    """draw.io library/diagram compression: encodeURIComponent -> raw deflate -> base64."""
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    return base64.b64encode(co.compress(quote(xml, safe="~()*!.'").encode("utf-8")) + co.flush()).decode("ascii")


def _lib_vertex(label, style, w, h):
    return (f'<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/><mxCell id="2" value="{escape(escape(label, quote=False))}" style="{escape(style)}" '
            f'vertex="1" parent="1"><mxGeometry width="{w}" height="{h}" as="geometry"/></mxCell></root></mxGraphModel>')


def _lib_edge(label, colour):
    return (f'<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/><mxCell id="2" value="{label}" style="{escape(ST["edge"].format(color=colour))}" '
            f'edge="1" parent="1"><mxGeometry width="50" height="50" relative="1" as="geometry"><mxPoint y="0" as="sourcePoint"/><mxPoint x="0" y="70" as="targetPoint"/>'
            f'</mxGeometry></mxCell></root></mxGraphModel>')


def library_entries(legend):
    """Flow Studio shape library: the standard shapes plus one activity per role of the master legend (tagged)."""
    items = [("Start", _lib_vertex("Start", ST["start"], 130, 38), 130, 38),
             ("End", _lib_vertex("End", ST["end"], 130, 38), 130, 38),
             ("Activity (no role yet)", _lib_vertex("Activity", ST["activity"].format(color=GREY, sw="1.5"), 240, 46), 240, 46),
             ("Decision", _lib_vertex("Decision?", ST["decision"].format(color=NO), 200, 96), 200, 96),
             ("Linked process (Ref ID)", _lib_vertex("Ref: XX-M-XX-01", ST["ref"], 240, 44), 240, 44),
             ("Note / checklist", _lib_vertex("Note", ST["note"], 230, 46), 230, 46),
             ("Connector – Yes", _lib_edge("Yes", YES), 50, 70), ("Connector – No", _lib_edge("No", NO), 50, 70), ("Connector", _lib_edge("", GREY), 50, 70)]
    for name, colour in dict.fromkeys(role_index(legend).values()):
        items.append((f"Activity – {name}", _lib_vertex(name, ST["activity"].format(color=colour, sw="2") + f"meaRole={name};", 240, 46), 240, 46))
    return [dict(xml=_compress(x), w=w, h=h, aspect="fixed", title=t) for t, x, w, h in items]


def library_xml(legend):
    """The same library as a file for draw.io Desktop / diagrams.net (File > Open Library)."""
    return "<mxlibrary title=\"dormakaba MEA\">" + escape(json.dumps(library_entries(legend)), quote=False) + "</mxlibrary>"
