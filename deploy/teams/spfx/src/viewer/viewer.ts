/**
 * Reader for a published MEA Process Hub library (the "site" export of the tool).
 * It shows what is in handbook.json and the pictures next to it - nothing can be edited here.
 * The same file is compiled into the SharePoint web part and into viewer.js of the export.
 */

type Row = Record<string, string>;

interface IPicture { file: string; label: string; part: number; of: number }
interface ISection { title: string; html: string }
interface IRelation { type: string; id: string; name: string }
interface IProcess {
  id: string; name: string; kind: string; status: string; status_label: string; version: string;
  owner: string; reviewer: string; approved_by: string; published_at: string; category: string; countries: string;
  responsible: string[]; raci_draft: boolean; pictures: IPicture[]; flow_revision?: number;
  sections: ISection[]; relations: IRelation[];
  objective: string; scope: string; trigger: string; inputs: string; outputs: string; risks: string; evidence: string; forms: string; notes: string;
  activities: Row[]; raci: Row[]; sap: Row[]; kpis: Row[]; escalation: Row[];
}
interface IDepartment { code: string; name: string; processes: IProcess[] }
interface IBook {
  format: number; title: string; org: string; classification: string; region: string; generated_at: string; generated_by: string;
  snapshot: string; count: number; unapproved: number; legend: { role: string; color: string }[]; departments: IDepartment[];
}
type Child = Node | string | undefined | false;

const CSS: string = `
.mph{--ink:#1c2430;--mute:#5b6676;--line:#d9dee6;--paper:#fff;--soft:#f4f6f9;--brand:#003594;--bad:#b3261e;--badsoft:#fbe9e7;--ok:#1e6b45;--oksoft:#e2f3ea;--warn:#8a5a00;--warnsoft:#fcf1d9;
  font:14px/1.5 "Segoe UI",system-ui,-apple-system,Arial,sans-serif;color:var(--ink);background:var(--paper);display:grid;grid-template-columns:minmax(240px,320px) minmax(0,1fr);min-height:480px;border:1px solid var(--line);box-sizing:border-box}
.mph *{box-sizing:border-box}
.mph-nav{border-right:1px solid var(--line);background:var(--soft);padding:14px 12px;display:flex;flex-direction:column;gap:10px;min-width:0;max-height:100vh;overflow:auto;position:sticky;top:0;align-self:start}
.mph-brand{font-weight:700;font-size:15px;color:var(--brand);cursor:pointer;background:none;border:0;padding:0;text-align:left}
.mph-search{width:100%;padding:7px 10px;border:1px solid var(--line);border-radius:4px;font:inherit;background:var(--paper);color:var(--ink)}
.mph-nav details{border-top:1px solid var(--line);padding-top:6px}
.mph-nav summary{cursor:pointer;font-weight:600;padding:3px 0}
.mph-nav summary span{color:var(--mute);font-weight:400;font-size:12px;margin-left:6px}
.mph-item{display:block;width:100%;text-align:left;background:none;border:0;padding:4px 6px 4px 14px;font:inherit;color:var(--ink);cursor:pointer;border-radius:3px}
.mph-item:hover,.mph-item:focus-visible{background:#e6ebf3;outline:none}
.mph-item.on{background:var(--brand);color:#fff}
.mph-item small{display:block;color:var(--mute);font-size:11px}
.mph-item.on small{color:#dbe4f5}
.mph-main{padding:18px 22px 28px;min-width:0}
.mph-kick{color:var(--bad);font-size:12px;margin:0}
.mph h2{font-size:22px;line-height:1.25;margin:2px 0 6px;color:var(--brand);font-weight:600}
.mph h3{font-size:15px;margin:20px 0 6px;font-weight:600}
.mph-meta{display:flex;flex-wrap:wrap;gap:6px 14px;color:var(--mute);font-size:12px;align-items:center}
.mph-pill{display:inline-block;padding:1px 9px;border-radius:999px;font-size:11px;font-weight:600;background:var(--warnsoft);color:var(--warn)}
.mph-pill.ok{background:var(--oksoft);color:var(--ok)}
.mph-banner{background:var(--badsoft);color:var(--bad);padding:8px 12px;margin:10px 0;font-weight:600;font-size:13px}
.mph-note{color:var(--mute);font-size:12px;font-style:italic;margin:4px 0}
.mph dl{display:grid;grid-template-columns:130px minmax(0,1fr);gap:4px 14px;margin:8px 0}
.mph dt{font-weight:600}
.mph dd{margin:0;white-space:pre-wrap}
.mph-scroll{overflow-x:auto}
.mph table{border-collapse:collapse;width:100%;font-size:13px}
.mph th{background:var(--brand);color:#fff;text-align:left;padding:6px 8px;font-weight:600;font-size:12px}
.mph td{border-bottom:1px solid var(--line);padding:6px 8px;vertical-align:top}
.mph-flow{margin:8px 0;text-align:center}
.mph-flow img{max-width:100%;height:auto;border:1px solid var(--line)}
.mph-flow figcaption{font-size:12px;color:var(--mute);font-weight:600}
.mph-link{color:var(--brand);background:none;border:0;padding:0;font:inherit;cursor:pointer;text-decoration:underline}
.mph-rt img{max-width:100%}
.mph-foot{margin-top:26px;border-top:1px solid var(--line);padding-top:8px;color:var(--mute);font-size:12px}
.mph-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;margin-top:12px}
.mph-card{border:1px solid var(--line);padding:10px 12px;background:var(--paper);text-align:left;cursor:pointer;font:inherit;color:var(--ink)}
.mph-card b{display:block;color:var(--brand)}
.mph-swatch{display:inline-block;width:14px;height:14px;border:2px solid;vertical-align:-2px;margin-right:6px;background:var(--paper)}
@media (max-width:820px){.mph{grid-template-columns:minmax(0,1fr)}.mph-nav{border-right:0;border-bottom:1px solid var(--line);position:static;max-height:300px}.mph dl{grid-template-columns:minmax(0,1fr)}}
`;

