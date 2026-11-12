"""Drafts derived from the process flows: a RACI per process and a work instruction per SAP task.

Rule of this module: nothing is assumed. Every entry comes from the flow (step, role, order of the steps, wording of
the step) or from the process record (owner). What the sources do not say - who is accountable, which SAP screens and
entries are used - is left empty or written as an open point, and the result is marked as a draft until a person edits it.

RACI (one row per step of the activity table)
  R  the role of the step (outline colour / lane of the flow)
  A  the process owner recorded for the process; a role the step text names as approver ("approval from X", "approved by X")
  C  a role the step text names for coordination ("coordinate with X", "consult X", "clarification from X", "support from X")
  I  the role of the next step when it differs from R (it receives the result); a role the step text names as recipient
     ("notify X", "inform X", "share with X", "send to X", "handover to X")

SAP work instruction (kind work_instruction, status draft, one per distinct SAP step text)
  known   the step, its role, the step before and after it, the transaction code if the step names one
  open    transaction (if not named), screen sequence, entries, organisational data, checks - listed for the owner"""
import json
import re

from . import db, service as svc
from .db import one, q

SYSTEM = "system"
RACI_NOTE = ("Draft derived from the flow: R = role of the step; I = role of the next step and roles the step text names as recipients; "
             "A and C only where the process owner is recorded or the step text names an approver / a party to coordinate with. Confirm or correct.")
SAP_WORD = re.compile(r"\bSAP\b")
SAP_CODE = re.compile(r"\b([A-Z]{2,4}\d{1,2}[A-Z]?|MIGO|MIRO)\b")
SAP_BLOCK = {"ZP00", "ZM00", "PG01"}
SAP_DOCS = re.compile(r"\b(PGI|GRN?|goods receipt|goods issue|sales order|purchase order|purchase requisition|PR|PO|SO|delivery note|invoice|MRP|info record|"
                      r"material master|production order|stock transfer|STO|picking list|inventory document|billing)\b", re.I)
# standard SAP names of the transactions that the supplied flows name (public SAP standard, no company configuration)
STANDARD_NAMES = {"MM01": "Create Material", "MM02": "Change Material", "VK11": "Create Condition Records", "VK12": "Change Condition Records",
                  "ME11": "Create Purchasing Info Record", "ME12": "Change Purchasing Info Record", "LS24": "Display Quants for Material",
                  "MIGO": "Goods Movement", "MIRO": "Enter Incoming Invoice", "VA01": "Create Sales Order", "VA02": "Change Sales Order", "VL01N": "Create Outbound Delivery",
                  "VL02N": "Change Outbound Delivery", "ME21N": "Create Purchase Order", "ME51N": "Create Purchase Requisition", "VF01": "Create Billing Document",
                  "MI01": "Create Physical Inventory Document", "MI04": "Enter Inventory Count", "MI07": "Post Inventory Difference", "MD04": "Stock/Requirements List"}
OPEN = "[to be completed by the process owner]"
APPROVE = r"(?:approval (?:from|of|by)|approved by|sign[- ]?off (?:from|by)|authori[sz]ation (?:from|by))"
CONSULT = r"(?:coordinat\w* with|consult\w*(?: with)?|clarification from|together with|support from)"
W = r"(?: [\w&/()-]+)"
INFORM = r"(?:notif\w*|inform\w*|share\w*" + W + r"{0,6}? with|send\w*" + W + r"{0,5}? to|hand ?over" + W + r"{0,3}? to|report\w*" + W + r"{0,3}? to|escalat\w* to)"


def _roles():
    legend = svc.master_legend() or {}
    names = {r["role"].strip() for r in legend.get("roles", []) if r.get("role")}
    return sorted(names, key=len, reverse=True)


TITLE_WORDS = {"head", "manager", "supervisor", "lead", "leader", "team", "controller", "director", "coordinator", "specialist", "analyst", "officer", "department", "dept"}
PHRASE = r"((?:[A-Z][A-Za-z&/.-]*)(?:\s+(?:[A-Z][A-Za-z&/.-]*|of)){0,3})"


