"use strict";
let editorInst = null;
const NAV = [["#/dashboard", "Dashboard", "▦"], ["#/handbook", "Master Handbook", "☰"], ["#/library", "Process Library", "≣"], ["#/flow", "Flow Studio", "⬡"], ["#/departments", "Departments", "▤"],
  ["#/governance", "Governance", "⚖"], ["#/reports", "Reports", "◔"], ["#/import", "Import & Sources", "⇪"], ["#/export", "Export Center", "⇩"], ["#/admin", "Administration", "⚙"]];

async function boot() {
  S.cfg = await GET("/api/config");
  const me = await GET("/api/me");
  S.user = me.user; S.csrf = me.csrf || null;
  window.addEventListener("hashchange", route);
  render();
}
function render() {
  const app = clear($("#app"));
  if (!S.user) return app.append(loginView());
  if (S.user.must_change) return app.append(passwordView(true));
  GET("/api/tree").then((t) => { S.tree = t.departments; app.append(layout()); route(); }).catch((e) => toast(e.message, true));
}
function loginView() {
  const u = h("input", {type: "text", autocomplete: "username", autofocus: true}), p = h("input", {type: "password", autocomplete: "current-password", onkeydown: (e) => { if (e.key === "Enter") go(); }}), err = h("div", {class: "banner bad", style: "display:none"});
  const go = async () => { try { const r = await api("POST", "/api/login", {username: u.value, password: p.value}); S.user = r.user; S.csrf = r.csrf; location.hash = "#/dashboard"; render(); } catch (e) { err.style.display = ""; err.textContent = e.message; } };
  return h("div", {class: "login"}, h("div", {class: "loginbox"},
    h("div", {class: "panel"}, h("img", {src: "/brand/dormakaba_logo_white.png", alt: "dormakaba"}),
      h("div", null, h("div", {class: "title"}, "MEA Process Hub"), h("ul", {style: "margin-top:14px"}, ["Master Process Handbook", "Process Library & Flow Studio", "Governance & Approvals", "Word / PDF Export Center"].map((x) => h("li", null, x))),
        h("p", {style: "margin:16px 0 0;font-weight:bold"}, "Classification: " + (S.cfg.classification || "Internal")))),
    h("div", {class: "form"}, h("div", {class: "kicker"}, S.cfg.org || "dormakaba MEA"), h("h1", null, "Sign in"), err,
      h("label", null, "Username"), u, h("label", null, "Password"), h("input", {type: "password", style: "display:none"}), p,
      h("div", {style: "margin-top:16px"}, h("button", {class: "btn pri", onclick: go}, "Sign in")),
      h("p", {class: "muted", style: "font-size:12px;margin-top:18px"}, "First start: user ", h("b", null, "admin"), " with the one-time password shown in the console window (also in ", h("code", null, "data\\FIRST_RUN_ADMIN_PASSWORD.txt"), "). Forgot it? Run ", h("b", null, "Reset admin password.bat"), " next to the EXE.")),
    h("div", {class: "band"}, h("span", null, "Process & Document Management"), h("span", null, S.cfg.region || "Region MEA"))));
}
function passwordView(forced) {
  const o = h("input", {type: "password"}), n = h("input", {type: "password"});
  return h("div", {class: "login"}, h("div", {class: "card"}, h("h1", null, "Change password"), forced ? h("div", {class: "banner warn"}, "You must set a new password before continuing.") : null,
    h("label", null, "Current password"), o, h("label", null, "New password (min 8 characters)"), n,
    h("div", {style: "margin-top:14px"}, h("button", {class: "btn pri", onclick: () => guard(async () => { await POST("/api/password", {old: o.value, new: n.value}); S.user.must_change = false; toast("Password changed"); render(); })}, "Save"))));
}
function layout() {
  const q = h("input", {type: "text", placeholder: "Search processes, IDs, SAP transactions, diagram labels…", "aria-label": "Search", onkeydown: (e) => { if (e.key === "Enter" && q.value.trim()) location.hash = "#/search/" + encodeURIComponent(q.value.trim()); }});
  return h("div", {class: "layout"},
    h("div", {class: "top"}, h("a", {class: "brand", href: "#/dashboard", "aria-label": "dormakaba MEA Process Hub"}, h("img", {class: "logo-c", src: "/brand/dormakaba_logo.png", alt: "dormakaba"}), h("img", {class: "logo-w", src: "/brand/dormakaba_logo_white.png", alt: ""}), h("span", {class: "prod"}, "MEA Process Hub")), h("div", {class: "search"}, q),
      h("div", {class: "userbox"}, h("span", null, S.user.display_name, " · ", h("span", {class: "chip"}, S.user.role)), h("button", {class: "btn sm", onclick: () => passwordModal()}, "Password"),
        h("button", {class: "btn sm", onclick: async () => { await POST("/api/logout"); S.user = null; render(); }}, "Sign out"))),
    h("nav", {class: "nav", "aria-label": "Primary"}, NAV.filter((n) => n[0] !== "#/admin" || can("admin")).map(([href, label, ic]) => h("a", {href, "data-nav": href}, ic, h("span", null, label)))),
    h("main", {class: "main", id: "main"}));
}
function svgIcon() { const s = document.createElementNS("http://www.w3.org/2000/svg", "svg"); s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("fill", "none"); s.setAttribute("stroke-width", "2"); s.setAttribute("stroke-linecap", "round"); const p = document.createElementNS("http://www.w3.org/2000/svg", "path"); p.setAttribute("d", "M5 8h14M5 12h14M5 16h9"); s.append(p); return s; }
function passwordModal() { const m = modal("Change password", passwordView(false).firstChild); }

async function route() {
  const main = $("#main"); if (!main) return;
  if (main.__cleanup) { main.__cleanup(); main.__cleanup = null; }
  if (editorInst) { editorInst.dispose(); editorInst = null; }
  const parts = (location.hash || "#/dashboard").slice(2).split("/").map(decodeURIComponent);
  const top = parts[0] || "dashboard";
  document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("on", a.dataset.nav === "#/" + (top === "process" ? "handbook" : top === "search" ? "" : top)));
  clear(main).append(h("p", {class: "muted"}, "Loading…"));
  try {
    const V = {dashboard: viewDashboard, handbook: viewHandbook, process: viewHandbook, library: viewLibrary, flow: viewFlow, departments: viewDepartments, governance: viewGovernance,
      reports: viewReports, import: viewImport, export: viewExport, admin: viewAdmin, search: viewSearch, new: viewNew};
    const node = await (V[top] || viewDashboard)(...parts.slice(1));
    if (node) {
      const h1 = node.querySelector && node.querySelector("h1");
      const navItem = NAV.find((n) => n[0] === "#/" + (top === "process" ? "handbook" : top));
      if (h1 && !node.querySelector(".kicker")) h1.before(h("div", {class: "kicker"}, (S.cfg.org || "dormakaba MEA") + " · " + (navItem ? navItem[1] : "Process Hub")));
      clear(main).append(node);
    }
  } catch (e) { clear(main).append(h("div", {class: "banner bad"}, e.message)); }
  main.scrollTop = 0;
}
const reloadTree = async () => { S.tree = (await GET("/api/tree")).departments; };
const pLink = (id, text) => h("a", {href: "#/process/" + encodeURIComponent(id)}, text || id);