const ALLOWED: Record<string, string[]> = {
  P: [], BR: [], B: [], STRONG: [], I: [], EM: [], U: [], UL: [], OL: [], LI: [], H3: [], H4: [], H5: [], H6: [],
  TABLE: [], THEAD: [], TBODY: [], TR: [], TH: ['colspan', 'rowspan'], TD: ['colspan', 'rowspan'], SPAN: [], DIV: [], A: ['href'], IMG: ['src', 'alt']
};
const TABLES: { key: 'activities' | 'raci' | 'sap' | 'kpis' | 'escalation'; title: string; cols: [string, string][] }[] = [
  { key: 'activities', title: 'Detailed activities', cols: [['no', 'No'], ['activity', 'Activity / decision'], ['role', 'Role'], ['sap', 'SAP / system'], ['output', 'Output']] },
  { key: 'raci', title: 'RACI', cols: [['activity', 'Activity'], ['R', 'Responsible'], ['A', 'Accountable'], ['C', 'Consulted'], ['I', 'Informed']] },
  { key: 'sap', title: 'SAP references', cols: [['transaction', 'Transaction'], ['purpose', 'Purpose']] },
  { key: 'kpis', title: 'KPIs', cols: [['name', 'KPI'], ['definition', 'Definition'], ['target', 'Target']] },
  { key: 'escalation', title: 'Escalation and SLA', cols: [['stage', 'Stage'], ['to', 'Task / reminder to'], ['time', 'Time period'], ['action', 'Escalation'], ['sla', 'Previous SLA']] }
];
const TEXTS: [keyof IProcess, string][] = [['objective', 'Objective'], ['scope', 'Scope'], ['trigger', 'Trigger'], ['inputs', 'Inputs'], ['outputs', 'Outputs']];
const LATER: [keyof IProcess, string][] = [['risks', 'Risks and controls'], ['evidence', 'Required evidence'], ['forms', 'Forms and templates'], ['notes', 'Notes']];

function h(tag: string, attrs?: Record<string, string>, ...children: Child[]): HTMLElement {
  const el: HTMLElement = document.createElement(tag);
  if (attrs) {
    Object.keys(attrs).forEach((k: string) => { if (k === 'class') { el.className = attrs[k]; } else { el.setAttribute(k, attrs[k]); } });
  }
  children.forEach((c: Child) => { if (c) { el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); } });
  return el;
}

