"use strict";
/* Settings page of the Teams channel tab. Teams shows it when the tab is added or its settings are opened and
   stores the address returned here. Nothing is sent anywhere else. */
(function () {
  const $ = (id) => document.getElementById(id), state = $("state");
  const clean = (s, rx) => (s || "").trim().toUpperCase().replace(rx, "");
  function target() {
    const v = (document.querySelector("input[name=start]:checked") || {}).value || "#/dashboard";
    if (v === "dept") { const c = clean($("dept").value, /[^A-Z0-9_-]/g); return c ? "#/departments/" + encodeURIComponent(c) : null; }
    if (v === "proc") { const p = clean($("proc").value, /[^A-Z0-9._-]/g); return p ? "#/process/" + encodeURIComponent(p) : null; }
    return v;
  }
  function refresh() {
    const t = target(), ok = !!t && $("name").value.trim().length > 0;
    state.textContent = ok ? "Opens: " + location.origin + "/" + t : "Enter the department code or process ID.";
    try { microsoftTeams.pages.config.setValidityState(ok); } catch (e) { /* not inside Teams */ }
  }
  document.querySelectorAll("input").forEach((el) => el.addEventListener("input", refresh));
  $("dept").addEventListener("focus", () => { document.querySelector("input[value=dept]").checked = true; refresh(); });
  $("proc").addEventListener("focus", () => { document.querySelector("input[value=proc]").checked = true; refresh(); });
  if (!window.microsoftTeams) { state.textContent = "Teams library not loaded."; return; }
  microsoftTeams.app.initialize().then(() => {
    microsoftTeams.pages.config.registerOnSaveHandler((ev) => {
      const t = target(), url = location.origin + "/" + t;
      microsoftTeams.pages.config.setConfig({contentUrl: url, websiteUrl: url, entityId: "mea-process-hub:" + t, suggestedDisplayName: $("name").value.trim().slice(0, 30)})
        .then(() => ev.notifySuccess(), (e) => ev.notifyFailure(String(e && e.message || e)));
    });
    refresh();
  }, () => { state.textContent = "This page is the settings page of the Teams tab. Open MEA Process Hub at " + location.origin + "/"; });
})();