// ---------------------------------------------------------------- dashboard
async function viewDashboard() {
  const d = await GET("/api/dashboard");
  const inbox = (await GET("/api/inbox")).rows;
  const kpi = (n, l, href, cls) => h("div", {class: "card kpi " + (cls || ""), onclick: () => href && (location.hash = href)}, h("div", {class: "n"}, n), h("div", {class: "l"}, l));
  const list = (items, empty, fn) => items.length ? h("ul", {style: "margin:0;padding-left:18px"}, items.slice(0, 8).map(fn), items.length > 8 ? h("li", {class: "muted"}, "… " + (items.length - 8) + " more") : null) : h("p", {class: "muted"}, empty);
  const ip = d.import_progress;
  return h("div", {class: "page"}, h("h1", null, "Enterprise overview"), h("div", {class: "sub"}, "Live from the process database – nothing here is sample data. " + d.sources + " source document(s) imported."),
    inbox.length ? h("div", {class: "card"}, h("h3", null, "My tasks (" + inbox.length + ")"), table(["Task", "Process", "Detail"], inbox.slice(0, 12).map((x) => ({click: () => (location.hash = "#/process/" + encodeURIComponent(x.process_id)), cells: [h("span", {class: "chip warn"}, x.kind), x.process_id + " – " + x.name, x.detail]})))) : null,
    h("div", {class: "grid g4"}, kpi(d.total, "Registered processes", "#/library"), kpi(d.by_status.published || 0, "Published (approved)", "#/library"),
      kpi(d.pending.length, "In review / approval", "#/governance/approvals", d.pending.length ? "warn" : ""), kpi(d.findings.high, "High-severity open findings", "#/reports/findings", d.findings.high ? "bad" : ""),
      kpi(d.needs_flow_validation, "Flowcharts requiring validation", "#/reports/gaps", d.needs_flow_validation ? "warn" : ""), kpi(d.missing_owner.length, "Processes without owner", "#/reports/gaps", "warn"),
      kpi(d.no_kpi, "Processes without KPI", "#/reports/gaps"), kpi(d.no_raci, "Processes without RACI", "#/governance/raci")),
    h("div", {class: "grid g2"},
      h("div", {class: "card"}, h("h3", null, "Import verification progress"), h("div", {class: "bar"}, h("i", {style: "width:" + (ip.total ? Math.round(100 * ip.accepted / ip.total) : 0) + "%"})),
        h("p", {class: "muted"}, ip.accepted + " of " + ip.total + " processes verified/authored · " + ip.imported + " still Imported / Unverified"), h("a", {href: "#/import"}, "Open import review workspace →")),
      h("div", {class: "card"}, h("h3", null, "Pending approvals"), list(d.pending, "Nothing waiting.", (x) => h("li", null, pLink(x.process_id, x.process_id + " – " + x.name), " ", chipS(x.status)))),
      h("div", {class: "card"}, h("h3", null, "Overdue reviews"), list(d.overdue_reviews, "None overdue. (" + d.no_review_schedule + " processes have no review schedule yet.)", (x) => h("li", null, pLink(x.process_id, x.process_id), " – due ", x.next_review))),
      h("div", {class: "card"}, h("h3", null, "Recently updated"), list(d.recent, "—", (x) => h("li", null, pLink(x.process_id, x.process_id + " – " + x.name), " ", chipS(x.status), " ", h("span", {class: "muted"}, fmtDate(x.updated_at))))),
      h("div", {class: "card"}, h("h3", null, "Missing flowcharts"), list(d.missing_flowchart, "All processes have a flowchart.", (x) => h("li", null, pLink(x.process_id, x.process_id + " – " + x.name)))),
      h("div", {class: "card"}, h("h3", null, "Duplicate candidates / open findings"), h("p", null, d.findings.duplicates + " duplicate candidates · " + d.findings.open + " open findings · " + d.orphan + " processes with no relationships"), h("a", {href: "#/reports/findings"}, "Open findings register →"))),
    h("div", {class: "card"}, h("h3", null, "Department coverage"), table(["Department", "Processes", "Published", "With flowchart", ""], d.coverage.map((c) => [h("a", {href: "#/departments/" + c.code}, c.name), c.total, c.published, c.with_flow,
      c.total ? "" : h("span", {class: "chip warn"}, "No documented processes – Documentation Required")]))));
}

