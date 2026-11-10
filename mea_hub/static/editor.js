"use strict";
/* Process editor: structured fields, table editors, Word-style rich text sections, debounced autosave to a draft. */
const TABLES = {
  activities: {label: "Detailed activities", cols: [["no", "No", 50], ["activity", "Activity / decision", 300], ["role", "Role", 130], ["sap", "SAP / system", 110], ["output", "Output", 130]]},
  raci: {label: "RACI", cols: [["activity", "Activity", 300], ["R", "Responsible", 120], ["A", "Accountable", 120], ["C", "Consulted", 120], ["I", "Informed", 120]]},
  sap: {label: "SAP references", cols: [["transaction", "Transaction", 160], ["purpose", "Purpose", 400]]},
  kpis: {label: "KPIs", cols: [["name", "KPI", 240], ["definition", "Definition / calculation", 320], ["target", "Target", 120]]},
  escalation: {label: "Escalation & SLA", cols: [["stage", "Stage", 70], ["to", "Task / reminder to", 200], ["time", "Time period", 160], ["action", "Escalation", 200], ["sla", "Previous SLA", 140]]},
};
const TEXT_FIELDS = [["objective", "Objective"], ["scope", "Scope"], ["trigger", "Trigger"], ["inputs", "Inputs"], ["outputs", "Outputs"], ["risks", "Risks and preventive controls"], ["evidence", "Required records / audit evidence"], ["forms", "Related forms and templates"], ["notes", "Notes"]];

function rte(initialHtml, onchange) {
  const ed = h("div", {class: "rte rt", contenteditable: "true", role: "textbox", "aria-multiline": "true"});
  setHTML(ed, initialHtml);
  const cmd = (c, v) => { ed.focus(); document.execCommand(c, false, v || null); onchange(); };
  const btn = (label, title, fn) => h("button", {class: "btn sm", type: "button", title, onmousedown: (e) => e.preventDefault(), onclick: fn}, label);
  const bar = h("div", {class: "rte-bar"},
    btn("B", "Bold", () => cmd("bold")), btn("I", "Italic", () => cmd("italic")), btn("U", "Underline", () => cmd("underline")),
    btn("H3", "Heading", () => cmd("formatBlock", "h3")), btn("H4", "Sub-heading", () => cmd("formatBlock", "h4")), btn("¶", "Paragraph", () => cmd("formatBlock", "p")),
    btn("• List", "Bulleted list", () => cmd("insertUnorderedList")), btn("1. List", "Numbered list", () => cmd("insertOrderedList")),
    btn("Link", "Insert hyperlink", async () => { const u = await promptBox("Insert link", "URL (https://… or #/process/ID)"); if (u) cmd("createLink", u); }),
    btn("Table", "Insert 3×3 table", () => cmd("insertHTML", "<table><tr><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th></tr><tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr><tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr></table><p></p>")),
    btn("Callout", "Insert callout", () => cmd("insertHTML", "<div class=\"callout\"><b>Note:</b> </div><p></p>")),
    btn("Page break", "Insert page break (exports)", () => cmd("insertHTML", "<div class=\"pagebreak\">— page break —</div><p></p>")),
    btn("Clear", "Remove formatting", () => cmd("removeFormat")), btn("↶", "Undo", () => cmd("undo")), btn("↷", "Redo", () => cmd("redo")));
  ed.addEventListener("input", onchange);
  ed.addEventListener("paste", (e) => { e.preventDefault(); const t = (e.clipboardData || window.clipboardData).getData("text/plain"); document.execCommand("insertText", false, t); });
  return {el: h("div", null, bar, ed), get: () => ed.innerHTML};
}

function tableEditor(spec, rows, onchange) {
  const body = h("tbody");
  const addRow = (r) => {
    const tr = h("tr");
    spec.cols.forEach(([k, , w]) => tr.append(h("td", {style: "min-width:" + Math.min(w, 200) + "px"}, h("input", {type: "text", value: (r && r[k]) || "", "data-k": k, oninput: onchange, "aria-label": k}))));
    tr.append(h("td", {style: "width:34px"}, h("button", {class: "btn sm bad", type: "button", title: "Remove row", onclick: () => { tr.remove(); onchange(); }}, "✕")));
    body.append(tr);
  };
  (rows || []).forEach(addRow);
  const el = h("div", {style: "overflow:auto"}, h("table", {class: "edtable"}, h("thead", null, h("tr", null, spec.cols.map((c) => h("th", null, c[1])), h("th"))), body),
    h("button", {class: "btn sm", type: "button", style: "margin-top:6px", onclick: () => { addRow(); onchange(); }}, "+ Add row"));
  return {el, get: () => [...body.children].map((tr) => { const o = {}; tr.querySelectorAll("input").forEach((i) => o[i.dataset.k] = i.value); return o; })};
}

