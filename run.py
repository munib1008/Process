"""MEA Process Hub launcher (also the PyInstaller entry point).

  MEA_Process_Hub.exe                 start the app and open the browser
  MEA_Process_Hub.exe --import a.docx b.docx
  MEA_Process_Hub.exe --demo-users    also create one evaluation user per role
  MEA_Process_Hub.exe --backup        write a backup ZIP and exit
"""
import argparse
import glob
import json
import os
import sys
import threading
import webbrowser

from mea_hub import config, db, importer, queries, service as svc
from mea_hub.server import make_server


def main():
    for stream in (sys.stdout, sys.stderr):          # never crash on a legacy Windows console code page
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="MEA Process Hub")
    ap.add_argument("--host", default=os.environ.get("MEA_HUB_HOST", "127.0.0.1"), help="bind address (default 127.0.0.1 = this PC only; env MEA_HUB_HOST)")
    ap.add_argument("--port", type=int, default=int(os.environ.get("MEA_HUB_PORT") or os.environ.get("PORT") or 8765), help="env MEA_HUB_PORT or PORT")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--import", dest="imports", nargs="*", help=".docx / .drawio files to import")
    ap.add_argument("--demo-users", action="store_true", help="create demo_<role> users (password ChangeMe!123) for evaluation")
    ap.add_argument("--backup", action="store_true")
    ap.add_argument("--reset-admin", action="store_true", help="give the 'admin' user a new one-time password and exit")
    ap.add_argument("--reconcile-report", metavar="FILE", help="write the source reconciliation report (markdown) and exit")
    args = ap.parse_args()

    config.ensure_dirs()
    if args.reset_admin:
        pw, path = svc.reset_admin()
        print("=" * 66)
        print(" Admin password reset.")
        print(f"   username: admin   password: {pw}")
        print(f"   (also saved in {path}; you must change it at first login)")
        print(" Start MEA_Process_Hub.exe (or refresh the browser) and sign in.")
        print("=" * 66)
        return
    first = svc.bootstrap(demo_users=args.demo_users)
    if args.backup:
        print("Backup written:", queries.make_backup())
        return
    if args.reconcile_report:
        with open(args.reconcile_report, "w", encoding="utf-8") as f:
            f.write(queries.reconcile_markdown())
        print("Report written:", args.reconcile_report)
        return
    files = list(args.imports or [])
    first_start = not db.one("SELECT 1 FROM sources LIMIT 1")
    if first_start:                                                      # first start: auto-import ./source_documents
        files += sorted(glob.glob(os.path.join(config.app_root(), "source_documents", "*.docx")) + glob.glob(os.path.join(config.app_root(), "source_documents", "*.drawio")) + glob.glob(os.path.join(config.app_root(), "source_documents", "flows", "*.drawio")))
    if files:
        print(f"Importing {len(files)} document(s)…")
        res = importer.import_paths(files, "system")
        for s in res["sources"]:
            print(f"  {s['filename']}: {len(s['new'])} new processes, {len(s['merged'])} duplicate mappings")
        for f in res["skipped"]:
            print("  skipped (already imported):", f)
        if first_start:                                                  # drafts derived from the flows: a RACI per process, a work instruction per SAP task
            from mea_hub import drafts
            r1, r2 = drafts.generate_all_raci(drafts.SYSTEM), drafts.generate_sap_instructions(drafts.SYSTEM)
            print(f"  draft RACI for {r1['processes']} processes ({r1['rows']} rows), {len(r2['created'])} draft SAP work instructions")
    mapping = os.path.join(config.app_root(), "source_documents", "_canvas", "canvas_mapping.json")
    if os.path.isfile(mapping):                                          # recorded ID decisions also reach an existing data folder (idempotent)
        try:
            with open(mapping, encoding="utf-8") as f:
                cor = [c for spec in json.load(f).get("flows", []) for c in spec.get("id_corrections", [])]
            for old_id, new_id in svc.apply_id_corrections(cor, "canvas_mapping.json"):
                print(f"  process ID changed by recorded decision: {old_id} -> {new_id}")
        except (OSError, ValueError) as e:
            print("  ID decisions not applied:", e)
    srv = make_server(args.host, args.port)
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '') else args.host}:{args.port}/"
    print("=" * 66)
    print(" MEA Process Hub is running:", url)
    print(" Data folder:", config.DATA_DIR)
    if first:
        print(f"\n FIRST RUN  ->  username: admin   password: {first[0]}")
        print(f" (also saved in {first[1]}; you must change it at first login)")
    elif os.path.isfile(os.path.join(config.DATA_DIR, svc.ADMIN_FILE)):
        print(f"\n Sign in as 'admin' with the one-time password in {os.path.join(config.DATA_DIR, svc.ADMIN_FILE)}")
    print(" Forgot the admin password? Close this window and run 'Reset admin password.bat'.")
    if args.host not in ("127.0.0.1", "localhost"):
        print(" WARNING: listening on the network. Use only on a trusted LAN or behind an HTTPS proxy; the app itself has no TLS.")
    print(" Press Ctrl+C (or close this window) to stop.")
    print("=" * 66)
    if not args.no_browser and args.host in ("127.0.0.1", "localhost"):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