// ---------------------------------------------------------------- tree + handbook / process page
function treePanel(current) {
  const wrap = h("div", {class: "tree"}, h("div", {class: "hd"}, "MASTER HANDBOOK"));
  for (const d of S.tree) {
    const has = d.processes.some((p) => p.process_id === current);
    const det = h("details", {open: has || (!current && d.processes.length && d === S.tree.find((x) => x.processes.length))}, h("summary", null, d.name, h("span", {class: "cnt"}, d.processes.length)));
    if (!d.processes.length) det.append(h("div", {class: "muted", style: "padding:4px 20px;font-size:12px"}, "No processes yet"));
    d.processes.forEach((p) => det.append(h("a", {class: "p" + (p.process_id === current ? " on" : ""), href: "#/process/" + encodeURIComponent(p.process_id), title: p.process_id}, p.name + (p.countries ? " (" + p.countries + ")" : ""))));
    wrap.append(det);
  }
  if (can("admin", "controller", "dept_owner", "editor")) wrap.append(h("div", {style: "margin-top:10px"}, h("a", {class: "btn sm", href: "#/new"}, "+ New process")));
  return wrap;
}
async function viewHandbook(pid) {
  if (!pid) {
    const first = S.tree.flatMap((d) => d.processes)[0];
    return h("div", {class: "page hb"}, treePanel(null), h("div", null, h("h1", null, "Master Handbook"), h("div", {class: "sub"}, "Generated dynamically from the process database. Choose a process on the left."),
      h("div", {class: "card"}, h("h3", null, "Export the complete handbook"), h("div", {class: "row"}, exportBtns({scope: "handbook"})),
        h("p", {class: "muted"}, "Exports use one consistent snapshot. Unapproved processes are labelled in the document and the cover shows an UNCONTROLLED DRAFT notice.")),
      first ? h("a", {class: "btn pri", href: "#/process/" + encodeURIComponent(first.process_id)}, "Open first process") : h("p", null, "No processes yet – import documents or create a process.")));
  }
  return processPage(pid, null, false);
}
function exportBtns(spec) {
  return ["docx", "pdf", "html", "zip"].map((f) => h("button", {class: "btn" + (f === "docx" ? " pri" : ""), title: f === "zip" ? "Editable .drawio sources + previews" : "", onclick: () => doExport(Object.assign({fmt: f}, spec))}, f === "zip" ? "Diagrams ZIP" : f.toUpperCase()));
}
async function doExport(spec) {
  toast("Generating " + spec.fmt.toUpperCase() + "…");
  await guard(async () => { const r = await POST("/api/exports", spec); toast("Export ready: " + r.export.filename); download("/api/exports/" + r.export.id + "/download"); });
}
async function processPage(pid, versionId, editing) {
  const d = await GET("/api/process/" + encodeURIComponent(pid) + (versionId ? "?version=" + versionId : ""));
  const p = d.process, v = d.version, c = v.content, perms = d.perms;
  const isLatest = !versionId || (d.versions[0] && d.versions[0].id === v.id);
  const reload = async (ed) => { await reloadTree(); clear($("#main")).append(await processPage(pid, null, ed)); };
  const act = (label, fn, cls) => h("button", {class: "btn " + (cls || ""), onclick: () => guard(async () => { if (editorInst && editorInst.isDirty()) await editorInst.save(); await fn(); })}, label);
  const bar = h("div", {class: "row"});
  const ov = d.open_version;
  if (editing) {
    bar.append(act("Save now", async () => { await editorInst.save(); toast("Saved"); }), act("Submit for review", async () => {
      const sum = await promptBox("Submit for review", "Change summary (what changed and why)", {multiline: true, required: true, value: v.change_summary || "", ok: "Submit"}); if (sum === null) return;
      const major = await confirmBox("Is this a MAJOR change (new major version, e.g. 2.0)? Choose Cancel for a minor change.", "Major change").then((x) => x);
      await POST("/api/process/" + pid + "/submit", {change_summary: sum, bump: major ? "major" : "minor"}); toast("Submitted for review"); editorInst.dispose(); editorInst = null; await reload(false);
    }, "pri"), act("Done editing", async () => { editorInst.dispose(); editorInst = null; await reload(false); }));
  } else {
    if (isLatest && perms.edit && (!ov || ["imported", "draft", "changes_requested"].includes(ov.status))) bar.append(h("button", {class: "btn pri", onclick: async () => { clear($("#main")).append(await processPage(pid, null, true)); }}, ov ? "Edit draft" : "Edit (creates draft)"));
    if (ov && ov.status === "imported" && perms.accept_import) bar.append(act("Accept import", async () => { await POST("/api/process/" + pid + "/accept-import", {}); toast("Import accepted – now a Draft"); await reload(); }));
    if (ov && ov.status === "under_review" && perms.review) bar.append(act("Approve review", async () => { await POST("/api/process/" + pid + "/review", {decision: "approve_review"}); await reload(); }, "pri"),
      act("Request changes", async () => { const n = await promptBox("Request changes", "What must change?", {multiline: true, required: true}); if (n === null) return; await POST("/api/process/" + pid + "/review", {decision: "request_changes", note: n}); await reload(); }, "bad"));
    if (ov && ov.status === "pending_approval" && perms.approve) bar.append(act("Approve", async () => { await POST("/api/process/" + pid + "/approve", {decision: "approve"}); toast("Approved"); await reload(); }, "pri"),
      act("Reject", async () => { const n = await promptBox("Reject", "Reason", {multiline: true, required: true}); if (n === null) return; await POST("/api/process/" + pid + "/approve", {decision: "reject", note: n}); await reload(); }, "bad"));
    if (ov && ov.status === "approved" && perms.publish) bar.append(act("Publish", async () => { await POST("/api/process/" + pid + "/publish", {}); toast("Published"); await reload(); }, "pri"));
    if (ov && ["under_review", "pending_approval", "approved"].includes(ov.status) && (perms.review || perms.edit)) bar.append(act("Withdraw to draft", async () => { await POST("/api/process/" + pid + "/withdraw", {}); await reload(); }));
    if (!isLatest && perms.edit && !ov) bar.append(act("Restore this version (new draft)", async () => { if (await confirmBox("Create a new draft containing the content of version " + v.version + "? History is preserved.", "Create draft")) { await POST("/api/process/" + pid + "/restore", {version_id: v.id}); toast("New draft created from v" + v.version); await reload(true); } }));
  }
  bar.append(h("button", {class: "btn", onclick: () => doExport({scope: "process", ids: [pid], fmt: "docx", version_id: versionId || undefined})}, "DOCX"), h("button", {class: "btn", onclick: () => doExport({scope: "process", ids: [pid], fmt: "pdf", version_id: versionId || undefined})}, "PDF"));

  const head = h("div", {class: "phead"}, h("div", null, h("div", {class: "kicker"}, (p.department || "") + " · Master Handbook"), h("h1", null, p.name), h("div", {class: "pid"}, p.process_id + " · Version " + v.version + " · " + (p.department || "") + (p.countries ? " · " + p.countries : "") + (p.chart_id && p.chart_id !== p.process_id ? " · source chart ID " + p.chart_id : ""))),
    h("div", {class: "row"}, chipS(v.status, d.status_label), d.versions.length > 1 ? h("select", {style: "width:auto", "aria-label": "Version", onchange: (e) => { location.hash = "#/process/" + encodeURIComponent(pid) + (e.target.value ? "?v=" + e.target.value : ""); }}, "") : null));
  // version selector handled below via query in hash
  const banners = [];
  if (v.status === "imported") banners.push(h("div", {class: "banner warn"}, "Imported / Unverified – extracted automatically from the source document(s). Verify against the original (see Sources tab) before submitting for approval."));
  if (!isLatest) banners.push(h("div", {class: "banner info"}, "You are viewing historical version " + v.version + " (" + d.status_label + "). Published versions are immutable."));
  if (ov && v.id !== ov.id && isLatest === false && d.published_version) banners.push(h("div", {class: "banner info"}, "A newer revision " + ov.version + " is " + (S.cfg.statuses[ov.status] || ov.status) + "."));
  if (v.status === "changes_requested" && v.review_note) banners.push(h("div", {class: "banner bad"}, "Changes requested: " + v.review_note));
  if (d.diagram && d.diagram.validation === "requires_validation") banners.push(h("div", {class: "banner warn"}, "Flowchart status: Requires Functional Validation – the imported picture is a locked reference layer; redraw it in Flow Studio and have the owner confirm it."));
  const body = h("div");
  if (editing) {
    editorInst = buildEditor(d, (payload) => PUT("/api/process/" + encodeURIComponent(pid) + "/draft", payload));
    body.append(flowCard(d, true, reload), editorInst.el);
  } else {
    body.append(overviewCard(c), flowCard(d, false, reload), tabsView(d, pid, reload));
  }
  const foot = h("div", {class: "footbar"}, h("span", null, "⛁ Autosave & version control · " + d.versions.length + " revision(s) · owner: " + (p.owner || "not assigned") + " · Classification: " + (S.cfg.classification || "Internal")),
    h("span", {class: "brandfoot"}, S.cfg.region || "Region MEA", h("img", {src: "/brand/dormakaba_logo.png", alt: "dormakaba"})), h("span", {class: "row"}, "Export:", ...["docx", "pdf"].map((f) => h("button", {class: "btn sm", onclick: () => doExport({scope: "process", ids: [pid], fmt: f})}, f.toUpperCase()))));
  const page = h("div", {class: "page hb"}, treePanel(pid), h("div", null, head, h("div", {style: "margin:10px 0"}, bar), banners, body, foot));
  if (d.versions.length > 1) { const sel = page.querySelector("select"); d.versions.forEach((x) => sel.append(h("option", {value: x.id, selected: x.id === v.id}, "v" + x.version + " · " + (S.cfg.statuses[x.status] || x.status)))); sel.onchange = (e) => { reloadVersion(pid, e.target.value); }; }
  return page;
}
async function reloadVersion(pid, vid) { clear($("#main")).append(await processPage(pid, vid, false)); }
function overviewCard(c) {
  const rows = TEXT_FIELDS.filter(([k]) => c[k]).map(([k, l]) => [h("b", null, l), h("span", {style: "white-space:pre-wrap"}, c[k])]);
  if (c.responsible && c.responsible.length) rows.push([h("b", null, "Responsible"), c.responsible.join(" · ")]);
  return h("div", {class: "card"}, h("h3", null, "Objective & definition"), rows.length ? h("table", {class: "t"}, h("tbody", null, rows.map((r) => h("tr", null, h("td", {style: "width:200px"}, r[0]), h("td", null, r[1]))))) : h("p", {class: "muted"}, "No definition yet – this is a Documentation Required gap."));
}
function previewUrl(dg) { return dg.preview_asset_id ? "/api/assets/" + dg.preview_asset_id : "/api/diagram-versions/" + dg.id + "/svg"; }
function flowCard(d, editing, reload) {
  const dg = d.diagram, p = d.process;
  const card = h("div", {class: "flow"}, h("div", {class: "row spread"}, h("b", null, "Process Flow"), h("span", {class: "muted"}, dg ? dg.code + " · revision " + dg.ver_no + (dg.locked_by ? " · locked by " + dg.locked_by : "") : "")));
  if (!dg) {
    card.append(h("p", {class: "muted"}, "No flowchart for this version."));
    if (d.perms.edit) { const sel = h("select", {style: "width:auto"}, Object.entries(S.cfg.templates).map(([k, n]) => h("option", {value: k}, n)));
      card.append(h("div", {class: "row"}, sel, h("button", {class: "btn pri", onclick: () => guard(async () => { const r = await POST("/api/diagrams", {process_id: p.process_id, title: p.name, template: sel.value}); location.hash = "#/flow/" + r.diagram_id; })}, "Create from template"), importDrawioBtn(p.process_id, reload))); }
    return card;
  }
  const img = h("img", {src: previewUrl(dg), alt: "Flowchart " + p.process_id, onclick: () => modal("Process Flow – " + p.process_id, h("img", {class: "big", src: previewUrl(dg), alt: ""}), {wide: true})});
  card.append(img);
  const links = dg.nodes.filter((n) => n.meta && n.meta.process_ref);
  const bar = h("div", {class: "row"},
    h("button", {class: "btn sm", onclick: () => img.click()}, "View full screen"),
    d.perms.edit ? h("button", {class: "btn sm pri", onclick: () => { location.hash = "#/flow/" + dg.diagram_id; }}, "Edit diagram") : null,
    h("button", {class: "btn sm", onclick: () => diagramHistory(dg)}, "Revision history"),
    h("button", {class: "btn sm", onclick: () => download("/api/diagram-versions/" + dg.id + "/xml")}, "Download .drawio"),
    h("button", {class: "btn sm", onclick: () => download("/api/diagram-versions/" + dg.id + "/svg")}, "Export SVG"),
    d.perms.edit ? importDrawioBtn(p.process_id, reload, "Replace diagram") : null,
    links.length ? h("select", {style: "width:auto", onchange: (e) => e.target.value && (location.hash = "#/process/" + e.target.value)}, h("option", {value: ""}, "Open related process…"), links.map((n) => h("option", {value: n.meta.process_ref}, n.meta.process_ref + " ← " + (n.label || n.node_id)))) : null);
  card.append(bar);
  if (dg.validation === "requires_validation") card.append(h("p", {class: "muted", style: "font-size:12px"}, "Original picture preserved as locked layer. Use Edit diagram to redraw shapes/connectors."));
  return card;
}
function importDrawioBtn(pid, reload, label) {
  const f = h("input", {type: "file", accept: ".drawio,.xml", style: "display:none", onchange: () => guard(async () => {
    const file = f.files[0]; if (!file) return; const xml = await readFile(file, "text");
    const r = await POST("/api/diagrams", {process_id: pid, title: file.name, xml}); toast("Diagram imported"); location.hash = "#/flow/" + r.diagram_id; })});
  return h("span", null, f, h("button", {class: "btn sm", onclick: () => f.click()}, label || "Import .drawio"));
}
async function diagramHistory(dg) {
  const r = await GET("/api/diagrams/" + dg.diagram_id);
  modal("Diagram revisions – " + dg.code, table(["Rev", "Origin", "Validation", "By", "When", "Note", ""], r.versions.map((v) => ["#" + v.ver_no, v.origin, v.validation, v.author, fmtDate(v.created_at), v.note,
    h("span", {class: "row"}, h("a", {href: "/api/diagram-versions/" + v.id + "/xml"}, ".drawio"), v.preview_asset_id ? h("a", {href: "/api/assets/" + v.preview_asset_id, target: "_blank"}, "preview") : null)])), {wide: true});
}
function tabsView(d, pid, reload) {
  const c = d.version.content, names = ["Content", "RACI", "SAP", "KPI", "Escalation", "Related", "Sources", "Comments", "History"];
  const area = h("div", {class: "card"}), bar = h("div", {class: "tabs", role: "tablist"});
  const show = async (n) => {
    [...bar.children].forEach((b) => b.classList.toggle("on", b.textContent === n)); clear(area);
    if (n === "Content") { (c.sections || []).length ? c.sections.forEach((s) => area.append(h("h3", null, s.title), setHTML(h("div", {class: "rt"}), s.html))) : area.append(h("p", {class: "muted"}, "No additional content.")); }
    else if (n === "RACI") area.append(tblOrGap(TABLES.raci, c.raci, "No RACI defined. Responsible list from source: " + ((c.responsible || []).join(", ") || "none")));
    else if (n === "SAP") area.append(tblOrGap(TABLES.sap, c.sap, "No SAP transactions documented in the source (Documentation Required)."));
    else if (n === "KPI") area.append(tblOrGap(TABLES.kpis, c.kpis, "No KPIs defined for this process."));
    else if (n === "Escalation") area.append(tblOrGap(TABLES.escalation, c.escalation, "No escalation matrix on this record."), c.activities.length ? [h("h3", null, "Detailed activities"), tblOrGap(TABLES.activities, c.activities, "")] : null);
    else if (n === "Related") {
      area.append(d.relationships.length ? table(["Direction", "Type", "Process", ""], d.relationships.map((r) => [r.dir === "out" ? "→ to" : "← from", r.rel_type + (r.inferred == 1 ? " (inferred from text)" : r.inferred == 2 ? " (suggested – confirm or remove)" : ""), pLink(r.process_id, r.process_id + " – " + r.name),
        d.perms.manage_relationships && r.inferred != 1 ? h("button", {class: "btn sm bad", onclick: () => guard(async () => { await DEL("/api/relationships/" + r.id); show("Related"); })}, "Remove") : ""])) : h("p", {class: "muted"}, "No relationships recorded – orphan process."));
      if (d.perms.manage_relationships) { const to = h("input", {type: "text", placeholder: "Process ID e.g. WL-M-IB-01"}), ty = h("select", {style: "width:auto"}, S.cfg.rel_types.map((t) => h("option", null, t)));
        area.append(h("div", {class: "row", style: "margin-top:10px"}, ty, to, h("button", {class: "btn", onclick: () => guard(async () => { await POST("/api/relationships", {from: pid, to: to.value.trim(), type: ty.value}); toast("Relationship added"); reload(); })}, "Link"))); }
    } else if (n === "Sources") {
      area.append(d.mappings.length ? table(["Source file", "Section", "Role", "Similarity", ""], d.mappings.map((m) => [m.filename, m.heading, m.role, m.similarity == null ? "—" : Math.round(m.similarity * 100) + "%", h("a", {href: "/api/sources/" + m.source_id + "/download"}, "original")])) : h("p", {class: "muted"}, "Authored in the application – no source document."),
        d.findings.length ? [h("h3", null, "Findings"), table(["Sev", "Kind", "Title", "Status"], d.findings.map((f) => [h("span", {class: "chip " + (f.severity === "high" ? "bad" : f.severity === "medium" ? "warn" : "")}, f.severity), f.kind, f.title, f.status]))] : null);
    } else if (n === "Comments") {
      const inp = h("textarea", {placeholder: "Add a comment…"});
      area.append(d.comments.length ? d.comments.map((cm) => h("div", {class: "card", style: "padding:8px 12px"}, h("b", null, cm.author), " ", h("span", {class: "muted"}, fmtDate(cm.created_at) + " · " + cm.kind + (cm.resolved ? " · resolved" : "")), h("div", {style: "white-space:pre-wrap"}, cm.body))) : h("p", {class: "muted"}, "No comments."),
        d.perms.comment ? h("div", null, inp, h("button", {class: "btn", style: "margin-top:6px", onclick: () => guard(async () => { await POST("/api/process/" + pid + "/comments", {body: inp.value}); reload(); })}, "Post comment")) : null);
    } else if (n === "History") {
      area.append(table(["Version", "Status", "Author", "Created", "Reviewed", "Approved", "Published", "Summary", ""], d.versions.map((v) => [h("a", {href: "javascript:void 0", onclick: () => reloadVersion(pid, v.id)}, "v" + v.version), chipS(v.status), v.author, fmtDate(v.created_at), v.reviewed_by || "", v.approved_by || "", fmtDate(v.published_at), v.change_summary,
        d.versions.length > 1 && v.id !== d.version.id ? h("button", {class: "btn sm", onclick: () => compareModal(pid, v.id, d.version.id)}, "Compare with shown") : ""])));
      const log = await GET("/api/changelog?process=" + encodeURIComponent(pid));
      area.append(h("h3", null, "Change log"), table(["When", "Who", "Action", "Detail"], log.rows.map((r) => [fmtDate(r.ts), r.username, r.action, r.detail])));
    }
  };
  names.forEach((n) => bar.append(h("button", {class: "tab", role: "tab", onclick: () => show(n)}, n)));
  show(c.sections && c.sections.length ? "Content" : "RACI");
  return h("div", null, bar, area);
}
function tblOrGap(spec, rows, gap) { return rows && rows.length ? table(spec.cols.map((c) => c[1]), rows.map((r) => spec.cols.map((c) => r[c[0]]))) : h("p", {class: "muted"}, gap); }
async function compareModal(pid, a, b) {
  const r = await GET("/api/process/" + encodeURIComponent(pid) + "/compare?a=" + a + "&b=" + b);
  modal("Compare v" + r.a.version + " → v" + r.b.version, h("div", {class: "diff"}, r.identical ? h("p", null, "No differences.") : null, r.diagram ? h("div", {class: "banner info"}, "Diagram revision changed (version " + r.diagram.before + " → " + r.diagram.after + "). Compare the flow images in the History / Revision dialog.") : null,
    r.changes.map((x) => h("div", {class: x.op}, (x.op === "add" ? "+ " : "− ") + x.text))), {wide: true});
}

