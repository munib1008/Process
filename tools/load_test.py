"""Load test for MEA Process Hub: how many people can work at the same time on one installation?

The test never touches a real library. It starts its own server on a throw-away data folder (a fresh first-start
import of the delivered documents, or a copy of an existing data folder), signs in simulated users and lets them
read and edit like real ones, at several user counts in a row.

    python tools/load_test.py                         # 10, 25, 50, 100 users, 30 s each, 3 s between two actions of a user
    python tools/load_test.py --levels 50,100,200 --seconds 60
    python tools/load_test.py --from-data D:\\MEAProcessHub\\data   # test with a COPY of your own library
    python tools/load_test.py --levels 20 --seconds 15 --max-p95 2.0 --max-errors 1.0   # exit code 1 when the limits are missed (build)

What a simulated user does (share of actions): opens a process 58 %, library 10 %, dashboard 8 %, search 7 %, process tree 5 %,
saves a draft of an own process 8 %, writes an audit comment 4 %. Editors are 30 % of the users, the others are readers of the
editors' draft content (role reviewer, so that unpublished content is visible to them as well).

Read the result as an estimate: both sides run on one machine, the simulated users are threads of one Python process, and the
network of the real installation is not part of it. Stdlib only."""
import argparse
import http.cookiejar
import json
import os
import random
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD = "Load#Test2026!x"
MIX = [("open process", 58), ("library", 10), ("dashboard", 8), ("search", 7), ("tree", 5), ("save draft", 8), ("comment", 4)]
WORDS = ["delivery", "purchase", "stock", "invoice", "order", "VL01N", "quotation", "return", "MRP", "approval"]


class Client:
    def __init__(self, base):
        self.base, self.csrf = base, None
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, body=None, timeout=60):
        h = {"Content-Type": "application/json"}
        if self.csrf:
            h["X-CSRF-Token"] = self.csrf
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
        try:
            with self.op.open(req, timeout=timeout) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)
        except urllib.error.HTTPError as e:
            e.read()
            return e.code, None
        except Exception:                                    # refused, reset, timeout: counted as an error
            return 0, None

    def login(self, user, password=PASSWORD):
        s, r = self.call("POST", "/api/login", {"username": user, "password": password})
        if s == 200:
            self.csrf = r["csrf"]
        return s == 200


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def setup(data, n_users):
    """Create the simulated users and one process per editor directly in the throw-away library."""
    code = r'''
import json, sys
from mea_hub import db, service as svc
n = int(sys.argv[1])
dept = db.one("SELECT id FROM departments ORDER BY id LIMIT 1")["id"]
users = []
with db.tx():
    for i in range(n):
        role = "editor" if i % 10 < 3 else "reviewer"
        name = f"load_{i:03d}"
        if not db.one("SELECT 1 FROM users WHERE username=?", (name,)):
            svc.create_user(name, f"Load user {i}", sys.argv[2], role)
        users.append([name, role])
for name, role in users:
    if role == "editor" and not db.one("SELECT 1 FROM processes WHERE process_id=?", (f"LT-S-{name[5:]}-01",)):
        u = db.one("SELECT * FROM users WHERE username=?", (name,))
        svc.new_process(u, dict(name=f"Load test process {name[5:]}", department_id=dept, process_id=f"LT-S-{name[5:]}-01", objective="Load test"))
print(json.dumps(dict(users=users, processes=[r["process_id"] for r in db.q("SELECT process_id FROM processes WHERE kind!='reference'")])))
'''
    out = subprocess.run([sys.executable, "-c", code, str(n_users), PASSWORD], cwd=ROOT, env=dict(os.environ, MEA_HUB_DATA=data), capture_output=True, text=True)
    if out.returncode:
        raise SystemExit("Setup failed:\n" + out.stderr[-2000:])
    return json.loads(out.stdout.strip().splitlines()[-1])


def run_level(base, users, pids, seconds, think, seed):
    """-> dict(action -> [latencies]), errors per action, wall time"""
    lat, err, lock = {a: [] for a, _ in MIX}, {a: 0 for a, _ in MIX}, threading.Lock()
    stop_at = [0.0]
    ready = threading.Barrier(len(users) + 1)
    failed_login = []

    def user(idx, name, role):
        rnd = random.Random(seed * 1000 + idx)
        c = Client(base)
        if not c.login(name):
            failed_login.append(name)
        own = f"LT-S-{name[5:]}-01"
        try:
            ready.wait(timeout=180)
        except threading.BrokenBarrierError:
            return
        time.sleep(rnd.random() * think)                     # users do not click in step
        actions, weights = [a for a, _ in MIX], [w for _, w in MIX]
        while time.time() < stop_at[0]:
            a = rnd.choices(actions, weights)[0]
            if a in ("save draft", "comment") and role != "editor":
                a = "open process"
            t0 = time.perf_counter()
            if a == "open process":
                s, _ = c.call("GET", "/api/process/" + rnd.choice(pids))
            elif a == "library":
                s, _ = c.call("GET", "/api/library")
            elif a == "dashboard":
                s, _ = c.call("GET", "/api/dashboard")
            elif a == "search":
                s, _ = c.call("GET", "/api/search?q=" + rnd.choice(WORDS))
            elif a == "tree":
                s, _ = c.call("GET", "/api/tree")
            elif a == "save draft":
                s, _ = c.call("PUT", f"/api/process/{own}/draft", {"content": {"objective": f"Load test text {rnd.random():.6f} " + "x" * 400}})
            else:
                s, _ = c.call("POST", f"/api/process/{own}/comments", {"body": f"Load test comment {rnd.random():.6f}"})
            d = time.perf_counter() - t0
            with lock:
                lat[a].append(d)
                if s != 200:
                    err[a] += 1
            if think:
                time.sleep(think * (0.5 + rnd.random()))     # 0.5 .. 1.5 x the think time

    threads = [threading.Thread(target=user, args=(i, n, r), daemon=True) for i, (n, r) in enumerate(users)]
    for t in threads:
        t.start()
    stop_at[0] = time.time() + 3600
    ready.wait(timeout=180)
    t0 = time.time()
    stop_at[0] = t0 + seconds
    for t in threads:
        t.join(timeout=seconds + 120)
    return lat, err, time.time() - t0, failed_login


