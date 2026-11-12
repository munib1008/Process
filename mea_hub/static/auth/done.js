"use strict";
/* Last page of a sign-in window: hands the one-time code to the page that opened the window (same site only) and closes.
   The code is in the address fragment, so it is not sent to any server or written to a log. */
(function () {
  const m = /[#&]h=([A-Za-z0-9_-]+)/.exec(location.hash), msg = document.getElementById("msg");
  history.replaceState(null, "", location.pathname);
  if (m && window.opener && !window.opener.closed) {
    try { window.opener.postMessage({meaHandoff: m[1]}, location.origin); window.close(); return; } catch (e) { /* fall through */ }
  }
  msg.textContent = m ? "This window can be closed. If MEA Process Hub did not sign you in, open it in a full browser window." : "You can close this window.";
})();