// ---------------------------------------------------------------- new process
async function viewNew() {
  const f = {name: h("input", {type: "text"}), id: h("input", {type: "text", placeholder: "optional – auto-assigned if empty"}), dept: h("select", null, S.tree.map((d) => h("option", {value: d.id}, d.name))),
    kind: h("select", null, S.cfg.kinds.map((k) => h("option", null, k))), tpl: h("select", null, h("option", {value: ""}, "No flowchart yet"), Object.entries(S.cfg.templates).map(([k, n]) => h("option", {value: k}, n))),
    copy: h("input", {type: "text", placeholder: "optional – existing process ID to copy"}), owner: h("input", {type: "text"})};
  return h("div", {class: "page"}, h("h1", null, "New process"), h("div", {class: "sub"}, "Creates a Draft (v0.1). It must pass review and approval before it is published."),
    h("div", {class: "card fields"}, [["Process name", f.name], ["Process ID", f.id], ["Department", f.dept], ["Type", f.kind], ["Flowchart template", f.tpl], ["Copy from existing", f.copy], ["Process owner", f.owner]].map(([l, e]) => h("div", null, h("label", null, l), e))),
    h("button", {class: "btn pri", onclick: () => guard(async () => { const r = await POST("/api/process", {name: f.name.value, process_id: f.id.value, department_id: +f.dept.value, kind: f.kind.value, template: f.tpl.value, copy_from: f.copy.value.trim(), owner: f.owner.value});
      await reloadTree(); toast("Created " + r.process_id); location.hash = "#/process/" + encodeURIComponent(r.process_id); })}, "Create draft"));
}

