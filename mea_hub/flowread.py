"""Read structured process content back out of a role-coloured flow (as produced by canvas.revamp or drawn in
Flow Studio on such a diagram): ordered activities, role per step (outline colour -> master legend inside the
diagram), decisions with their branches, linked processes, SAP codes and checklist notes."""
import re

from . import drawio

SAP_RE = re.compile(r"\b([A-Z]{2,4}\d{1,2}[A-Z]?|MIGO|MIRO)\b")
SAP_BLOCK = {"ZP00", "ZM00", "PG01"}
ID_RE = re.compile(r"\b[A-Z]{2,3}-[A-Z]{1,2}-[A-Z]{2,3}-\d{2}(?:\.\d+)?\b")
NEUTRAL = {"", "none", "default", "#000000", "#36393d", "#666666", "#ffffff", "#999999", "#484848", "#333333", "#003594", "#e4002b", "#009900", "#bfbfbf"}


def is_tagged(xml: str) -> bool:
    return "meaKind=" in xml


def _clean(t):
    return re.sub(r"\s+", " ", (t or "").replace("\xa0", " ")).strip()


def read(xml: str) -> dict:
    sc = drawio.scene(xml)
    B = sc["boxes"]
    for b in B.values():
        b["label"] = _clean(b["label"])
    legend, legend_colour = {}, {}                           # colour -> role and role -> colour, from the legend chips inside the diagram
    for b in B.values():
        if b["id"].startswith("mea_lg_c") and b["style"].get("strokeColor"):
            legend.setdefault(b["style"]["strokeColor"].lower(), b["label"])
            legend_colour.setdefault(b["label"], b["style"]["strokeColor"].lower())

    def kind(b):
        st = b["style"]
        k = st.get("meaKind")
        if st.get("meaExport"):                              # export area of the document picture: not part of the process
            return "export"
        if k:
            return k
        first = st["_first"]
        if first == "swimlane" or st.get("swimlane") is not None:
            return "container"
        if st.get("group") is not None or first == "group" or st.get("shape") in ("table", "tableRow", "partialRectangle", "image"):
            return "other"
        if first == "text":
            return "ref" if ID_RE.search(b["label"]) else "text"
        if first.startswith("rhombus") or st.get("shape") == "rhombus":
            return "decision"
        if st.get("shape") in ("note", "note2", "card", "document", "dataStorage") or (st.get("fillColor") or "").lower() == "#ffffe0":
            return "note"
        if first.startswith("ellipse") or (st.get("rounded") == "1" and drawio._num(st.get("arcSize")) >= 40):
            return "terminator"
        if ID_RE.search(b["label"]) and st.get("shape") == "process":
            return "ref"
        return "activity"

    def role(b):
        st = b["style"]
        c = (st.get("strokeColor") or "").lower()
        by_colour = legend.get(c, "") if c not in NEUTRAL else ""
        tag = st.get("meaRole") or ""
        if tag:                                              # the outline was recoloured in the editor: the legend colour wins over the old tag
            return by_colour if by_colour and by_colour != tag and legend_colour.get(tag, c) != c else tag
        return by_colour
    K = {i: kind(b) for i, b in B.items()}
    skip = {i for i, k in K.items() if k in ("legend", "frame", "export")}
    changed = True
    while changed:                                           # everything inside the legend group is legend
        changed = False
        for i, b in B.items():
            if i not in skip and b["parent"] in skip and K.get(b["parent"]) == "legend":
                skip.add(i)
                changed = True
    containers = {i for i, k in K.items() if k == "container" and i not in skip}
    child_of = {i: b["parent"] for i, b in B.items() if b["parent"] in containers}

    def top(i):
        return child_of.get(i, i)
    steps = [B[i] for i, k in K.items() if i not in skip and i not in child_of and k in ("activity", "decision", "ref", "container") and (B[i]["label"] or i in containers)]
    step_ids = {b["id"] for b in steps}
    notes = {i for i, k in K.items() if k == "note" and i not in skip}
    out_e, in_n, note_of = {}, {}, {}
    for e in sc["edges"]:
        a, c = top(e["source"]) if e["source"] else None, top(e["target"]) if e["target"] else None
        if a is None or c is None or a == c:
            continue
        if c in notes and a in step_ids:
            note_of.setdefault(a, []).append(B[c]["label"])
            continue
        if a in notes and c in step_ids:
            note_of.setdefault(c, []).append(B[a]["label"])
            continue
        if a in B and c in B:
            out_e.setdefault(a, []).append((c, _clean(e["label"])))
            in_n[c] = in_n.get(c, 0) + 1
    starts = [i for i, k in K.items() if k in ("start", "terminator") and i not in skip and in_n.get(i, 0) == 0 and out_e.get(i)]
    starts = starts or [b["id"] for b in sorted(steps, key=lambda b: (b["y"], b["x"])) if in_n.get(b["id"], 0) == 0]
    order, seen, queue = [], set(), list(starts)
    while queue:
        cur = queue.pop(0)
        if cur in seen:
            continue
        seen.add(cur)
        order.append(cur)
        queue += [c for c, _ in out_e.get(cur, [])]
    rank = {i: n for n, i in enumerate(order)}
    steps.sort(key=lambda b: (rank.get(b["id"], 10 ** 6), b["y"], b["x"]))
    activities, sap, roles, node_meta, note_lines = [], {}, [], {}, []
    for n, b in enumerate(steps, 1):
        k = K[b["id"]]
        label = b["label"]
        r = role(b)
        if b["id"] in containers:
            kids = [B[c] for c, p in child_of.items() if p == b["id"] and B[c]["label"] and K[c] not in ("note", "text")]
            kids.sort(key=lambda x: (x["y"], x["x"]))
            label = (label + ": " if label else "") + "; ".join(x["label"] for x in kids)
            kr = [role(x) for x in kids if role(x)]
            r = r or " / ".join(dict.fromkeys(kr))
        ref = ID_RE.search(label)
        if k == "decision":
            label = "Decision: " + label
        elif k == "ref":
            label = "Linked process: " + label
        nxt = []

        def target(c, depth=0):                              # split / join bars are passed through: what follows them is the next step
            tk = K.get(c)
            if tk in ("fork", "join") and depth < 4:
                outs = [t for t in (target(c2, depth + 1) for c2, _ in out_e.get(c, [])) if t]
                return ("in parallel: " if tk == "fork" and len(outs) > 1 else "") + " + ".join(outs) if outs else "next step"
            return "End" if tk in ("end", "terminator") or (tk == "start" and not out_e.get(c)) else (B[c]["label"] or "next step")[:70]
        for c, lb in out_e.get(b["id"], []):
            nxt.append((f"{lb}: " if lb else "") + target(c))
        codes = [c for c in dict.fromkeys(SAP_RE.findall(label)) if c not in SAP_BLOCK and not ID_RE.search(c)]
        codes = [c for c in codes if not any(c in m for m in ID_RE.findall(label))]
        activities.append(dict(no=str(n), activity=label, role=r, sap=" / ".join(codes), output=("→ " + "; ".join(nxt)) if nxt else ""))
        for c in codes:
            sap.setdefault(c, label[:160])
        for rr in [x.strip() for x in r.split(" / ") if x.strip()]:
            if rr not in roles:
                roles.append(rr)
        meta = {}
        if r:
            meta["role"] = r
        if codes:
            meta["sap"] = " / ".join(codes)
        if ref:
            meta["related"] = ref.group(0)
        if meta:
            node_meta[b["id"]] = meta
        for t in note_of.get(b["id"], []):
            note_lines.append((n, t))
    loose = [B[i]["label"] for i in sorted(notes, key=lambda i: (B[i]["y"], B[i]["x"])) if B[i]["label"] and not any(B[i]["label"] == t for _, t in note_lines)]
    for i, k in K.items():                                   # "Responsible ■ A ■ B" text blocks
        if k == "text" and i not in skip and B[i]["label"].lower().startswith("responsible"):
            for part in re.split(r"[■•]|\s{2,}", B[i]["label"])[1:]:
                part = part.strip(" :")
                if part and part not in roles and len(part) < 60:
                    roles.append(part)
    from html import escape
    notes_html = ""
    if note_lines or loose:
        notes_html = "<ul>" + "".join(f"<li><b>Step {n}:</b> {escape(t)}</li>" for n, t in note_lines) + "".join(f"<li>{escape(t)}</li>" for t in loose) + "</ul>"
    acts_only = [a for a in activities if not a["activity"].startswith(("Decision:", "Linked process:"))]
    summary = ""
    if activities:
        summary = (f"Starts with “{activities[0]['activity'][:90]}” and ends with “{activities[-1]['activity'][:90]}”. "
                   f"{len(acts_only)} activities, {sum(1 for a in activities if a['activity'].startswith('Decision:'))} decision points"
                   + (f", {sum(1 for a in activities if a['activity'].startswith('Linked process:'))} linked processes" if any(a['activity'].startswith('Linked process:') for a in activities) else "")
                   + (f". Roles involved: {', '.join(roles)}." if roles else "."))
    unreached = sum(1 for b in steps if b["id"] not in seen)
    # ---- flow check: structural points a reviewer would raise (nothing is corrected automatically)
    def names(bs):
        return "; ".join("“" + (b["label"][:60] or "unnamed shape") + "”" for b in bs[:4]) + (f" and {len(bs) - 4} more" if len(bs) > 4 else "")
    live = [i for i in K if i not in skip]
    checks = []
    if not any(K[i] in ("start", "terminator") and in_n.get(i, 0) == 0 and out_e.get(i) for i in live):
        checks.append(dict(code="no_start", text="No Start shape with an outgoing connector."))
    if not any(K[i] in ("end", "terminator") and in_n.get(i, 0) > 0 and not out_e.get(i) for i in live):
        checks.append(dict(code="no_end", text="No End shape is reached by a connector."))
    if unreached:
        checks.append(dict(code="unreached", text=f"{unreached} step(s) cannot be reached from Start: " + names([b for b in steps if b["id"] not in seen]) + "."))
    dead = [b for b in steps if not out_e.get(b["id"]) and b["id"] in seen]
    if dead:
        checks.append(dict(code="dead_end", text=f"{len(dead)} step(s) have no next step (connect them to the next step or to End): " + names(dead) + "."))
    one_way = [b for b in steps if K[b["id"]] == "decision" and len(out_e.get(b["id"], [])) == 1]
    if one_way:
        checks.append(dict(code="one_branch", text=f"{len(one_way)} decision(s) have only one outgoing branch: " + names(one_way) + "."))
    unlabelled = [b for b in steps if K[b["id"]] == "decision" and len(out_e.get(b["id"], [])) > 1 and any(not lb for _, lb in out_e[b["id"]])]
    if unlabelled:
        checks.append(dict(code="unlabelled", text=f"{len(unlabelled)} decision(s) have a branch without a label (Yes / No): " + names(unlabelled) + "."))
    no_role = [b for b in steps if K[b["id"]] == "activity" and not role(b)]
    if no_role:
        checks.append(dict(code="no_role", text=f"{len(no_role)} activity step(s) have no responsible role (outline colour from the master legend): " + names(no_role) + "."))
    return dict(activities=activities, sap=[dict(transaction=k, purpose=v) for k, v in sap.items()], responsible=roles, notes_html=notes_html,
                node_meta=node_meta, summary=summary, shapes=len(steps), has_start=bool(starts), unreached=unreached, checks=checks,
                graph=_graph(B, K, skip, containers, child_of, top, role, sc["edges"]))
