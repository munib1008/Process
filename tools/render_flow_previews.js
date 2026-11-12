/* Render every source_documents/flows/*.drawio to a PNG with the real draw.io engine (headless Chromium).
   The PNG sits next to the flow file and is used by the importer as the authoritative preview.

   Usage:  node tools/render_flow_previews.js [baseUrl] [flowsDir] [file1.drawio,file2.drawio]
   A file with several pages gets one picture per page (<file>.png, <file>.p2.png, ...).
   Needs:  a running MEA Process Hub with the local draw.io copy (default http://127.0.0.1:8765) and Playwright. */
const {chromium} = require('playwright');
const fs = require('fs');
const path = require('path');

const base = process.argv[2] || 'http://127.0.0.1:8765';
const dir = process.argv[3] || path.join(__dirname, '..', 'source_documents', 'flows');

(async () => {
  const only = process.argv[4] ? process.argv[4].split(',') : null;      // optional: comma-separated file names
  const files = fs.readdirSync(dir).filter((f) => f.endsWith('.drawio') && (!only || only.includes(f))).sort();
  const browser = await chromium.launch();
  const page = await (await browser.newContext({viewport: {width: 1600, height: 1000}})).newPage();
  // same arrangement as the app: draw.io runs in an iframe and talks to the parent page via postMessage
  await page.goto(base + '/drawio/clear.html').catch(() => {});
  await page.setContent('<html><body style="margin:0"><iframe id="f" style="width:1600px;height:1000px;border:0"></iframe></body></html>');
  await page.evaluate((src) => {
    window.__ev = [];
    window.addEventListener('message', (e) => {
      try { const m = JSON.parse(e.data); if (m && m.event) window.__ev.push(m); } catch (err) { /* not ours */ }
    });
    document.getElementById('f').src = src;
  }, base + '/drawio/index.html?embed=1&proto=json&spin=0&offline=1&libraries=0');
  await page.waitForFunction(() => window.__ev.some((m) => m.event === 'init'), null, {timeout: 90000});
  let ok = 0, failed = [];
  const jobs = [];                                                        // one picture per page: <file>.png, <file>.p2.png, ...
  for (const f of files) {
    const xml = fs.readFileSync(path.join(dir, f), 'utf8');
    const pages = xml.match(/<diagram[\s\S]*?<\/diagram>/g) || [];
    if (pages.length < 2) jobs.push([f.replace(/\.drawio$/, '.png'), xml]);
    else pages.forEach((p, i) => jobs.push([f.replace(/\.drawio$/, i ? '.p' + (i + 1) + '.png' : '.png'), '<mxfile>' + p + '</mxfile>']));
  }
  for (const [out, xml] of jobs) {
    const f = out;
    try {
      const data = await page.evaluate(async (xml) => {
        const wait = (name, ms) => new Promise((res, rej) => {
          const t0 = Date.now();
          const tick = () => {
            const i = window.__ev.findIndex((m) => m.event === name);
            if (i >= 0) { const m = window.__ev.splice(i, 1)[0]; return res(m); }
            if (Date.now() - t0 > ms) return rej(new Error('timeout waiting for ' + name));
            setTimeout(tick, 50);
          };
          tick();
        });
        window.__ev.length = 0;
        const fr = document.getElementById('f').contentWindow;
        fr.postMessage(JSON.stringify({action: 'load', xml, autosave: 0}), '*');
        await wait('load', 30000);
        fr.postMessage(JSON.stringify({action: 'export', format: 'png', scale: 1.5, border: 10, background: '#ffffff'}), '*');
        const m = await wait('export', 60000);
        return m.data;
      }, xml);
      const b64 = String(data).split(',')[1];
      const buf = Buffer.from(b64, 'base64');
      if (buf.slice(0, 4).toString('hex') !== '89504e47') throw new Error('not a PNG');
      fs.writeFileSync(path.join(dir, out), buf);
      ok++;
    } catch (e) { failed.push(f + ': ' + e.message); }
  }
  console.log(`${ok} of ${jobs.length} previews rendered`);
  failed.forEach((x) => console.log('FAILED', x));
  await browser.close();
})();