// ---------------------------------------------------------------- library, search
async function viewLibrary() {
  const st = {dept: "", status: "", kind: "", q: ""}, out = h("div");
  const load = async () => { const r = await GET("/api/library?" + new URLSearchParams(st)); clear(out).append(h("p", {class: "muted"}, r.processes.length + " processes"), table(["ID", "Name", "Department", "Type", "Region", "Version", "Status", "Flowchart", "Owner"],
    r.processes.map((p) => ({click: () => (location.hash = "#/process/" + encodeURIComponent(p.process_id)), cells: [h("span", {class: "mono"}, p.process_id), p.name, p.department, p.kind, p.countries, p.version, chipS(p.status), p.has_diagram ? (p.diagram_validation === "requires_validation" ? h("span", {class: "chip warn"}, "to validate") : h("span", {class: "chip ok"}, "yes")) : h("span", {class: "chip bad"}, "missing"), p.owner || h("span", {class: "muted"}, "—")]})))); };
  const sel = (k, opts) => h("select", {style: "width:auto", onchange: (e) => { st[k] = e.target.value; load(); }}, h("option", {value: ""}, "All " + k), opts.map(([v, l]) => h("option", {value: v}, l)));
  await load();
  return h("div", {class: "page"}, h("div", {class: "row spread"}, h("h1", null, "Process Library"), can("admin", "controller", "dept_owner", "editor") ? h("a", {class: "btn pri", href: "#/new"}, "+ New process") : null),
    h("div", {class: "row", style: "margin-bottom:10px"}, sel("dept", S.tree.map((d) => [d.code, d.name])), sel("status", Object.entries(S.cfg.statuses)), sel("kind", S.cfg.kinds.map((k) => [k, k])),
      h("input", {type: "text", placeholder: "Filter by name or ID", style: "width:240px", oninput: (e) => { st.q = e.target.value; load(); }})), out);
}
async function viewSearch(q) {
  const r = await GET("/api/search?q=" + encodeURIComponent(q || ""));
  return h("div", {class: "page"}, h("h1", null, "Search: " + q), h("div", {class: "sub"}, r.results.length + " result(s) – process names/IDs, SAP transactions, KPI text, content and diagram labels."),
    r.results.map((x) => h("div", {class: "card"}, h("div", {class: "row"}, pLink(x.process_id, x.process_id + " – " + x.name), chipS(x.status), h("span", {class: "muted"}, x.department)), h("div", {class: "muted"}, x.snippet))));
}

// ---------------------------------------------------------------- flow studio
async function viewFlow(id) {
  if (id) { const root = $("#main"); clear(root); await openFlowStudio(+id, root, "#/flow"); return null; }
  const r = await GET("/api/diagrams");
  const title = h("input", {type: "text", placeholder: "Title for a new library diagram"}), tpl = h("select", {style: "width:auto"}, Object.entries(S.cfg.templates).map(([k, n]) => h("option", {value: k}, n)));
  return h("div", {class: "page"}, h("h1", null, "Flow Studio"), h("div", {class: "sub"}, "Every diagram stores native, editable draw.io XML with a revision history. Editing a process diagram creates a draft revision; published versions never change."),
    h("div", {class: "card"}, h("h3", null, "New diagram from template"), h("div", {class: "row"}, title, tpl, h("button", {class: "btn pri", disabled: !can("admin", "controller", "dept_owner", "editor"), onclick: () => guard(async () => { const x = await POST("/api/diagrams", {title: title.value || "Untitled", template: tpl.value}); location.hash = "#/flow/" + x.diagram_id; })}, "Create"))),
    table(["Code", "Title", "Process", "Revision", "Validation", "Origin", ""], r.diagrams.map((d) => [d.code, d.title, d.process_id ? pLink(d.process_id) : "library", "#" + d.ver_no, d.validation === "requires_validation" ? h("span", {class: "chip warn"}, "requires validation") : d.validation, d.origin,
      h("a", {class: "btn sm", href: "#/flow/" + d.id}, "Open")])));
}

// ---------------------------------------------------------------- departments
async function viewDepartments(code) {
  const cov = (await GET("/api/dashboard")).coverage;
  if (!code) return h("div", {class: "page"}, h("h1", null, "Departments"), h("div", {class: "grid g2"}, S.tree.map((d) => h("div", {class: "card"}, h("h3", null, h("a", {href: "#/departments/" + d.code}, d.name)), h("div", {class: "muted"}, d.processes.length + " processes"),
    d.processes.length ? null : h("span", {class: "chip warn"}, "No documented processes – Documentation Required")))));
  const d = S.tree.find((x) => x.code === code); if (!d) throw new Error("Unknown department");
  const pend = (await GET("/api/approvals")).rows.filter((x) => x.department === d.name);
  return h("div", {class: "page"}, h("div", {class: "row spread"}, h("h1", null, d.name), h("div", {class: "row"}, exportBtns({scope: "department", dept: d.code}))),
    h("div", {class: "card"}, h("h3", null, "Pending reviews / approvals"), pend.length ? table(["Process", "Status", "Version", "Author"], pend.map((x) => [pLink(x.process_id, x.process_id + " – " + x.name), chipS(x.status), x.version, x.author])) : h("p", {class: "muted"}, "None.")),
    h("div", {class: "card"}, h("h3", null, "Processes"), d.processes.length ? table(["ID", "Name", "Type", "Status", "Owner"], d.processes.map((p) => ({click: () => (location.hash = "#/process/" + encodeURIComponent(p.process_id)), cells: [p.process_id, p.name, p.kind, chipS(p.status), p.owner || "—"]}))) : h("p", {class: "muted"}, "No processes.")));
}

