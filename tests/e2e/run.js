/* Browser journey and accessibility check for MEA Process Hub.

   Starts its own server on a throw-away data folder (first start imports the delivered documents, demo users are
   created), drives the real pages in headless Chromium the way people use them, and checks the main pages with
   axe-core (WCAG 2.1 A and AA rules).

   Usage:   node tests/e2e/run.js            (needs: python on the PATH, the npm packages playwright and axe-core)
   Options: PYTHON=python3  E2E_KEEP=1 (keep the data folder)  E2E_SHOTS=dir (screenshots of every step)
   Exit code 1 when a step fails, a page logs a script error, or axe reports a serious or critical problem. */
const {chromium, devices} = require('playwright');
const {spawn} = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const net = require('net');

const ROOT = path.join(__dirname, '..', '..');
const PY = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const PW = 'ChangeMe!123';
const results = [];
let failed = 0;

const freePort = () => new Promise((res) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function step(name, fn) {
  const t0 = Date.now();
  try { await fn(); results.push(['ok', name, Date.now() - t0]); console.log('  ok   ' + name); }
  catch (e) { failed++; results.push(['FAIL', name, Date.now() - t0, String(e.message || e).split('\n')[0]]); console.log('  FAIL ' + name + ' – ' + String(e.message || e).split('\n')[0]); }
}
const expect = (cond, msg) => { if (!cond) throw new Error(msg); };

(async () => {
  const data = fs.mkdtempSync(path.join(os.tmpdir(), 'mea_e2e_'));
  const port = await freePort(), base = 'http://127.0.0.1:' + port;
  const log = fs.openSync(path.join(data, 'server.log'), 'w');
  const srv = spawn(PY, [path.join(ROOT, 'run.py'), '--port', String(port), '--no-browser', '--demo-users'], {cwd: ROOT, env: Object.assign({}, process.env, {MEA_HUB_DATA: data}), stdio: ['ignore', log, log]});
  let browser;
  const scriptErrors = [];
  try {
    console.log('Starting the server (first start imports the delivered documents) …');
    let up = false;
    for (let i = 0; i < 600 && !up; i++) { await sleep(500); if (srv.exitCode !== null) throw new Error('server stopped, see ' + path.join(data, 'server.log')); try { up = (await fetch(base + '/api/health')).ok; } catch (e) { /* not yet */ } }
    if (!up) throw new Error('server did not start');
    const adminPw = fs.readFileSync(path.join(data, 'FIRST_RUN_ADMIN_PASSWORD.txt'), 'utf8').split('password: ')[1].split(/\s/)[0];
    browser = await chromium.launch();
    const axeSource = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');

    const open = async (user, password, opts) => {
      const ctx = await browser.newContext(opts || {viewport: {width: 1440, height: 950}});
      const p = await ctx.newPage();
      p.on('pageerror', (e) => scriptErrors.push(user + ': ' + e.message));
      p.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) scriptErrors.push(user + ': ' + m.text()); });
      await p.goto(base + '/');
      await p.fill('input[type=text]', user);
      await p.fill('input[type=password]:not([style*="none"])', password || PW);
      await p.click('button:has-text("Sign in")');
      await p.waitForSelector('.nav, .login .banner.warn', {timeout: 20000});
      return p;
    };
    const go = async (p, hash, sel) => { await p.goto(base + '/' + hash); await p.waitForSelector(sel || '#main h1', {timeout: 20000}); await p.waitForTimeout(400); };
    const shot = async (p, name) => { if (process.env.E2E_SHOTS) await p.screenshot({path: path.join(process.env.E2E_SHOTS, name + '.png')}); };
    const axe = async (p, name) => {
      await p.evaluate(axeSource + '; void 0');
      const r = await p.evaluate(() => window.axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']}, resultTypes: ['violations']}));
      const bad = r.violations.filter((v) => ['serious', 'critical'].includes(v.impact));
      r.violations.forEach((v) => console.log('         axe ' + name + ': [' + v.impact + '] ' + v.id + ' – ' + v.help + ' (' + v.nodes.length + ' element' + (v.nodes.length > 1 ? 's' : '') + (v.nodes[0] ? ', e.g. ' + v.nodes[0].target.join(' ') : '') + ')'));
      expect(!bad.length, bad.length + ' serious or critical accessibility problem(s): ' + bad.map((v) => v.id).join(', '));
    };

    let admin, editor, reviewer, approver, controller, viewer;
    const pid = 'E2E-S-TS-01';

    await step('sign-in page: wrong password is refused, page is accessible', async () => {
      const ctx = await browser.newContext({viewport: {width: 1440, height: 950}}); const p = await ctx.newPage();
      await p.goto(base + '/'); await p.waitForSelector('button:has-text("Sign in")');
      await axe(p, 'sign-in');
      await p.fill('input[type=text]', 'demo_editor'); await p.fill('input[type=password]:not([style*="none"])', 'not the password'); await p.click('button:has-text("Sign in")');
      await p.waitForSelector('text=/Invalid username or password/i', {timeout: 8000});
      await ctx.close();
    });
    await step('administrator must change the one-time password, then reaches the dashboard', async () => {
      admin = await open('admin', adminPw);
      await admin.waitForSelector('text=You must set a new password');
      const inputs = admin.locator('input[type=password]');
      await inputs.nth(0).fill(adminPw); await inputs.nth(1).fill('E2e#Admin2026!');
      await admin.click('button:has-text("Save")');
      await admin.waitForSelector('.nav'); await admin.waitForSelector('h1:has-text("Enterprise overview")');
      await shot(admin, '01_dashboard'); await axe(admin, 'dashboard');
    });
    await step('landscape: the value stream opens the process behind a shape', async () => {
      await go(admin, '#/landscape', '.lsmap a.hot');
      expect(await admin.locator('.lsmap a.hot').count() >= 5, 'fewer than 5 clickable shapes');
      await shot(admin, '02_landscape'); await axe(admin, 'landscape');
      await admin.locator('.lsmap a.hot').first().click();
      await admin.waitForFunction(() => location.hash.startsWith('#/process/'));
      await admin.waitForSelector('.tabs'); await axe(admin, 'process page');
    });
    await step('editor creates a process with a swimlane flow from text', async () => {
      editor = await open('demo_editor');
      const r = await editor.evaluate(async (id) => {
        const a = await POST('/api/process', {name: 'Browser test process', department: 'LOG', process_id: id, objective: 'Created by the browser test'});
        const f = await POST('/api/flows/build', {process_id: id, layout: 'lanes', steps: 'Logistics: Create delivery (VL01N)\nParallel: Warehouse: Pick goods\nParallel: Logistics: Book transport\nWarehouse: Post goods issue'});
        return [a.process_id, f.steps, f.warnings.length, f.checks.length];
      }, pid);
      expect(r[0] === pid && r[1] === 4 && r[2] === 0 && r[3] === 0, 'flow not built as expected: ' + JSON.stringify(r));
      await go(editor, '#/process/' + pid, 'text=Flow check');
      await editor.click('.tab:has-text("Activities")'); await editor.waitForSelector('text=Post goods issue');
      await shot(editor, '03_process_draft');
    });
    await step('editor submits, reviewer and approver sign, controller publishes', async () => {
      await editor.click('button:has-text("Edit draft")'); await editor.waitForSelector('button:has-text("Submit for review")');
      await editor.click('button:has-text("Submit for review")');
      await editor.fill('.modal textarea', 'First issue from the browser test'); await editor.click('.modal button:has-text("Submit")');
      await editor.click('.modal button:has-text("Cancel")');                     // minor change
      await editor.waitForSelector('text=Submitted for review', {timeout: 10000});
      reviewer = await open('demo_reviewer'); await go(reviewer, '#/process/' + pid, 'button:has-text("Approve review")');
      await reviewer.click('button:has-text("Approve review")'); await reviewer.waitForSelector('.chip:has-text("Pending")', {timeout: 10000});
      approver = await open('demo_approver'); await go(approver, '#/process/' + pid, 'button:has-text("Approve")');
      await approver.click('button.pri:has-text("Approve")'); await approver.waitForSelector('text=Approved', {timeout: 10000});
      controller = await open('demo_controller'); await go(controller, '#/process/' + pid, 'button:has-text("Publish")');
      await controller.click('button:has-text("Publish")'); await controller.waitForSelector('.chip:has-text("Published")', {timeout: 10000});
      await controller.click('.tab:has-text("History")'); await controller.waitForSelector('h3:has-text("Signed decisions")');
      expect(await controller.locator('.chip.ok:has-text("content unchanged")').count() === 3, 'three signed decisions expected');
      await shot(controller, '04_signed'); await axe(controller, 'history with signatures');
    });
    await step('reader sees the published version and suggests a change; the controller gets the task', async () => {
      viewer = await open('demo_viewer'); await go(viewer, '#/process/' + pid, 'button:has-text("Suggest a change")');
      expect(await viewer.locator('button:has-text("Edit")').count() === 0, 'a reader must not get edit buttons');
      await viewer.click('button:has-text("Suggest a change")'); await viewer.waitForSelector('.modal textarea');
      await viewer.selectOption('.modal select', {index: 1});
      await viewer.fill('.modal textarea', 'The transport is now booked by the freight forwarder.');
      await viewer.click('.modal button:has-text("Send")'); await viewer.waitForSelector('text=Sent to the process owner');
      await go(viewer, '#/dashboard', 'h3:has-text("My change requests")');
      await go(controller, '#/dashboard', '.chip.warn:has-text("Change request")');
    });
    await step('KPI value, reading statistics, periodic review list', async () => {
      await editor.evaluate(async (id) => { await PUT('/api/process/' + id + '/draft', {content: {kpis: [{name: 'On-time delivery', definition: 'Deliveries on the confirmed date', target: '≥ 95 %'}]}}); }, pid);
      await go(editor, '#/governance/kpis', 'button:has-text("Enter value")');
      await editor.locator('tr:has-text("' + pid + '") button:has-text("Enter value")').click();
      await editor.fill('.modal input[aria-label="Value"]', '96.5'); await editor.click('.modal button:has-text("Save")');
      await editor.waitForSelector('tr:has-text("' + pid + '") .chip.ok:has-text("target met")', {timeout: 10000});
      await axe(editor, 'KPI register');
      await go(controller, '#/reports/usage', 'text=Readers 30 days');
      expect(await controller.locator('tr:has-text("' + pid + '")').count() === 1, 'the new process is missing in the reading statistics');
      await go(controller, '#/governance/reviews', 'text=' + pid);
      await go(controller, '#/library', 'table.t'); await axe(controller, 'library');
    });
    await step('administration: restore drill passes, signature register is intact', async () => {
      await go(admin, '#/admin/backup', 'button:has-text("Run restore drill now")');
      await admin.click('button:has-text("Run restore drill now")');
      await admin.waitForSelector('.banner.ok:has-text("Last drill passed")', {timeout: 120000});
      await shot(admin, '05_drill'); await axe(admin, 'administration');
      await go(admin, '#/admin/audit', 'button:has-text("Check the register now")');
      await admin.click('button:has-text("Check the register now")');
      await admin.waitForSelector('.banner.ok:has-text("complete and unaltered")', {timeout: 20000});
    });
    await step('phone: pages fit the screen, the process list folds away', async () => {
      const phone = await open('demo_viewer', PW, Object.assign({}, devices['iPhone 13']));
      for (const hash of ['#/dashboard', '#/landscape', '#/process/' + pid, '#/library']) {
        await go(phone, hash, hash.startsWith('#/process') ? '.tabs' : '#main h1');
        const [sw, cw] = await phone.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
        expect(sw <= cw + 1, hash + ' is wider than the screen (' + sw + ' > ' + cw + ')');
      }
      await go(phone, '#/process/' + pid, '.tree.shut');
      await shot(phone, '06_phone'); await axe(phone, 'process page on a phone');
    });
    await step('no page logged a script error', async () => { expect(!scriptErrors.length, scriptErrors.slice(0, 3).join(' | ')); });
  } catch (e) {
    failed++; console.log('  FAIL setup – ' + (e.message || e));
  } finally {
    if (browser) await browser.close();
    srv.kill();
    fs.closeSync(log);
    if (failed) { try { console.log('---- server log (end) ----\n' + fs.readFileSync(path.join(data, 'server.log'), 'utf8').slice(-1500)); } catch (e) { /* ignore */ } }
    if (!process.env.E2E_KEEP) fs.rmSync(data, {recursive: true, force: true});
  }
  console.log('\n' + results.filter((r) => r[0] === 'ok').length + ' of ' + results.length + ' steps passed.');
  process.exit(failed ? 1 : 0);
})();
