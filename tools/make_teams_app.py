"""Build the Microsoft Teams app package for MEA Process Hub (the same package as Administration > Teams & SharePoint).

Usage:
    python tools/make_teams_app.py --url https://processhub.example.com
    python tools/make_teams_app.py --url https://processhub.example.com --name "MEA Process Hub" --developer "dormakaba MEA" --out MEA_Process_Hub_Teams.zip

Upload the ZIP in Teams (Apps > Manage your apps > Upload an app) or in the Teams admin center (Manage apps > Upload new app).
On the server, start the tool with  --embed-origins teams  (or MEA_HUB_EMBED_ORIGINS=teams) so that Teams may display it."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mea_hub.teams import build, icons, manifest  # noqa: E402,F401


def main():
    ap = argparse.ArgumentParser(description="Build the Microsoft Teams app package for MEA Process Hub")
    ap.add_argument("--url", required=True, help="https address of the hosted tool, e.g. https://processhub.example.com")
    ap.add_argument("--name", default="MEA Process Hub")
    ap.add_argument("--developer", default="dormakaba MEA", help="organisation shown as the publisher of the app")
    ap.add_argument("--app-id", help="GUID of the app (default: derived from the address, so it stays the same for updates)")
    ap.add_argument("--version", default="1.0.0", help="raise it when you upload an update")
    ap.add_argument("--privacy-url", help="default: <url>/teams/about.html")
    ap.add_argument("--terms-url", help="default: <url>/teams/about.html")
    ap.add_argument("--out", default="MEA_Process_Hub_Teams.zip")
    a = ap.parse_args()
    try:
        data = build(a.url, name=a.name, developer=a.developer, app_id=a.app_id, version=a.version, privacy_url=a.privacy_url, terms_url=a.terms_url)
    except ValueError as e:
        sys.exit(str(e))
    with open(a.out, "wb") as f:
        f.write(data)
    print(f"{a.out} written ({len(data) // 1024} KB). Server: start the tool with  --embed-origins teams  and HTTPS in front of it.")


if __name__ == "__main__":
    main()