// ---------------------------------------------------------------- governance
async function viewGovernance(tab) {
  tab = tab || "approvals";
  const tabs = [["approvals", "Approvals"], ["raci", "RACI"], ["escalation", "Escalation matrix"], ["kpis", "KPIs"], ["changelog", "Revision history"], ["map", "Process map"], ["ownership", "Ownership & register"]];
  const bar = h("div", {class: "tabs"}, tabs.map(([k, l]) => h("a", {class: "tab" + (k === tab ? " on" : ""), href: "#/governance/" + k}, l)));
  let body;
  if (tab === "approvals") { const r = await GET("/api/approvals"); body = h("div", null, h("div", {class: "banner info"}, "Document approval (publishing a procedure) is separate from business-transaction approval (an actual sales order, PR, master-data change). This module controls the former."),
    r.rows.length ? table(["Process", "Department", "Status", "Version", "Author", "Submitted", "Summary"], r.rows.map((x) => ({click: () => (location.hash = "#/process/" + encodeURIComponent(x.process_id)), cells: [x.process_id + " – " + x.name, x.department, chipS(x.status), x.version, x.author, fmtDate(x.submitted_at), x.summary]}))) : h("p", {class: "muted"}, "Nothing is waiting for review or approval.")); }
  else if (tab === "raci") { const r = await GET("/api/raci"); body = h("div", null, h("div", {class: "banner warn"}, "Suggested corrections never rewrite approved responsibility assignments – owners must edit RACI in the process draft."),
    table(["Process", "Department", "Owner", "Responsible (source)", "RACI rows", "Issues"], r.rows.map((x) => ({click: () => (location.hash = "#/process/" + encodeURIComponent(x.process_id)), cells: [x.process_id + " – " + x.name, x.department, x.owner || "—", x.responsible_listed.join(", "), x.raci.length, x.issues.length ? h("span", {class: "chip bad"}, x.issues[0] + (x.issues.length > 1 ? " (+" + (x.issues.length - 1) + ")" : "")) : h("span", {class: "chip ok"}, "OK")]})))); }
  else if (tab === "escalation") { const r = await GET("/api/escalation"); body = r.rows.length ? table(["Process", "Department", "Stage", "Task / reminder to", "Time period", "Escalation", "Previous SLA"], r.rows.map((x) => [x.process_id, x.department, x.stage, x.to, x.time, x.action, x.sla])) : h("p", null, "No escalation data."); }
  else if (tab === "kpis") { const r = await GET("/api/kpis"); body = r.rows.length ? table(["Process", "Department", "KPI", "Definition", "Target"], r.rows.map((x) => [x.process_id, x.department, x.name, x.definition, x.target])) : h("p", null, "No KPIs."); }
  else if (tab === "changelog") { const r = await GET("/api/changelog"); body = table(["When", "Who", "Action", "Entity", "Detail"], r.rows.map((x) => [fmtDate(x.ts), x.username, x.action, x.entity_id, x.detail])); }
  else if (tab === "ownership") body = await ownershipView();
  else body = await mapView();
  return h("div", {class: "page"}, h("h1", null, "Governance"), bar, body);
}
async function ownershipView() {
  const lib = (await GET("/api/library")).processes.filter((p) => p.kind !== "reference");
  const dept = h("select", null, S.tree.map((d) => h("option", {value: d.code}, d.name))), owner = h("input", {type: "text", placeholder: "Process owner (name)"}), rev = h("input", {type: "text", placeholder: "Reviewer (name)"}),
    months = h("input", {type: "number", placeholder: "Review every N months", min: 1, max: 60}), only = h("input", {type: "checkbox", checked: true, style: "width:auto"});
  const fi = h("input", {type: "file", accept: ".xlsx"}), out = h("div");
  const rows = lib.map((p) => { const o = h("input", {type: "text", value: p.owner || ""}), r = h("input", {type: "text", value: p.reviewer || ""});
    return [h("a", {href: "#/process/" + encodeURIComponent(p.process_id)}, p.process_id), p.name, p.department, o, r, h("button", {class: "btn sm", onclick: () => guard(async () => { await POST("/api/ownership", {items: [{process_id: p.process_id, owner: o.value, reviewer: r.value}]}); toast("Saved " + p.process_id); })}, "Save")]; });
  return h("div", null, h("div", {class: "card"}, h("h3", null, "Bulk assign owner / reviewer to a department"), h("div", {class: "row"}, dept, owner, rev, months,
      h("label", {style: "margin:0"}, only, " only fill empty"), h("button", {class: "btn pri", onclick: () => guard(async () => { const r = await POST("/api/ownership", {dept: dept.value, owner: owner.value, reviewer: rev.value, review_months: months.value, only_empty: only.checked}); toast(r.updated + " processes updated"); route(); })}, "Apply")),
    h("p", {class: "muted"}, "Owners must be real people accountable for the process – the tool never invents them.")),
    h("div", {class: "card"}, h("h3", null, "Load owners, RACI and KPIs from Excel"), h("p", {class: "muted"}, "Download the register, fill the sheets Ownership, Cross-Functional RACI and KPI Register, and load it back. RACI/KPI changes become draft revisions that still go through review and approval."),
      h("div", {class: "row"}, h("a", {class: "btn", href: "/api/register.xlsx"}, "Download register workbook"), fi, h("button", {class: "btn pri", onclick: () => guard(async () => { if (!fi.files[0]) throw new Error("Choose the .xlsx first."); const buf = await readFile(fi.files[0]); const r = await api("POST", "/api/register-import", new Blob([buf]));
        clear(out).append(h("div", {class: "banner " + (r.errors.length ? "warn" : "ok")}, r.ownership + " ownership rows · RACI for " + r.raci_processes + " processes · KPIs for " + r.kpi_processes + " processes"), r.errors.length ? h("ul", null, r.errors.map((e) => h("li", null, e))) : null); })}, "Load workbook")), out),
    h("div", {class: "card"}, h("h3", null, "Per-process ownership (" + lib.length + ")"), table(["ID", "Name", "Department", "Owner", "Reviewer", ""], rows)));
}
async function mapView() {
  const m = await GET("/api/map"), codes = S.tree.map((d) => d.code).filter((c) => m.nodes.some((n) => n.dept === c)), pos = {}, W = 230, H = 22;
  codes.forEach((c, i) => m.nodes.filter((n) => n.dept === c).forEach((n, j) => pos[n.id] = {x: 20 + i * W, y: 40 + j * H, n}));
  const maxY = Math.max(...Object.values(pos).map((p) => p.y), 100) + 30, ns = "http://www.w3.org/2000/svg";
  const el = (t, a, txt) => { const e = document.createElementNS(ns, t); Object.entries(a).forEach(([k, v]) => e.setAttribute(k, v)); if (txt) e.textContent = txt; return e; };
  const svg = el("svg", {width: codes.length * W + 40, height: maxY, class: "mapsvg"});
  m.edges.forEach((e) => { const a = pos[e.from_id], b = pos[e.to_id]; if (a && b) svg.append(el("path", {d: `M${a.x + 170},${a.y} C${a.x + 215},${a.y} ${b.x - 40},${b.y} ${b.x},${b.y}`, fill: "none", stroke: e.inferred ? "#8aa" : "#d77", "stroke-dasharray": e.inferred ? "4 3" : "0"})); });
  codes.forEach((c, i) => svg.append(el("text", {x: 20 + i * W, y: 20, "font-weight": "bold", fill: "currentColor"}, c)));
  Object.values(pos).forEach((p) => { const g = el("g", {class: "mapnode"}); g.append(el("title", {}, p.n.process_id + " – " + p.n.name), el("rect", {x: p.x, y: p.y - 12, width: 168, height: 18, rx: 4, fill: "none", stroke: "#789"}), el("text", {x: p.x + 4, y: p.y + 1, fill: "currentColor"}, (p.n.process_id + " " + p.n.name).slice(0, 30))); g.onclick = () => (location.hash = "#/process/" + encodeURIComponent(p.n.process_id)); svg.append(g); });
  const sug = can("admin", "controller", "dept_owner", "editor") ? h("button", {class: "btn pri", onclick: () => guard(async () => { const r = await POST("/api/map/suggest-links"); toast(r.links_added + " handover links suggested from the Level 1 value stream (" + r.stages_matched + " stages matched)"); route(); })}, "Suggest links from Level 1 value stream") : null;
  return h("div", null, sug, h("div", {class: "banner info"}, "Built from recorded relationships (solid = authored, dashed = inferred from IDs mentioned in text). Diagram layout is not the source of relationships. Add links on a process's Related tab."),
    h("div", {class: "card", style: "overflow:auto"}, svg), h("div", {class: "card"}, h("h3", null, m.orphans.length + " orphan processes (no relationships)"), m.orphans.slice(0, 60).map((n) => h("span", {style: "margin-right:8px"}, pLink(n.process_id)))));
}

// ---------------------------------------------------------------- reports
async function viewReports(tab) {
  tab = tab || "inventory";
  const tabs = [["inventory", "Process inventory"], ["findings", "Findings register"], ["sources", "Source audit"], ["gaps", "Ownership & completeness gaps"]];
  const bar = h("div", {class: "tabs"}, tabs.map(([k, l]) => h("a", {class: "tab" + (k === tab ? " on" : ""), href: "#/reports/" + k}, l)));
  let body;
  if (tab === "inventory") { const r = await GET("/api/library"); body = h("div", null, h("a", {class: "btn pri", href: "/api/register.xlsx"}, "Download MEA_Master_Process_Register.xlsx"), h("p", {class: "muted"}, "Workbook contains inventory, source mapping, audit register, findings, escalation, KPI, flowchart index, RACI and revision history sheets."),
    table(["ID", "Name", "Department", "Status", "Version", "Next review"], r.processes.map((p) => [pLink(p.process_id), p.name, p.department, chipS(p.status), p.version, p.next_review || "—"]))); }
  else if (tab === "findings") body = await findingsView();
  else if (tab === "sources") { const r = await GET("/api/sources"); body = h("div", null, r.sources.map((s) => h("div", {class: "card"}, h("div", {class: "row spread"}, h("h3", null, s.filename.replace(/^[0-9a-f]{8}-/, "")), h("a", {class: "btn sm", href: "/api/sources/" + s.id + "/download"}, "Download original")),
    h("div", {class: "muted"}, "Cover: " + s.title + " · version " + (s.version_text || "?") + " · imported " + fmtDate(s.imported_at) + " · sha256 " + s.sha256.slice(0, 12)),
    h("p", null, "Declared (file name): ", h("b", null, s.declared_name || "?"), " → actual content: ", h("b", null, s.actual_name || "?"), " ", !s.declared_dept ? h("span", {class: "chip"}, "n/a") : s.declared_dept !== s.actual_dept ? h("span", {class: "chip bad"}, "MISMATCH") : h("span", {class: "chip ok"}, "consistent"), " · confidence ", s.confidence),
    h("p", {class: "muted"}, Object.entries(s.stats).map(([k, v]) => k + ": " + v).join(" · ")),
    table(["Process", "Source section", "Role", "Similarity"], s.processes.map((p) => [pLink(p.process_id, p.process_id + " – " + p.name), p.heading, p.role, p.similarity == null ? "" : Math.round(p.similarity * 100) + "%"]))))); }
  else { const d = await GET("/api/dashboard"); const L = (t, a) => h("div", {class: "card"}, h("h3", null, t + " (" + a.length + ")"), a.length ? a.slice(0, 80).map((x) => h("div", null, pLink(x.process_id, x.process_id + " – " + x.name))) : h("p", {class: "muted"}, "None")); body = h("div", {class: "grid g2"}, L("Processes without a named owner", d.missing_owner), L("Missing flowcharts", d.missing_flowchart), h("div", {class: "card"}, h("h3", null, "Counts"), h("p", null, d.no_kpi + " processes without KPI · " + d.no_raci + " without RACI · " + d.needs_flow_validation + " flowcharts requiring validation · " + d.orphan + " orphans"))); }
  return h("div", {class: "page"}, h("h1", null, "Reports"), bar, body);
}
async function findingsView() {
  const st = {kind: "", status: "open"}, out = h("div");
  const load = async () => { const r = await GET("/api/findings?" + new URLSearchParams(st)); clear(out).append(h("div", {class: "row spread"}, h("p", {class: "muted"}, r.rows.length + " finding(s)"),
    can("admin", "controller", "dept_owner") && r.rows.length ? h("button", {class: "btn", onclick: async () => { const dc = await promptBox("Apply one decision to all " + r.rows.length + " shown findings", "Decision / rationale (recorded with your name)", {multiline: true, required: true}); if (dc === null) return; const status = (await promptBox("Status", "accepted | resolved | wont_fix", {value: "accepted", required: true})); if (!status) return; await guard(() => POST("/api/findings/bulk", {ids: r.rows.map((x) => x.id), status, decision: dc})); load(); }}, "Apply decision to all shown") : null), r.rows.map((f) => h("div", {class: "card", style: "padding:10px 14px"},
    h("div", {class: "row spread"}, h("div", null, h("span", {class: "chip " + (f.severity === "high" ? "bad" : f.severity === "medium" ? "warn" : "")}, f.severity), " ", h("span", {class: "chip"}, f.kind), " ", h("b", null, f.title)),
      h("span", {class: "chip"}, f.status)), h("div", {class: "muted", style: "margin:4px 0"}, f.detail), h("div", null, h("b", null, "Recommended: "), f.recommended), f.pid_text ? h("div", null, "Process: ", pLink(f.pid_text, f.pid_text + " – " + f.pname)) : null, f.decision ? h("div", null, "Decision: " + f.decision + " (" + f.resolved_by + ")") : null,
    can("admin", "controller", "dept_owner") ? h("div", {class: "row", style: "margin-top:6px"}, ["accepted", "resolved", "wont_fix", "open"].filter((s) => s !== f.status).map((s) => h("button", {class: "btn sm", onclick: async () => { const dc = await promptBox("Record decision", "Decision / rationale", {multiline: true}); if (dc === null) return; await guard(() => PUT("/api/findings/" + f.id, {status: s, decision: dc})); load(); }}, "Mark " + s))) : null))); };
  await load();
  const sel = (k, opts) => h("select", {style: "width:auto", onchange: (e) => { st[k] = e.target.value; load(); }}, h("option", {value: ""}, "All " + k), opts.map((o) => h("option", {value: o, selected: st[k] === o}, o)));
  return h("div", null, h("div", {class: "row", style: "margin-bottom:8px"}, sel("kind", ["conflict", "gap", "duplicate", "uncertain"]), sel("status", ["open", "accepted", "resolved", "wont_fix"])), out);
}