/** Text sections come from the tool already cleaned; they are cleaned again here because the file sits in a library that people can edit. */
function cleanHtml(html: string, base: string): DocumentFragment {
  const doc: Document = new DOMParser().parseFromString('<div>' + html + '</div>', 'text/html');
  const out: DocumentFragment = document.createDocumentFragment();
  const copy = (src: Node, dst: Node): void => {
    src.childNodes.forEach((n: Node) => {
      if (n.nodeType === Node.TEXT_NODE) { dst.appendChild(document.createTextNode(n.textContent || '')); return; }
      if (n.nodeType !== Node.ELEMENT_NODE) { return; }
      const e: Element = n as Element;
      const allowed: string[] | undefined = ALLOWED[e.tagName];
      if (!allowed) { if (e.tagName !== 'SCRIPT' && e.tagName !== 'STYLE') { copy(e, dst); } return; }
      const el: HTMLElement = document.createElement(e.tagName.toLowerCase());
      allowed.forEach((a: string) => {
        const v: string | undefined = e.getAttribute(a) || undefined;
        if (v === undefined) { return; }
        if (a === 'href') { if (/^https?:\/\//i.test(v)) { el.setAttribute('href', v); el.setAttribute('target', '_blank'); el.setAttribute('rel', 'noopener noreferrer'); } }
        else if (a === 'src') { if (/^assets\/[A-Za-z0-9._-]+$/.test(v)) { el.setAttribute('src', base + '/' + v); } }
        else if (a === 'colspan' || a === 'rowspan') { if (/^\d{1,2}$/.test(v)) { el.setAttribute(a, v); } }
        else { el.setAttribute(a, v); }
      });
      copy(e, el);
      dst.appendChild(el);
    });
  };
  copy(doc.body.firstChild as Node, out);
  return out;
}

function table(rows: Row[], cols: [string, string][]): HTMLElement {
  const body: HTMLElement = h('tbody');
  rows.forEach((r: Row) => body.appendChild(h('tr', undefined, ...cols.map((c: [string, string]) => h('td', undefined, r[c[0]] || '')))));
  return h('div', { class: 'mph-scroll' }, h('table', undefined, h('thead', undefined, h('tr', undefined, ...cols.map((c: [string, string]) => h('th', undefined, c[1])))), body));
}

/** Shows the published library found at `baseUrl` (a folder that holds handbook.json) inside `root`. */
export function mount(root: HTMLElement, baseUrl: string): void {
  const base: string = baseUrl.replace(/\/+$/, '');
  if (!document.getElementById('mph-style')) {
    const st: HTMLElement = h('style', { id: 'mph-style' });
    st.textContent = CSS;
    document.head.appendChild(st);
  }
  root.textContent = '';
  const main: HTMLElement = h('div', { class: 'mph-main' }, h('p', { class: 'mph-note' }, 'Loading the process library…'));
  const nav: HTMLElement = h('div', { class: 'mph-nav' });
  root.appendChild(h('div', { class: 'mph' }, nav, main));

  const file = (path: string): string => base + '/' + path.split('/').map(encodeURIComponent).join('/');
  const current = (): string => { const m: RegExpMatchArray | undefined = /[#&]mph=([^&]*)/.exec(window.location.hash) || undefined; return m ? decodeURIComponent(m[1]) : ''; };
  const go = (id: string): void => { window.location.hash = id ? 'mph=' + encodeURIComponent(id) : 'mph='; };

  fetch(file('handbook.json'), { credentials: 'same-origin', cache: 'no-cache' })
    .then((r: Response) => { if (!r.ok) { throw new Error('HTTP ' + r.status); } return r.json(); })
    .then((book: IBook) => {
      const all: { p: IProcess; d: IDepartment }[] = [];
      book.departments.forEach((d: IDepartment) => d.processes.forEach((p: IProcess) => all.push({ p, d })));
      const byId: Record<string, { p: IProcess; d: IDepartment }> = {};
      all.forEach((x: { p: IProcess; d: IDepartment }) => { byId[x.p.id] = x; });
      const search: HTMLInputElement = h('input', { class: 'mph-search', type: 'search', placeholder: 'Search ID, name, step, SAP code…', 'aria-label': 'Search processes' }) as HTMLInputElement;
      const list: HTMLElement = h('div');
      const text = (p: IProcess): string => [p.id, p.name, p.owner, p.objective, p.scope].concat(p.activities.map((a: Row) => a.activity + ' ' + a.role + ' ' + a.sap), p.sap.map((s: Row) => s.transaction)).join(' ').toLowerCase();
      const index: Record<string, string> = {};
      all.forEach((x: { p: IProcess; d: IDepartment }) => { index[x.p.id] = text(x.p); });

      const item = (p: IProcess): HTMLElement => {
        const b: HTMLElement = h('button', { class: 'mph-item' + (p.id === current() ? ' on' : ''), type: 'button' }, p.name, h('small', undefined, p.id + ' · ' + p.status_label));
        b.addEventListener('click', () => go(p.id));
        return b;
      };
      const drawNav = (): void => {
        const q: string = search.value.trim().toLowerCase();
        list.textContent = '';
        book.departments.forEach((d: IDepartment) => {
          const hits: IProcess[] = d.processes.filter((p: IProcess) => !q || index[p.id].indexOf(q) >= 0);
          if (!hits.length) { return; }
          const det: HTMLElement = h('details', undefined, h('summary', undefined, d.name, h('span', undefined, String(hits.length))), ...hits.map(item));
          if (q || d.processes.some((p: IProcess) => p.id === current())) { det.setAttribute('open', ''); }
          list.appendChild(det);
        });
        if (!list.firstChild) { list.appendChild(h('p', { class: 'mph-note' }, 'No process matches “' + search.value + '”.')); }
      };
      search.addEventListener('input', drawNav);
      const home: HTMLElement = h('button', { class: 'mph-brand', type: 'button' }, book.title);
      home.addEventListener('click', () => go(''));
      nav.appendChild(home);
      nav.appendChild(search);
      nav.appendChild(list);

      const foot = (): HTMLElement => h('div', { class: 'mph-foot' }, 'Published ' + book.generated_at.replace('T', ' ').replace('Z', ' UTC') + ' by ' + book.generated_by + ' · snapshot ' + book.snapshot +
        ' · ' + book.classification + ' · read-only copy; the controlled version is in MEA Process Hub.');
      const draft = (): HTMLElement | undefined => book.unapproved ? h('div', { class: 'mph-banner' }, 'UNCONTROLLED DRAFT – ' + book.unapproved + ' of ' + book.count + ' processes are not approved yet.') : undefined;

      const drawHome = (): void => {
        main.textContent = '';
        main.appendChild(h('p', { class: 'mph-kick' }, book.org + ' · ' + book.region));
        main.appendChild(h('h2', undefined, book.title));
        main.appendChild(h('div', { class: 'mph-meta' }, book.count + ' processes in ' + book.departments.length + ' departments'));
        const d0: HTMLElement | undefined = draft();
        if (d0) { main.appendChild(d0); }
        const cards: HTMLElement = h('div', { class: 'mph-cards' });
        book.departments.forEach((d: IDepartment) => {
          const c: HTMLElement = h('button', { class: 'mph-card', type: 'button' }, h('b', undefined, d.name), d.processes.length + ' processes · ' + d.processes.filter((p: IProcess) => p.status === 'published').length + ' approved');
          c.addEventListener('click', () => { if (d.processes.length) { go(d.processes[0].id); } });
          cards.appendChild(c);
        });
        main.appendChild(cards);
        if (book.legend.length) {
          main.appendChild(h('h3', undefined, 'Flowchart legend – outline colour shows the responsible role'));
          main.appendChild(h('div', { class: 'mph-cards' }, ...book.legend.map((l: { role: string; color: string }) => {
            const sw: HTMLElement = h('span', { class: 'mph-swatch' });
            if (/^#[0-9A-Fa-f]{6}$/.test(l.color)) { sw.style.borderColor = l.color; }
            return h('div', undefined, sw, l.role);
          })));
        }
        main.appendChild(foot());
      };

      const drawProcess = (p: IProcess, d: IDepartment): void => {
        main.textContent = '';
        main.appendChild(h('p', { class: 'mph-kick' }, d.name));
        main.appendChild(h('h2', undefined, p.id + ' – ' + p.name));
        const facts: string[] = ['Version ' + p.version, 'Owner: ' + (p.owner || '—')].concat(p.approved_by ? ['Approved by: ' + p.approved_by] : [], p.countries ? ['Region: ' + p.countries] : []);
        main.appendChild(h('div', { class: 'mph-meta' }, h('span', { class: 'mph-pill' + (p.status === 'published' ? ' ok' : '') }, p.status_label),
          ...facts.map((f: string) => h('span', undefined, f))));
        if (p.status !== 'published') { main.appendChild(h('div', { class: 'mph-banner' }, 'Not approved – for information only.')); }
        const dl: HTMLElement = h('dl');
        TEXTS.forEach((t: [keyof IProcess, string]) => { const v: string = String(p[t[0]] || ''); if (v) { dl.appendChild(h('dt', undefined, t[1])); dl.appendChild(h('dd', undefined, v)); } });
        if (p.responsible.length) { dl.appendChild(h('dt', undefined, 'Responsible')); dl.appendChild(h('dd', undefined, p.responsible.join(', '))); }
        if (dl.firstChild) { main.appendChild(dl); }
        if (p.pictures.length) {
          main.appendChild(h('h3', undefined, 'Process flow'));
          p.pictures.forEach((pic: IPicture) => {
            const cap: string = (pic.part ? 'Part ' + pic.part + ' of ' + pic.of : '') + (pic.part && pic.label ? ' – ' : '') + pic.label;
            main.appendChild(h('figure', { class: 'mph-flow' }, h('img', { src: file(pic.file), alt: 'Flowchart ' + p.id + (cap ? ', ' + cap : ''), loading: 'lazy' }), cap ? h('figcaption', undefined, cap) : undefined));
          });
        }
        TABLES.forEach((t: { key: 'activities' | 'raci' | 'sap' | 'kpis' | 'escalation'; title: string; cols: [string, string][] }) => {
          const rows: Row[] = p[t.key];
          if (!rows || !rows.length) { return; }
          main.appendChild(h('h3', undefined, t.title + ' (' + rows.length + ')'));
          main.appendChild(table(rows, t.cols));
          if (t.key === 'raci' && p.raci_draft) { main.appendChild(h('p', { class: 'mph-note' }, 'Draft RACI derived from the flowchart – not yet confirmed by the process owner.')); }
        });
        LATER.forEach((t: [keyof IProcess, string]) => { const v: string = String(p[t[0]] || ''); if (v) { main.appendChild(h('h3', undefined, t[1])); main.appendChild(h('dd', undefined, v)); } });
        p.sections.forEach((s: ISection) => {
          if (s.title) { main.appendChild(h('h3', undefined, s.title)); }
          const box: HTMLElement = h('div', { class: 'mph-rt' });
          box.appendChild(cleanHtml(s.html, base));
          main.appendChild(box);
        });
        const rel: IRelation[] = p.relations.filter((r: IRelation) => !!byId[r.id]);
        if (rel.length) {
          main.appendChild(h('h3', undefined, 'Related processes'));
          const ul: HTMLElement = h('ul');
          rel.forEach((r: IRelation) => {
            const a: HTMLElement = h('button', { class: 'mph-link', type: 'button' }, r.id + ' – ' + r.name);
            a.addEventListener('click', () => go(r.id));
            ul.appendChild(h('li', undefined, a, ' (' + r.type + ')'));
          });
          main.appendChild(ul);
        }
        main.appendChild(foot());
      };

      const route = (): void => {
        const hit: { p: IProcess; d: IDepartment } | undefined = byId[current()];
        if (hit) { drawProcess(hit.p, hit.d); } else { drawHome(); }
        drawNav();
        main.scrollIntoView({ block: 'nearest' });
      };
      window.addEventListener('hashchange', route);
      route();
    })
    .catch((e: Error) => {
      main.textContent = '';
      main.appendChild(h('div', { class: 'mph-banner' }, 'The published process library could not be loaded from ' + base + '/handbook.json (' + e.message + ').'));
      main.appendChild(h('p', { class: 'mph-note' }, 'Check that the folder address is right, that handbook.json was uploaded, and that you have permission to read the library.'));
    });
}
