# PyInstaller spec - builds a single-file executable (MEA_Process_Hub.exe on Windows).
# Usage (from the repository root):  pyinstaller build/mea_hub.spec --noconfirm --distpath dist --workpath build/work
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = os.path.abspath(os.path.join(SPECPATH, ".."))
datas = [(os.path.join(root, "mea_hub", "static"), "static")]
datas += collect_data_files("docx")        # python-docx default template
# python-docx opens "docx/parts/../templates/default-header.xml"; the folder must physically exist when frozen.
_keep = os.path.join(root, "build", "work", "_keep")
os.makedirs(_keep, exist_ok=True)
open(os.path.join(_keep, ".keep"), "w").close()
datas += [(_keep, "docx/parts")]
datas += collect_data_files("reportlab")   # bundled TrueType fonts used by the PDF export
datas += collect_data_files("openpyxl")
hidden = collect_submodules("lxml") + ["PIL.PngImagePlugin", "PIL.JpegImagePlugin", "openpyxl.cell._writer"]

a = Analysis([os.path.join(root, "run.py")], pathex=[root], datas=datas, hiddenimports=hidden,
             excludes=["tkinter", "matplotlib", "numpy", "scipy", "pytest"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="MEA_Process_Hub", debug=False, strip=False, upx=False,
          console=True, disable_windowed_traceback=False)
