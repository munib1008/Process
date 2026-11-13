"""BPMN 2.0 export of a flow: the open exchange format that process platforms and modelling tools read.

What is written
  start / end shapes        -> startEvent / endEvent
  activities                -> task (the role as performer and in the documentation)
  decisions                 -> exclusiveGateway, connector labels (Yes / No) as names of the sequence flows
  linked processes          -> callActivity (the linked ID stays in the name)
  notes and loose text      -> textAnnotation, with an association to the step a note is attached to
  positions                 -> BPMN diagram interchange, so the flow opens with the same layout

What BPMN cannot carry over: the dormakaba styling, the master legend, the frame and export areas. Roles are written as
performers, not as lanes, because the flows mark roles by outline colour and not by position."""
import re

from lxml import etree

from . import __version__, flowread

NS = dict(bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL", bpmndi="http://www.omg.org/spec/BPMN/20100524/DI",
          dc="http://www.omg.org/spec/DD/20100524/DC", di="http://www.omg.org/spec/DD/20100524/DI")
TAG = {"start": "startEvent", "end": "endEvent", "activity": "task", "decision": "exclusiveGateway", "ref": "callActivity",
       "fork": "parallelGateway", "join": "parallelGateway"}
FLOW = set(TAG)
SCALE = 1.5          # draw.io shapes are compact; BPMN tools write larger text, so the layout is enlarged evenly


def _q(prefix, name):
    return f"{{{NS[prefix]}}}{name}"


def _id(prefix, raw):
    return prefix + "_" + re.sub(r"[^A-Za-z0-9_.-]", "_", str(raw))


def _box(n):
    """Bounds in the BPMN picture: events and gateways have fixed sizes there, centred on the drawn shape."""
    x, y, w, h = (n[k] * SCALE for k in ("x", "y", "w", "h"))
    cx, cy = x + w / 2, y + h / 2
    if n["kind"] in ("start", "end"):
        return (cx - 18, cy - 18, 36, 36)
    if n["kind"] in ("decision", "fork", "join"):
        return (cx - 25, cy - 25, 50, 50)
    return (x, y, w, h)


def _dock(box, toward):
    """Point on the border of `box` facing the point `toward`."""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    dx, dy = toward[0] - cx, toward[1] - cy
    if abs(dx) * h >= abs(dy) * w:
        return (x + w if dx > 0 else x, cy)
    return (cx, y + h if dy > 0 else y)


