"""Download the jgraph/drawio web app (Apache-2.0) so the editor runs fully offline, from this server.

Usage:  python fetch_drawio.py            (needs git on PATH and internet access once)
Result: ./drawio_webapp/  (served by MEA Process Hub at /drawio/). Review jgraph's licence / production
terms before relying on it for production use (see docs/ADMIN_GUIDE.md).
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
DEST = os.path.join(ROOT, "drawio_webapp")


def run(*a, cwd=None):
    subprocess.run(a, cwd=cwd, check=True)


def main():
    if shutil.which("git") is None:
        sys.exit("git is required (https://git-scm.com). Alternatively download the 'drawio-war' release from github.com/jgraph/drawio/releases and unzip its webapp into ./drawio_webapp")
    with tempfile.TemporaryDirectory() as td:
        run("git", "init", "-q", td)
        run("git", "remote", "add", "origin", "https://github.com/jgraph/drawio.git", cwd=td)
        run("git", "config", "core.sparseCheckout", "true", cwd=td)
        with open(os.path.join(td, ".git", "info", "sparse-checkout"), "w") as f:
            f.write("src/main/webapp/\n")
        run("git", "fetch", "--depth", "1", "origin", "HEAD", cwd=td)
        run("git", "checkout", "-q", "FETCH_HEAD", cwd=td)
        src = os.path.join(td, "src", "main", "webapp")
        if os.path.isdir(DEST):
            shutil.rmtree(DEST)
        shutil.copytree(src, DEST)
    print("draw.io installed to", DEST)


if __name__ == "__main__":
    main()