// ---------------------------------------------------------------- import & review workspace
async function viewImport() {
  const out = h("div"), drop = h("div", {class: "dropzone"}, "Drop .docx / .drawio files here or ", h("button", {class: "btn sm", onclick: () => fi.click()}, "choose files"));
  const fi = h("input", {type: "file", accept: ".docx,.drawio", multiple: true, style: "display:none", onchange: () => up([...fi.files])});
  async function up(files) {
    for (const f of files) {
      await guard(async () => { toast("Importing " + f.name + "…"); const buf = await readFile(f); const r = await api("POST", "/api/import", new Blob([buf]), {headers: {"X-Filename": encodeURIComponent(f.name)}});
        r.sources.forEach((s) => toast(s.filename.replace(/^[0-9a-f]{8}-/, "") + ": " + s.new.length + " new processes, " + s.merged.length + " duplicate mappings")); r.skipped.forEach((n) => toast("Already imported: " + n)); });
    }
    await reloadTree(); viewImport().then((n) => clear($("#main")).append(n));
  }
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); }); drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); up([...e.dataTransfer.files].filter((f) => /\.(docx|drawio)$/i.test(f.name))); });
  const lib = (await GET("/api/library?status=imported")).processes, src = await GET("/api/sources");
  const rows = lib.map((p) => ({click: () => reviewWorkspace(p.process_id, out), cells: [p.process_id, p.name, p.department, p.kind, p.diagram_validation === "requires_validation" ? "flowchart to validate" : (p.has_diagram ? "ok" : "no flowchart")]}));
  return h("div", {class: "page"}, h("h1", null, "Import & Sources"), h("div", {class: "sub"}, src.sources.length + " source document(s) preserved unchanged. Imported content is never published automatically."),
    can("admin", "controller") ? h("div", {class: "card"}, drop, fi) : null,
    h("div", {class: "card"}, h("h3", null, "Import Review Workspace – " + lib.length + " process(es) Imported / Unverified"), h("p", {class: "muted"}, "Select a process to compare the original extraction (left) with the generated record (right)."), rows.length ? table(["ID", "Name", "Department", "Type", "Flowchart"], rows) : h("p", null, "Everything imported has been accepted or edited.")), out);
}
async function reviewWorkspace(pid, out) {
  const d = await GET("/api/process/" + encodeURIComponent(pid)), c = d.version.content;
  const dsel = h("select", {style: "width:auto"}, S.tree.map((x) => h("option", {value: x.id, selected: x.id === d.process.department_id}, x.name)));
  const left = h("div", {class: "card"}, h("h3", null, "Original source extraction"), d.mappings.map((m) => h("div", null, h("p", null, h("b", null, m.filename.replace(/^[0-9a-f]{8}-/, "")), " – ", m.heading, " ", h("span", {class: "chip"}, m.role), m.similarity != null ? " similarity " + Math.round(m.similarity * 100) + "%" : ""),
    h("div", {class: "rt"}, m.asset_ids.map((a) => h("img", {src: "/api/assets/" + a, alt: "source image", style: "max-width:100%;border:1px solid var(--line)"}))))),
    c.objective ? h("p", null, c.objective) : null, (c.sections || []).map((s) => setHTML(h("div", {class: "rt"}), s.html)));
  const right = h("div", {class: "card"}, h("h3", null, "Generated process record"), h("p", null, h("b", null, d.process.process_id), " – ", d.process.name), h("p", null, "Department: ", d.process.department, " · type: ", d.process.kind),
    h("p", null, "Responsible: ", (c.responsible || []).join(", ") || "—"), d.diagram ? h("img", {src: previewUrl(d.diagram), alt: "", style: "max-width:100%"}) : h("p", {class: "muted"}, "No diagram"),
    d.findings.length ? h("ul", null, d.findings.map((f) => h("li", null, h("span", {class: "chip " + (f.severity === "high" ? "bad" : "warn")}, f.severity), " ", f.title))) : null,
    h("div", {class: "row"}, can("admin", "controller") ? h("button", {class: "btn pri", onclick: () => guard(async () => { await POST("/api/process/" + pid + "/accept-import", {}); await reloadTree(); toast("Accepted"); viewImport().then((n) => clear($("#main")).append(n)); })}, "Accept extraction") : null,
      h("a", {class: "btn", href: "#/process/" + encodeURIComponent(pid)}, "Edit"),
      can("admin", "controller") ? [dsel, h("button", {class: "btn", onclick: () => guard(async () => { await PUT("/api/process/" + pid + "/department", {department_id: +dsel.value}); await reloadTree(); toast("Department reassigned"); })}, "Reassign department")] : null,
      h("button", {class: "btn", onclick: () => guard(async () => { const t = await promptBox("Mark conflict", "Describe the conflict", {multiline: true, required: true}); if (t === null) return; await POST("/api/process/" + pid + "/finding", {kind: "conflict", title: "Reviewer-marked conflict: " + d.process.name, detail: t}); toast("Conflict logged in findings register"); })}, "Mark conflict"),
      h("button", {class: "btn", onclick: () => guard(async () => { const t = await promptBox("Request owner review", "Message to the process owner", {multiline: true, required: true}); if (t === null) return; await POST("/api/process/" + pid + "/comments", {body: "OWNER REVIEW REQUESTED: " + t}); toast("Comment recorded on the process"); })}, "Request owner review")));
  clear(out).append(h("div", {class: "two"}, left, right));
  out.scrollIntoView({behavior: "smooth"});
}

