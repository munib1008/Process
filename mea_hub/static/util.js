"use strict";
/* Tiny DOM + API helpers. Text is always inserted via textContent (XSS-safe);
   rich text comes only from the server-sanitised `html` fields via setHTML. */
const S = {user: null, csrf: null, cfg: null};
/* Make append()/replaceChildren() accept arrays and skip null/false, like h() does. */
(function () {
  const clean = (k) => k.flat(Infinity).filter((x) => x !== null && x !== undefined && x !== false);
  const ap = Element.prototype.append, rc = Element.prototype.replaceChildren;
  Element.prototype.append = function (...k) { return ap.apply(this, clean(k)); };
  Element.prototype.replaceChildren = function (...k) { return rc.apply(this, clean(k)); };
})();

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked" || k === "disabled" || k === "selected" || k === "open") el[k] = !!v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat(Infinity)) {
    if (k === null || k === undefined || k === false) continue;
    el.append(k.nodeType ? k : document.createTextNode(String(k)));
  }
  return el;
}
const $ = (s, r) => (r || document).querySelector(s);
function setHTML(el, html) { el.innerHTML = html || ""; return el; }   // html is sanitised server-side
function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }

async function api(method, url, body, opts) {
  opts = opts || {};
  const headers = {};
  if (S.csrf) headers["X-CSRF-Token"] = S.csrf;
  let payload;
  if (body instanceof Blob || body instanceof ArrayBuffer) payload = body;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  Object.assign(headers, opts.headers || {});
  const r = await fetch(url, {method, headers, body: payload, credentials: "same-origin"});
  if (opts.raw) { if (!r.ok) throw await asError(r); return r; }
  let data = {};
  try { data = await r.json(); } catch (e) { /* empty */ }
  if (!r.ok) {
    if (r.status === 401 && S.user) { S.user = null; render(); }
    if (data.must_change) { S.user && (S.user.must_change = true); }
    const err = new Error(data.error || ("HTTP " + r.status)); err.status = r.status; err.data = data; throw err;
  }
  return data;
}
async function asError(r) { let d = {}; try { d = await r.json(); } catch (e) {} const e = new Error(d.error || ("HTTP " + r.status)); e.status = r.status; return e; }
const GET = (u) => api("GET", u), POST = (u, b) => api("POST", u, b || {}), PUT = (u, b) => api("PUT", u, b || {}), DEL = (u) => api("DELETE", u);

function toast(msg, bad) {
  const t = h("div", {class: "toast" + (bad ? " bad" : "")}, msg);
  $("#toasts").append(t);
  setTimeout(() => t.remove(), bad ? 7000 : 3500);
}
async function guard(fn) { try { return await fn(); } catch (e) { toast(e.message, true); return undefined; } }

function modal(title, body, opts) {
  opts = opts || {};
  const close = () => bg.remove();
  const bg = h("div", {class: "modalbg", onclick: (e) => { if (e.target === bg) close(); }},
    h("div", {class: "modal" + (opts.wide ? " wide" : ""), role: "dialog", "aria-label": title},
      h("div", {class: "row spread"}, h("h2", {style: "margin-top:0"}, title), h("button", {class: "btn sm", onclick: close, "aria-label": "Close"}, "✕")),
      body));
  document.body.append(bg);
  return {close, el: bg};
}
function confirmBox(msg, label) {
  return new Promise((res) => {
    const m = modal("Please confirm", h("div", null, h("p", null, msg),
      h("div", {class: "row"}, h("button", {class: "btn pri", onclick: () => { m.close(); res(true); }}, label || "Confirm"),
        h("button", {class: "btn", onclick: () => { m.close(); res(false); }}, "Cancel"))));
  });
}
function promptBox(title, label, opts) {
  opts = opts || {};
  return new Promise((res) => {
    const inp = opts.multiline ? h("textarea", {value: opts.value || ""}) : h("input", {type: "text", value: opts.value || ""});
    const m = modal(title, h("div", null, h("label", null, label), inp,
      h("div", {class: "row", style: "margin-top:12px"},
        h("button", {class: "btn pri", onclick: () => { if (opts.required && !inp.value.trim()) { toast("This field is required", true); return; } m.close(); res(inp.value); }}, opts.ok || "OK"),
        h("button", {class: "btn", onclick: () => { m.close(); res(null); }}, "Cancel"))));
    inp.focus();
  });
}

const fmtDate = (s) => s ? s.replace("T", " ").replace("Z", "") : "";
const chipS = (st, label) => h("span", {class: "chip s-" + st}, label || (S.cfg && S.cfg.statuses[st]) || st);
const can = (...roles) => S.user && roles.includes(S.user.role);
function download(url) { const a = h("a", {href: url}); document.body.append(a); a.click(); a.remove(); }
function readFile(file, as) { return new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; as === "text" ? r.readAsText(file) : r.readAsArrayBuffer(file); }); }
function table(headers, rows, opts) {
  opts = opts || {};
  return h("table", {class: "t"}, h("thead", null, h("tr", null, headers.map((x) => h("th", null, x)))),
    h("tbody", null, rows.map((r) => { const cells = r.cells || r; return h("tr", {class: r.click ? "click" : "", onclick: r.click}, cells.map((c) => h("td", null, c))); })));
}