FLOW_NOTES_TITLE = "Checklists and notes from the flowchart"



def _graph(B, K, skip, containers, child_of, top, role, edges):
    """The flow as typed nodes and connectors with their positions (used for exchange formats such as BPMN).
    A container whose inner shapes carry connectors (a swimlane) is a "group" and its shapes are steps with the lane as
    role; a container with plain rows inside (e.g. "Parallel Tasks") stays one step."""
    wired = {i for e in edges for i in (e["source"], e["target"]) if i in child_of}
    lanes = {child_of[i] for i in wired}
    changed = True
    while changed:                                           # a pool that holds lanes is a group as well
        changed = False
        for i in list(lanes):
            if i in child_of and child_of[i] not in lanes:
                lanes.add(child_of[i])
                changed = True

    def own(i):                                              # the node a shape belongs to: itself inside a lane, else its closed container
        return i if child_of.get(i) in lanes or i not in child_of else child_of[i]
    nodes, has_in, has_out = {}, set(), set()
    for i, b in B.items():
        if i in skip or K[i] in ("other", "lane") or own(i) != i:
            continue
        label = b["label"]
        if i in lanes:
            if label:
                nodes[i] = dict(id=i, kind="group", label=label, role="", x=b["x"], y=b["y"], w=b["w"], h=b["h"])
            continue
        if i in containers:
            kids = sorted((B[c] for c, p in child_of.items() if p == i and B[c]["label"] and K[c] not in ("note", "text")), key=lambda x: (x["y"], x["x"]))
            label = (label + ": " if label and kids else label) + "; ".join(x["label"] for x in kids)
        if not label and K[i] not in ("fork", "join"):
            continue
        r = role(b) if K[i] in ("activity", "decision", "container") else ""
        if not r and child_of.get(i) in lanes and K[i] in ("activity", "decision"):
            r = B[child_of[i]]["label"]                     # the swimlane names the role
        nodes[i] = dict(id=i, kind=K[i], label=label, role=r, x=b["x"], y=b["y"], w=b["w"], h=b["h"])
    links = []
    for e in edges:
        a, c = own(e["source"]) if e["source"] else None, own(e["target"]) if e["target"] else None
        if a in nodes and c in nodes and a != c:
            links.append(dict(id=e["id"], source=a, target=c, label=_clean(e["label"]), points=list(e["points"])))
            if nodes[a]["kind"] != "note" and nodes[c]["kind"] != "note":
                has_out.add(a)
                has_in.add(c)
    for n in nodes.values():
        if n["kind"] == "terminator":                        # an untagged terminator is a start or an end by its connectors
            n["kind"] = "start" if n["id"] not in has_in else "end"
        elif n["kind"] == "container":                       # connected: one step; unconnected: a frame drawn around other steps
            n["kind"] = "activity" if n["id"] in has_in or n["id"] in has_out else "group"
    return dict(nodes=list(nodes.values()), edges=links)


def apply_to_content(content: dict, fr: dict) -> dict:
    """Merge a flow reading into a content dict (used at import and whenever a synced diagram is saved)."""
    c = dict(content)
    c["activities"] = fr["activities"]
    if fr["sap"]:
        c["sap"] = fr["sap"]
    if fr["responsible"]:
        c["responsible"] = fr["responsible"]
    secs = [s for s in c.get("sections", []) if s.get("title") != FLOW_NOTES_TITLE]
    if fr["notes_html"]:
        secs.append(dict(title=FLOW_NOTES_TITLE, html=fr["notes_html"]))
    c["sections"] = secs
    if fr["summary"] and (not c.get("scope") or c.get("scope", "").startswith("Starts with “")):
        c["scope"] = fr["summary"]
    c["flow_sync"] = True
    return c