def _named(text, trigger, roles, skip):
    """Who the text names right after a trigger phrase: a role of the master legend when the wording is exactly that role,
    otherwise the capitalised name as written ("Logistics Head" stays "Logistics Head", it is not shortened to "Logistics")."""
    out = []

    def add(x):
        x = x.strip(" .,;:-")
        if x and x not in skip and x not in out and len(x) > 1:
            out.append(x)
    for m in re.finditer(trigger + r"\s+(?:the\s+)?(.{0,70})", text, re.I):
        tail = m.group(1)
        while tail:
            hit = None
            for r in roles:
                mm = re.match(re.escape(r) + r"\b(?:\s+(\w+))?", tail, re.I)
                if mm and (mm.group(1) or "").lower() not in TITLE_WORDS and not (mm.group(1) or "")[:1].isupper():
                    hit = (r, mm.end() if not mm.group(1) else mm.start(1))
                    break
            if not hit:
                mm = re.match(PHRASE, tail)                   # a name as written, accepted only when it ends in a job-title word
                if not mm or mm.group(1).split()[-1].lower() not in TITLE_WORDS:
                    break
                hit = (mm.group(1), mm.end())
            add(hit[0])
            nxt = re.match(r"\s*(?:,|and|&)\s+(?:the\s+)?", tail[hit[1]:])
            tail = tail[hit[1] + nxt.end():] if nxt else ""
    return out


def raci_rows(activities, owner="", roles=None):
    roles = roles if roles is not None else _roles()
    role_of = {}
    for a in activities:
        role_of.setdefault(re.sub(r"^Decision:\s*", "", a["activity"]).strip().lower(), a.get("role", ""))
    rows = []
    for a in activities:
        if a["activity"].startswith("Linked process:"):      # a reference to another process, not a step of this one
            continue
        text, r = a["activity"], (a.get("role") or "").strip()
        nxt = []
        for part in re.split(r";", (a.get("output") or "").lstrip("→ ")):
            target = re.sub(r"^[^:]{1,25}:\s*(?=\S)", "", part.strip()) if ":" in part[:28] else part.strip()
            for cand in (part.strip(), target):
                role = role_of.get(re.sub(r"^Decision:\s*", "", cand).strip().lower())
                if role and role != r and role not in nxt:
                    nxt.append(role)
                    break
        approvers = _named(text, APPROVE, roles, {r})
        consulted = _named(text, CONSULT, roles, {r, *approvers})
        informed = [x for x in _named(text, INFORM, roles, {r, *approvers, *consulted}) + nxt if x not in approvers and x not in consulted]
        informed = list(dict.fromkeys(informed))
        rows.append(dict(activity=text, R=r, A=", ".join(approvers) if approvers else (owner or "").strip(), C=", ".join(consulted), I=", ".join(informed)))
    return rows


def generate_raci(user, pid_text, force=False):
    """Draft RACI for one process (only when it has steps and no RACI yet, unless forced). -> number of rows written."""
    proc = svc.get_process(pid_text)
    svc.need(user, "edit", proc) if user != SYSTEM else None
    with db.tx():
        v = svc.open_version(proc["id"]) or svc.ensure_draft(proc, user if user != SYSTEM else SYSTEM)
        content = v["content"]
        if not content.get("activities") or (content.get("raci") and not force):
            return 0
        content = dict(content, raci=raci_rows(content["activities"], proc.get("owner") or ""), raci_draft=True)
        db.db().execute("UPDATE process_versions SET content=?, updated_at=? WHERE id=?", (json.dumps(content), svc.now(), v["id"]))
        svc.audit(user, "raci_drafted", "process", proc["process_id"], f"{len(content['raci'])} rows derived from the flow")
        svc.reindex(proc["id"])
        return len(content["raci"])