// ---------------------------------------------------------------- export center
async function viewExport() {
  const sel = h("select", {multiple: true, size: 12}, S.tree.flatMap((d) => d.processes.map((p) => h("option", {value: p.process_id}, p.process_id + " – " + p.name)))), dept = h("select", null, S.tree.map((d) => h("option", {value: d.code}, d.name))), inc = h("input", {type: "checkbox", checked: true});
  const fmt = h("select", null, ["docx", "pdf", "html", "zip"].map((f) => h("option", {value: f}, f === "zip" ? "ZIP (editable .drawio diagrams)" : f.toUpperCase())));
  const hist = (await GET("/api/exports")).rows;
  return h("div", {class: "page"}, h("h1", null, "Export Center"), h("div", {class: "sub"}, "Each export is built from one consistent revision snapshot, hashed and logged."),
    h("div", {class: "grid g2"}, h("div", {class: "card"}, h("h3", null, "Scope"), h("label", null, "Format"), fmt,
      h("label", null, h("input", {type: "checkbox", style: "width:auto", checked: true, onchange: (e) => { inc.checked = e.target.checked; }}), " Include unapproved processes (labelled as uncontrolled draft)"),
      h("div", {class: "row", style: "margin-top:10px"}, h("button", {class: "btn pri", onclick: () => doExport({scope: "handbook", fmt: fmt.value, include_unapproved: inc.checked})}, "Complete master handbook")),
      h("label", null, "Department manual"), h("div", {class: "row"}, dept, h("button", {class: "btn", onclick: () => doExport({scope: "department", dept: dept.value, fmt: fmt.value, include_unapproved: inc.checked})}, "Export")),
      h("label", null, "Selected processes (Ctrl/Shift-click)"), sel, h("div", {style: "margin-top:6px"}, h("button", {class: "btn", onclick: () => { const ids = [...sel.selectedOptions].map((o) => o.value); doExport({scope: ids.length === 1 ? "process" : "selected", ids, fmt: fmt.value, include_unapproved: inc.checked}); }}, "Export selection")),
      h("p", {class: "muted"}, "A DOCX contains real Word text/tables with flowchart previews; the editable source stays a .drawio file (ZIP format). Word cannot edit the preview picture itself.")),
      h("div", {class: "card"}, h("h3", null, "Recent exports"), table(["#", "When", "By", "Scope", "Fmt", "Status", ""], hist.map((e) => [e.id, fmtDate(e.ts), e.username, e.scope.slice(0, 40), e.fmt, e.status === "failed" ? h("span", {class: "chip bad", title: e.error}, "failed") : e.status, e.status === "done" ? h("a", {href: "/api/exports/" + e.id + "/download"}, (e.size / 1024).toFixed(0) + " KB · " + e.sha256.slice(0, 8)) : ""]))))) ;
}

// ---------------------------------------------------------------- administration
async function viewAdmin(tab) {
  if (!can("admin")) throw new Error("Administrator access required.");
  tab = tab || "users";
  const tabs = [["users", "Users & roles"], ["settings", "Settings"], ["backup", "Backup & restore"], ["audit", "Audit log"]];
  const bar = h("div", {class: "tabs"}, tabs.map(([k, l]) => h("a", {class: "tab" + (k === tab ? " on" : ""), href: "#/admin/" + k}, l)));
  let body;
  if (tab === "users") {
    const r = await GET("/api/users"), u = h("input", {type: "text"}), n = h("input", {type: "text"}), pw = h("input", {type: "password"}), role = h("select", null, S.cfg.roles.map((x) => h("option", null, x))), dp = h("select", null, h("option", {value: ""}, "All departments"), S.tree.map((d) => h("option", {value: d.id}, d.name)));
    body = h("div", null, table(["User", "Name", "Role", "Dept scope", "Active", ""], r.users.map((x) => [x.username, x.display_name, h("select", {style: "width:auto", onchange: (e) => guard(async () => { await PUT("/api/users/" + x.id, {role: e.target.value}); toast("Role updated"); })}, S.cfg.roles.map((rr) => h("option", {selected: rr === x.role}, rr))), x.department || "all", x.active ? "yes" : "no",
      h("span", {class: "row"}, h("button", {class: "btn sm", onclick: () => guard(async () => { await PUT("/api/users/" + x.id, {active: !x.active}); route(); })}, x.active ? "Deactivate" : "Activate"),
        h("button", {class: "btn sm", onclick: async () => { const p = await promptBox("Reset password", "New temporary password (min 8)"); if (p) guard(async () => { await PUT("/api/users/" + x.id, {password: p}); toast("Password reset (user must change it)"); }); }}, "Reset password"))])),
      h("div", {class: "card", style: "margin-top:14px"}, h("h3", null, "Add user"), h("div", {class: "fields"}, [["Username", u], ["Display name", n], ["Temporary password", pw], ["Role", role], ["Department scope", dp]].map(([l, e]) => h("div", null, h("label", null, l), e))),
        h("button", {class: "btn pri", style: "margin-top:10px", onclick: () => guard(async () => { await POST("/api/users", {username: u.value, display_name: n.value, password: pw.value, role: role.value, department_id: dp.value ? +dp.value : null}); toast("User created"); route(); })}, "Create user")),
      h("div", {class: "card"}, h("h3", null, "Role permissions"), table(["Role", "Can"], [["admin", "Everything"], ["controller", "Import, accept imports, edit, review, publish approved revisions, manage findings, view all"], ["dept_owner", "Edit/submit/review within own department, manage findings, relationships"],
        ["editor", "Edit drafts and diagrams (own department if scoped), submit for review"], ["reviewer", "Review and comment (cannot review own changes)"], ["approver", "Approve / reject pending revisions (separation of duties enforced)"], ["viewer", "Read published content only"]])));
  } else if (tab === "settings") {
    const s = await GET("/api/settings"), f = {org_name: h("input", {type: "text", value: s.org_name}), export_footer: h("input", {type: "text", value: s.export_footer}), classification: h("input", {type: "text", value: s.classification || "Internal"}), region_label: h("input", {type: "text", value: s.region_label || "Region MEA"}), default_review_months: h("input", {type: "number", value: s.default_review_months}),
      allow_self_approval: h("select", null, h("option", {value: "0", selected: s.allow_self_approval !== "1"}, "No – enforce separation of duties (recommended)"), h("option", {value: "1", selected: s.allow_self_approval === "1"}, "Yes – single-user / pilot mode"))};
    body = h("div", {class: "card"}, h("div", {class: "fields"}, [["Organisation name", f.org_name], ["Export footer text", f.export_footer], ["Classification label (cover, footers)", f.classification], ["Region label (footers)", f.region_label], ["Default review frequency (months)", f.default_review_months], ["Author may review/approve own revision", f.allow_self_approval]].map(([l, e]) => h("div", null, h("label", null, l), e))),
      h("button", {class: "btn pri", style: "margin-top:10px", onclick: () => guard(async () => { const b = {}; Object.entries(f).forEach(([k, e]) => b[k] = e.value); await PUT("/api/settings", b); toast("Saved"); })}, "Save settings"),
      h("p", {class: "muted"}, "draw.io editor: " + (S.cfg.drawio_local ? "self-hosted copy at /drawio/ (offline)" : "online host " + S.cfg.drawio_url + " – run fetch_drawio.py for a local copy.")));
  } else if (tab === "backup") {
    const fi = h("input", {type: "file", accept: ".zip"});
    body = h("div", {class: "grid g2"}, h("div", {class: "card"}, h("h3", null, "Backup"), h("p", {class: "muted"}, "Consistent ZIP of database, imported source documents and assets."), h("button", {class: "btn pri", onclick: () => guard(async () => { const r = await api("POST", "/api/backup", {}, {raw: true}); const b = await r.blob(); const a = h("a", {href: URL.createObjectURL(b), download: "mea_hub_backup.zip"}); document.body.append(a); a.click(); a.remove(); toast("Backup downloaded"); })}, "Create & download backup")),
      h("div", {class: "card"}, h("h3", null, "Restore"), h("div", {class: "banner bad"}, "Restoring REPLACES all current data and signs everyone out."), fi, h("button", {class: "btn bad", style: "margin-top:8px", onclick: () => guard(async () => { if (!fi.files[0]) throw new Error("Choose a backup ZIP first."); if (!(await confirmBox("Replace ALL current data with this backup?", "Restore"))) return; const buf = await readFile(fi.files[0]); await api("POST", "/api/restore", new Blob([buf])); toast("Restored – signing out"); S.user = null; render(); })}, "Restore from backup")));
  } else { const r = await GET("/api/audit"); body = table(["When", "User", "Action", "Entity", "Detail"], r.rows.map((x) => [fmtDate(x.ts), x.username, x.action, (x.entity || "") + " " + (x.entity_id || ""), x.detail])); }
  return h("div", {class: "page"}, h("h1", null, "Administration"), bar, body);
}
boot();