def pct(values, p):
    if not values:
        return 0.0
    v = sorted(values)
    return v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))]


def main():
    ap = argparse.ArgumentParser(description="Load test on a throw-away copy of the library")
    ap.add_argument("--levels", default="10,25,50,100", help="numbers of simultaneous users, tested one after the other")
    ap.add_argument("--seconds", type=int, default=30, help="duration per level")
    ap.add_argument("--think", type=float, default=3.0, help="average seconds between two actions of one user (0 = as fast as possible)")
    ap.add_argument("--from-data", help="copy this data folder instead of importing the delivered documents")
    ap.add_argument("--report", help="write the result as markdown to this file")
    ap.add_argument("--max-p95", type=float, help="fail (exit code 1) when the 95th percentile of any level is above this many seconds")
    ap.add_argument("--max-errors", type=float, help="fail when the error rate of any level is above this percentage")
    a = ap.parse_args()
    levels = [int(x) for x in a.levels.split(",") if x.strip()]
    tmp = tempfile.mkdtemp(prefix="mea_load_")
    data = os.path.join(tmp, "data")
    if a.from_data:
        shutil.copytree(a.from_data, data, ignore=shutil.ignore_patterns("backups", "exports"))
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    log = open(os.path.join(tmp, "server.log"), "w")
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "run.py"), "--port", str(port), "--no-browser"], cwd=ROOT, env=dict(os.environ, MEA_HUB_DATA=data), stdout=log, stderr=subprocess.STDOUT)
    rows, ok = [], True
    try:
        print("Starting a server on a throw-away library" + ("" if a.from_data else " (first start imports the delivered documents, this takes a minute)") + " …")
        for _ in range(600):
            if srv.poll() is not None:
                raise SystemExit("The server stopped: see " + log.name)
            if Client(base).call("GET", "/api/health", timeout=3)[0] == 200:
                break
            time.sleep(0.5)
        else:
            raise SystemExit("The server did not start: see " + log.name)
        info = setup(data, max(levels))
        pids = info["processes"]
        print(f"Library: {len(pids)} processes. Users per level: {levels}; {a.seconds} s each; think time {a.think} s.\n")
        head = f"{'users':>6} {'actions':>8} {'per s':>7} {'errors':>7} {'median':>8} {'p95':>8} {'p99':>8} {'max':>8}   slowest action (p95)"
        print(head)
        for n in levels:
            lat, err, wall, bad = run_level(base, info["users"][:n], pids, a.seconds, a.think, n)
            allv = [x for v in lat.values() for x in v]
            errors = sum(err.values()) + len(bad)
            rate = 100.0 * errors / max(1, len(allv))
            slow = max(lat, key=lambda k: pct(lat[k], 95))
            row = dict(users=n, actions=len(allv), per_s=len(allv) / wall, errors=errors, error_rate=rate, median=statistics.median(allv) if allv else 0, p95=pct(allv, 95), p99=pct(allv, 99),
                       max=max(allv) if allv else 0, slowest=f"{slow} {pct(lat[slow], 95):.2f} s", by_action={k: dict(n=len(v), p95=pct(v, 95), errors=err[k]) for k, v in lat.items()})
            rows.append(row)
            print(f"{n:>6} {row['actions']:>8} {row['per_s']:>7.1f} {rate:>6.2f}% {row['median']:>7.3f}s {row['p95']:>7.3f}s {row['p99']:>7.3f}s {row['max']:>7.2f}s   {row['slowest']}")
            if (a.max_p95 is not None and row["p95"] > a.max_p95) or (a.max_errors is not None and rate > a.max_errors) or not allv:
                ok = False
        good = [r["users"] for r in rows if r["p95"] <= 1.0 and r["error_rate"] <= 0.5]
        verdict = (f"Up to {max(good)} simultaneous users answered 95 % of all actions within 1 second with at most 0.5 % errors." if good
                   else "No tested level answered 95 % of all actions within 1 second with at most 0.5 % errors.")
        print("\n" + verdict)
        if a.report:
            with open(a.report, "w", encoding="utf-8") as f:
                f.write(f"# Load test result\n\n{time.strftime('%Y-%m-%d %H:%M')} · {len(pids)} processes · {a.seconds} s per level · think time {a.think} s · "
                        f"{os.cpu_count()} CPU cores · Python {sys.version.split()[0]}\n\n| Users | Actions | per second | Errors | Median | p95 | p99 | Max | Slowest action (p95) |\n|---|---|---|---|---|---|---|---|---|\n")
                for r in rows:
                    f.write(f"| {r['users']} | {r['actions']} | {r['per_s']:.1f} | {r['error_rate']:.2f} % | {r['median']:.3f} s | {r['p95']:.3f} s | {r['p99']:.3f} s | {r['max']:.2f} s | {r['slowest']} |\n")
                f.write(f"\n{verdict}\n\nServer and simulated users ran on the same machine; treat the figures as an estimate.\n")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        log.close()
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