/* Builds the editable form. returns {el, collect(), setStatus} ; calls save(payload) debounced */
function buildEditor(detail, saveFn) {
  const p = detail.process, c = detail.version.content;
  let timer = null, dirty = false, baseUpdated = detail.version.updated_at;
  const status = h("span", {class: "muted"}, "No changes");
  const mark = () => { dirty = true; status.textContent = "Unsaved changes…"; clearTimeout(timer); timer = setTimeout(save, 2000); };
  const inputs = {};
  const field = (k, label, el) => { inputs[k] = el; return h("div", null, h("label", null, label), el); };
  const depts = S.tree.map((d) => h("option", {value: d.id, selected: d.id === p.department_id}, d.name));
  const meta = h("div", {class: "fields"},
    field("name", "Process name", h("input", {type: "text", value: p.name, oninput: mark})),
    field("department_id", "Department", h("select", {onchange: mark}, depts)),
    field("kind", "Process type", h("select", {onchange: mark}, S.cfg.kinds.map((k) => h("option", {value: k, selected: k === p.kind}, k.replace("_", " "))))),
    field("owner", "Process owner", h("input", {type: "text", value: p.owner, oninput: mark})),
    field("reviewer", "Reviewer", h("input", {type: "text", value: p.reviewer, oninput: mark})),
    field("countries", "Countries / region", h("input", {type: "text", value: p.countries, oninput: mark})),
    field("category", "Category", h("input", {type: "text", value: p.category, oninput: mark})),
    field("review_months", "Review frequency (months)", h("input", {type: "number", min: 1, max: 60, value: p.review_months || "", oninput: mark})));
  const texts = TEXT_FIELDS.map(([k, label]) => field("t_" + k, label, h("textarea", {value: c[k] || "", oninput: mark})));
  const resp = field("responsible", "Responsible departments / roles (one per line)", h("textarea", {value: (c.responsible || []).join("\n"), oninput: mark}));
  const tabs = {};
  const sync = h("input", {type: "checkbox", style: "width:auto", checked: !!c.flow_sync, onchange: mark});
  const tabEls = Object.entries(TABLES).map(([k, spec]) => { tabs[k] = tableEditor(spec, c[k], mark); return h("div", null, h("h3", null, spec.label),
    k === "activities" ? h("label", {style: "font-weight:normal;color:var(--ink);margin:0 0 6px"}, sync, " Keep activities, roles and SAP references linked to the flowchart (they are re-read from the diagram every time it is saved; manual changes to this table would then be replaced)") : null, tabs[k].el); });
  const secs = [];
  const secWrap = h("div");
  const addSection = (s) => {
    const title = h("input", {type: "text", value: s.title || "", oninput: mark, placeholder: "Section title"});
    const ed = rte(s.html || "", mark);
    const box = h("div", {class: "card"}, h("div", {class: "row"}, title, h("button", {class: "btn sm bad", type: "button", onclick: () => { box.remove(); secs.splice(secs.indexOf(entry), 1); mark(); }}, "Remove section")), ed.el);
    const entry = {title, ed};
    secs.push(entry); secWrap.append(box);
  };
  (c.sections || []).forEach(addSection);
  const summary = h("input", {type: "text", placeholder: "Change summary (required to submit for review)", value: detail.version.change_summary || "", oninput: mark});

  function collect() {
    const content = {flow_sync: sync.checked, responsible: inputs.responsible.value.split("\n").map((x) => x.trim()).filter(Boolean),
      sections: secs.map((s) => ({title: s.title.value, html: s.ed.get()}))};
    TEXT_FIELDS.forEach(([k]) => content[k] = inputs["t_" + k].value);
    Object.keys(TABLES).forEach((k) => content[k] = tabs[k].get());
    return {content, meta: {name: inputs.name.value, department_id: +inputs.department_id.value, kind: inputs.kind.value, owner: inputs.owner.value,
      reviewer: inputs.reviewer.value, countries: inputs.countries.value, category: inputs.category.value, review_months: inputs.review_months.value}, change_summary: summary.value};
  }
  async function save() {
    clearTimeout(timer);
    if (!dirty) return true;
    status.textContent = "Saving…";
    try {
      const body = collect(); body.base_updated_at = baseUpdated;
      const r = await saveFn(body);
      baseUpdated = r.updated_at; dirty = false; status.textContent = "Saved " + new Date().toLocaleTimeString();
      return true;
    } catch (e) { status.textContent = "Save failed: " + e.message; toast(e.message, true); return false; }
  }
  const el = h("div", null,
    h("div", {class: "banner info row spread"}, h("span", null, "Editing draft. Changes autosave; the published version stays unchanged until approved."), status),
    h("div", {class: "card"}, h("h3", null, "Process identification"), meta, h("label", null, "Process ID"), h("input", {type: "text", value: p.process_id, disabled: true})),
    h("div", {class: "card"}, h("h3", null, "Operational definition"), texts, resp),
    h("div", {class: "card"}, tabEls),
    h("div", {class: "card"}, h("h3", null, "Document content (rich text)"), secWrap, h("button", {class: "btn", type: "button", onclick: () => { addSection({title: "New section", html: "<p></p>"}); mark(); }}, "+ Add section")),
    h("div", {class: "card"}, h("label", null, "Change summary"), summary));
  window.onbeforeunload = () => dirty ? "You have unsaved changes." : undefined;
  return {el, save, isDirty: () => dirty, dispose: () => { clearTimeout(timer); window.onbeforeunload = null; }};
}