def raci_candidates():
    """(processes a draft RACI can be derived for, processes without RACI that have no steps to derive it from)."""
    can, no_steps = [], []
    for p in q("SELECT id,process_id,kind FROM processes ORDER BY id"):
        if p["kind"] in ("reference", "form", "work_instruction"):
            continue
        v = svc.latest_version(p["id"])
        if not v or v["content"].get("raci"):
            continue
        if not any(not a["activity"].startswith("Linked process:") for a in v["content"].get("activities", [])):
            no_steps.append(p["process_id"])                 # no flow, or an overview that only links to other processes
        elif v["status"] not in ("published", "superseded"):
            can.append(p["process_id"])
    return can, no_steps


def generate_all_raci(user):
    """Draft RACI for every process that has steps, no RACI and an editable (not published) latest version."""
    if user != SYSTEM:
        svc.need(user, "generate_drafts")
    done, rows, skipped = 0, 0, []
    with db.tx():
        for p in q("SELECT id,process_id,kind FROM processes ORDER BY id"):
            if p["kind"] in ("reference", "form", "work_instruction"):
                continue
            v = svc.latest_version(p["id"])
            if not v or not v["content"].get("activities") or v["content"].get("raci"):
                continue
            if v["status"] in ("published", "superseded"):
                skipped.append(p["process_id"])              # an approved version is never changed in bulk
                continue
            n = generate_raci(SYSTEM, p["process_id"])
            done, rows = done + (1 if n else 0), rows + n
        if done and user != SYSTEM:
            svc.audit(user, "raci_drafted_bulk", "process", "*", f"{done} processes, {rows} rows")
    return dict(processes=done, rows=rows, skipped_published=skipped)


# ---------------------------------------------------------------------------------------------- SAP work instructions
def is_sap_step(a, extended=False):
    text = a["activity"]
    if a.get("sap") or SAP_WORD.search(text) or any(c not in SAP_BLOCK for c in SAP_CODE.findall(text)):
        return True
    return bool(extended and SAP_DOCS.search(text))


def sap_steps(extended=False):
    """Distinct SAP step texts with every place they occur: [dict(text, codes, uses=[dict(process_id, name, dept, no, role, before, after)])]."""
    found = {}
    for p in q("SELECT p.id,p.process_id,p.name,p.kind,p.category,d.code dept FROM processes p LEFT JOIN departments d ON d.id=p.department_id ORDER BY d.sort,p.sort_order,p.id"):
        if p["kind"] in ("reference", "form", "work_instruction", "department"):
            continue                                         # department overviews repeat the SOP steps; canvas remnants are not processes
        acts = (svc.latest_version(p["id"]) or {"content": {}})["content"].get("activities", [])
        for i, a in enumerate(acts):
            if a["activity"].startswith(("Linked process:", "Decision:")) or not is_sap_step(a, extended):
                continue
            me = a["activity"].strip().lower()               # the step(s) whose connector leads here - not simply the row above
            before = "; ".join(b["activity"] for b in acts if b is not a and me and me in (b.get("output") or "").lower())[:300]
            text = re.sub(r"\s+", " ", a["activity"]).strip(" .-")
            codes = [c for c in dict.fromkeys(SAP_CODE.findall((a.get("sap") or "") + " " + text)) if c not in SAP_BLOCK]
            item = found.setdefault(text.lower(), dict(text=text, codes=codes, uses=[]))
            item["uses"].append(dict(process_id=p["process_id"], name=p["name"], dept=p["dept"] or "E2E", no=a.get("no", str(i + 1)), role=a.get("role", ""),
                                     before=before, after=(a.get("output") or "").lstrip("→ ").strip()))
    return list(found.values())