def export(xml: str, process_id: str = "", name: str = "") -> bytes:
    g = flowread.read(xml)["graph"]
    nodes = {n["id"]: n for n in g["nodes"]}
    flow_ids = {i for i, n in nodes.items() if n["kind"] in FLOW}
    seq = [e for e in g["edges"] if e["source"] in flow_ids and e["target"] in flow_ids]
    assoc = [e for e in g["edges"] if (e["source"] in flow_ids) != (e["target"] in flow_ids) and "group" not in (nodes[e["source"]]["kind"], nodes[e["target"]]["kind"])]
    groups = [n for n in g["nodes"] if n["kind"] == "group"]
    inc, out = {}, {}
    for e in seq:
        out.setdefault(e["source"], []).append(e)
        inc.setdefault(e["target"], []).append(e)
    pid = re.sub(r"[^A-Za-z0-9_.-]", "_", process_id or "flow")
    root = etree.Element(_q("bpmn", "definitions"), nsmap=NS, id=f"Definitions_{pid}", targetNamespace="http://mea-process-hub/bpmn",
                         exporter="MEA Process Hub", exporterVersion=__version__)
    roles = list(dict.fromkeys(n["role"] for n in g["nodes"] if n["role"]))
    for r in roles:
        etree.SubElement(root, _q("bpmn", "resource"), id=_id("Role", r), name=r)
    if groups:                                               # swimlanes and frames keep their names as BPMN groups
        cat = etree.SubElement(root, _q("bpmn", "category"), id=f"Category_{pid}")
        for n in groups:
            etree.SubElement(cat, _q("bpmn", "categoryValue"), id=_id("cv", n["id"]), value=n["label"])
    proc = etree.SubElement(root, _q("bpmn", "process"), id=f"Process_{pid}", name=(f"{process_id} – {name}" if process_id and name else name or process_id or "Flow"), isExecutable="false")
    etree.SubElement(proc, _q("bpmn", "documentation")).text = "Exported from MEA Process Hub. Roles are given as performers of the tasks."
    for n in g["nodes"]:
        if n["kind"] not in FLOW:
            continue
        el = etree.SubElement(proc, _q("bpmn", TAG[n["kind"]]), id=_id("n", n["id"]), name=n["label"])
        if n["role"]:
            etree.SubElement(el, _q("bpmn", "documentation")).text = "Responsible role: " + n["role"]
        for e in inc.get(n["id"], []):
            etree.SubElement(el, _q("bpmn", "incoming")).text = _id("f", e["id"])
        for e in out.get(n["id"], []):
            etree.SubElement(el, _q("bpmn", "outgoing")).text = _id("f", e["id"])
        if n["role"] and n["kind"] == "activity":
            perf = etree.SubElement(el, _q("bpmn", "performer"), id=_id("p", n["id"]))
            etree.SubElement(perf, _q("bpmn", "resourceRef")).text = _id("Role", n["role"])
    for e in seq:
        attrs = dict(id=_id("f", e["id"]), sourceRef=_id("n", e["source"]), targetRef=_id("n", e["target"]))
        if e["label"]:
            attrs["name"] = e["label"]
        etree.SubElement(proc, _q("bpmn", "sequenceFlow"), **attrs)
    for n in groups:
        etree.SubElement(proc, _q("bpmn", "group"), id=_id("n", n["id"]), categoryValueRef=_id("cv", n["id"]))
    for n in g["nodes"]:
        if n["kind"] in FLOW or n["kind"] == "group":
            continue
        ta = etree.SubElement(proc, _q("bpmn", "textAnnotation"), id=_id("n", n["id"]))
        etree.SubElement(ta, _q("bpmn", "text")).text = n["label"]
    for e in assoc:
        etree.SubElement(proc, _q("bpmn", "association"), id=_id("a", e["id"]), sourceRef=_id("n", e["source"]), targetRef=_id("n", e["target"]))
    dia = etree.SubElement(root, _q("bpmndi", "BPMNDiagram"), id=f"Diagram_{pid}")
    plane = etree.SubElement(dia, _q("bpmndi", "BPMNPlane"), id=f"Plane_{pid}", bpmnElement=f"Process_{pid}")
    boxes = {i: _box(n) for i, n in nodes.items()}
    for n in g["nodes"]:
        attrs = dict(id=_id("s", n["id"]), bpmnElement=_id("n", n["id"]))
        if n["kind"] == "decision":
            attrs["isMarkerVisible"] = "true"
        sh = etree.SubElement(plane, _q("bpmndi", "BPMNShape"), **attrs)
        x, y, w, h = boxes[n["id"]]
        etree.SubElement(sh, _q("dc", "Bounds"), x=f"{x:.0f}", y=f"{y:.0f}", width=f"{w:.0f}", height=f"{h:.0f}")
    for e, prefix in [(e, "f") for e in seq] + [(e, "a") for e in assoc]:
        sb, tb = boxes[e["source"]], boxes[e["target"]]
        sc_, tc_ = (sb[0] + sb[2] / 2, sb[1] + sb[3] / 2), (tb[0] + tb[2] / 2, tb[1] + tb[3] / 2)
        mid = [(p[0] * SCALE, p[1] * SCALE) for p in e["points"]]
        if not mid and abs(sc_[0] - tc_[0]) > 2 and abs(sc_[1] - tc_[1]) > 2:       # one elbow instead of a diagonal
            mid = [(tc_[0], sc_[1])] if abs(tc_[0] - sc_[0]) * sb[3] >= abs(tc_[1] - sc_[1]) * sb[2] else [(sc_[0], tc_[1])]
        pts = [_dock(sb, mid[0] if mid else tc_)] + mid + [_dock(tb, mid[-1] if mid else sc_)]
        ed = etree.SubElement(plane, _q("bpmndi", "BPMNEdge"), id=_id("e", e["id"]), bpmnElement=_id(prefix, e["id"]))
        for px, py in pts:
            etree.SubElement(ed, _q("di", "waypoint"), x=f"{px:.0f}", y=f"{py:.0f}")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def summary(xml: str) -> dict:
    g = flowread.read(xml)["graph"]
    kinds = {}
    for n in g["nodes"]:
        kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1
    return dict(nodes=kinds, connectors=len(g["edges"]))
