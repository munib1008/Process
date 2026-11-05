"use strict";
/* Flow Studio: draw.io embed mode (JSON postMessage protocol).
   - only messages from the draw.io iframe window AND its configured origin are accepted
   - exclusive edit lease + optimistic revision check (409 => reload, nothing overwritten)
   - every save stores the editable XML plus a PNG preview exported by draw.io itself          */
async function openFlowStudio(diagramId, root, exitTo) {
  clear(root);
  const info = await GET("/api/diagrams/" + diagramId);
  let baseVer = info.latest.ver_no, latestDv = info.latest.id, dirty = false, busy = false, pending = null, lost = false, ready = false, exportWaiters = [];
  const title = info.process ? info.process.process_id + " – " + info.process.name : info.diagram.title;
  const status = h("span", {class: "muted"}, "Opening editor…");
  const banner = h("div");
  const nodesBox = h("div"), revBox = h("div");

  let lock = null, readOnly = false;
  try { lock = await POST("/api/diagrams/" + diagramId + "/lock"); } catch (e) { readOnly = true; banner.append(h("div", {class: "banner bad"}, e.message + " The diagram is opened read-only.")); }
  const renew = setInterval(async () => { if (readOnly) return; try { await POST("/api/diagrams/" + diagramId + "/lock"); } catch (e) { lost = true; banner.replaceChildren(h("div", {class: "banner bad"}, "Edit lease lost: " + e.message)); } }, 120000);

  const base = new URL(S.cfg.drawio_url, location.href);
  const origin = base.origin;
  const params = new URLSearchParams({embed: "1", proto: "json", spin: "1", saveAndExit: "0", noSaveBtn: "0", noExitBtn: "1", ui: "kennedy", libraries: "1"});
  if (S.cfg.drawio_local) params.set("offline", "1");
  const iframe = h("iframe", {src: base.href.split("?")[0] + "?" + params, title: "draw.io editor", allow: "clipboard-write"});
  const post = (o) => iframe.contentWindow && iframe.contentWindow.postMessage(JSON.stringify(o), origin);

  function requestPng() {
    return new Promise((res) => {
      const t = setTimeout(() => { exportWaiters = exportWaiters.filter((w) => w !== done); res(null); }, 12000);
      const done = (data) => { clearTimeout(t); res(data); };
      exportWaiters.push(done);
      post({action: "export", format: "png", scale: 1.5, border: 10, background: "#ffffff"});
    });
  }
  async function persist(xml) {
    if (readOnly || lost) return;
    if (busy) { pending = xml; return; }
    busy = true; status.textContent = "Saving…";
    try {
      const png = await requestPng();
      const r = await POST("/api/diagrams/" + diagramId + "/save", {xml, png, base_ver: baseVer});
      baseVer = r.ver_no; dirty = false;
      status.textContent = (r.changed ? "Saved as revision " : "No change – revision ") + r.ver_no + " at " + new Date().toLocaleTimeString();
      post({action: "status", message: "Saved (revision " + r.ver_no + ")", modified: false});
      await refreshSide();
    } catch (e) {
      status.textContent = "Save failed";
      banner.replaceChildren(h("div", {class: "banner bad"}, e.message + (e.status === 409 ? " Reload the page to continue from the latest revision." : "")));
      if (e.status === 409) lost = true;
    } finally { busy = false; if (pending) { const x = pending; pending = null; persist(x); } }
  }
  function onMessage(ev) {
    if (ev.origin !== origin || ev.source !== iframe.contentWindow) return;           // never trust arbitrary postMessage
    let msg; try { msg = typeof ev.data === "string" ? JSON.parse(ev.data) : null; } catch (e) { return; }
    if (!msg || typeof msg.event !== "string") return;
    if (msg.event === "init") { post({action: "load", xml: info.latest.xml, autosave: readOnly ? 0 : 1, title}); ready = true; status.textContent = readOnly ? "Read-only" : "Loaded revision " + baseVer; }
    else if (msg.event === "autosave" && msg.xml) { dirty = true; status.textContent = "Unsaved changes…"; clearTimeout(onMessage.t); onMessage.t = setTimeout(() => persist(msg.xml), 2500); }
    else if (msg.event === "save" && msg.xml) { clearTimeout(onMessage.t); persist(msg.xml); }
    else if (msg.event === "export") { const w = exportWaiters.shift(); if (w) w(msg.data || null); }
    else if (msg.event === "load" && info.latest.preview_approx && !readOnly) {      // swap the server's approximate preview for draw.io's own render
      setTimeout(async () => { const png = await requestPng(); if (png) { try { await POST("/api/diagram-versions/" + info.latest.id + "/preview", {png}); } catch (e) { /* non-fatal */ } } }, 1500);
    }
    else if (msg.event === "exit") { leave(); }
  }
  window.addEventListener("message", onMessage);
  window.onbeforeunload = () => (dirty ? "Unsaved diagram changes." : undefined);

  async function leave() {
    if (dirty && !(await confirmBox("There are unsaved changes in the diagram. Leave anyway?", "Leave without saving"))) return;
    cleanup(); try { await POST("/api/diagrams/" + diagramId + "/unlock"); } catch (e) {}
    location.hash = exitTo || "#/flow";
  }
  function cleanup() { clearInterval(renew); window.removeEventListener("message", onMessage); window.onbeforeunload = null; root.dataset.flowCleanup = ""; }
  root.__cleanup = () => { cleanup(); if (!readOnly) navigator.sendBeacon && 0; fetch("/api/diagrams/" + diagramId + "/unlock", {method: "POST", headers: {"X-CSRF-Token": S.csrf, "Content-Type": "application/json"}, body: "{}", credentials: "same-origin", keepalive: true}); };

  async function refreshSide() {
    const d = await GET("/api/diagrams/" + diagramId);
    latestDv = d.latest.id;
    clear(nodesBox).append(h("h3", null, "Business metadata for shapes"),
      h("p", {class: "muted"}, "Stored separately from geometry, keyed by stable shape IDs. Link a shape to a process to make it navigable."),
      d.nodes.length ? d.nodes.map((n) => nodeForm(n)) : h("p", {class: "muted"}, "Save the diagram once to list its shapes."));
    clear(revBox).append(h("h3", null, "Revisions"), table(["Rev", "By", "When", ""], d.versions.map((v) => [
      "#" + v.ver_no + (v.validation === "requires_validation" ? " ⚑" : ""), v.author, fmtDate(v.created_at),
      h("a", {href: "/api/diagram-versions/" + v.id + "/xml"}, ".drawio")])));
  }
  function nodeForm(n) {
    if (!n.label && !Object.keys(n.meta).length) return null;
    const keys = S.cfg.node_meta_keys, inputs = {};
    const det = h("details", {class: "card", style: "padding:8px 10px;margin-bottom:6px"}, h("summary", null, (n.label || n.node_id).slice(0, 38), Object.keys(n.meta).length ? " ●" : ""),
      keys.map((k) => { inputs[k] = h("input", {type: "text", value: n.meta[k] || "", placeholder: k === "process_ref" ? "e.g. WL-M-IB-01" : ""}); return h("div", null, h("label", null, k.replace("_", " ")), inputs[k]); }),
      h("button", {class: "btn sm", style: "margin-top:6px", disabled: readOnly, onclick: () => guard(async () => {
        const meta = {}; keys.forEach((k) => meta[k] = inputs[k].value);
        await PUT("/api/diagram-versions/" + latestDv + "/nodes/" + encodeURIComponent(n.node_id), meta); toast("Metadata saved");
      })}, "Save metadata"));
    return det;
  }
  const side = h("div", {class: "side"}, h("div", {class: "card"}, status, banner), revBox, nodesBox);
  root.append(h("div", {class: "page"}, h("div", {class: "row spread"}, h("div", null, h("h1", null, "Flow Studio"), h("div", {class: "sub"}, title + " · " + info.diagram.code)),
      h("div", {class: "row"}, h("button", {class: "btn", onclick: () => api("GET", "/api/diagram-versions/" + latestDv + "/xml", undefined, {raw: true}).then(() => download("/api/diagram-versions/" + latestDv + "/xml"))}, "Download .drawio"),
        h("button", {class: "btn", onclick: () => download("/api/diagram-versions/" + latestDv + "/svg")}, "Export SVG"),
        h("button", {class: "btn pri", onclick: leave}, "Close editor"))),
    S.cfg.drawio_local ? null : h("div", {class: "banner warn"}, "Using the online draw.io host (", origin, "). Diagram content is exchanged with that host. For fully local use run fetch_drawio.py (see Admin Guide)."),
    h("div", {class: "flowpage"}, iframe, side)));
  await refreshSide();
}