def _wi_content(item):
    u0, codes = item["uses"][0], item["codes"]
    roles = list(dict.fromkeys(u["role"] for u in item["uses"] if u["role"]))
    used = "; ".join(f"{u['process_id']} step {u['no']} ({u['name']})" for u in item["uses"])
    tx_text = " / ".join(f"{c} – {STANDARD_NAMES[c]}" if c in STANDARD_NAMES else c for c in codes)
    acts = [dict(no="1", activity=("Before you start: the previous step is complete – “" + u0["before"] + "”") if u0["before"] else "Before you start: " + OPEN,
                 role=u0["role"], sap="", output=""),
            dict(no="2", activity=("Open SAP transaction " + tx_text) if codes else "Open the SAP transaction for this task – the source documents do not name it " + OPEN,
                 role=u0["role"], sap=" / ".join(codes), output=""),
            dict(no="3", activity="Carry out the task: " + item["text"] + ". Entries, organisational data and mandatory fields: " + OPEN, role=u0["role"], sap=" / ".join(codes), output=""),
            dict(no="4", activity="Check and save: messages to expect, document number created, printout or output: " + OPEN, role=u0["role"], sap="", output=""),
            dict(no="5", activity=("Hand over: " + u0["after"]) if u0["after"] else "Hand over: " + OPEN, role=u0["role"], sap="", output=u0["after"])]
    content = json.loads(json.dumps(svc.EMPTY))
    content.update(
        objective=f"Describes how the step “{item['text']}” is carried out in SAP.",
        scope="Used in: " + used + ".",
        trigger=("Previous step: " + u0["before"]) if u0["before"] else "",
        outputs=u0["after"],
        responsible=roles,
        activities=acts,
        sap=[dict(transaction=c, purpose=(STANDARD_NAMES[c] + " (standard SAP name)") if c in STANDARD_NAMES else "Purpose not stated in the source – to be confirmed") for c in codes],
        notes=("DRAFT – generated from the process flows. Taken from the sources: the step, its role, the step before and after it"
               + (", the transaction code written in the step" if codes else "") + ". Not in the sources and therefore left open: "
               + ("" if codes else "the transaction, ") + "screen sequence, entries, organisational data (company code, plant, sales organisation), authorisations and checks. "
               "Nothing was assumed about the SAP configuration."))
    return content


def generate_sap_instructions(user, extended=False):
    """One draft work instruction per distinct SAP step. Existing ones (same step text) are left untouched."""
    if user != SYSTEM:
        svc.need(user, "generate_drafts")
    uname = user if isinstance(user, str) else user["username"]
    created, existing = [], 0
    with db.tx():
        have = {r["gen_key"] for r in q("SELECT gen_key FROM processes WHERE gen_key LIKE 'SAPWI:%'")}
        for item in sap_steps(extended):
            key = "SAPWI:" + re.sub(r"[^a-z0-9]+", "-", item["text"].lower())[:150]
            if key in have:
                existing += 1
                continue
            u0 = item["uses"][0]
            n = 1
            while one("SELECT 1 FROM processes WHERE process_id=?", (f"{u0['process_id']}-WI-{n:02d}",)):
                n += 1
            pid = f"{u0['process_id']}-WI-{n:02d}"
            name = "SAP task – " + (item["text"] if len(item["text"]) <= 90 else item["text"][:87].rstrip() + "…")
            pr = svc.create_process_record(pid, None, name, u0["dept"], "work_instruction", _wi_content(item), "draft", "generated", uname, category="SAP work instruction (draft)")
            db.db().execute("UPDATE processes SET gen_key=? WHERE id=?", (key, pr["id"]))
            for u in item["uses"]:
                parent = one("SELECT id FROM processes WHERE process_id=?", (u["process_id"],))
                db.db().execute("INSERT OR IGNORE INTO relationships(from_id,to_id,rel_type,note,inferred) VALUES(?,?,?,?,1)",
                                (pr["id"], parent["id"], "supports", f"Work instruction for step {u['no']}"))
            svc.add_finding("gap", "low", None, pr["id"], f"Draft SAP work instruction to be completed ({pid})",
                            "Generated from the flow step “" + item["text"] + "”. " + ("The transaction is named in the step. " if item["codes"] else "The source does not name the transaction. ")
                            + "Screen sequence, entries, organisational data and checks are open and must be written by the process owner before review.")
            svc.reindex(pr["id"])
            created.append(pid)
        if created:
            svc.audit(user, "sap_instructions_drafted", "process", "*", f"{len(created)} draft work instructions" + (" (extended scope)" if extended else ""))
    return dict(created=created, existing=existing)
