"""dormakaba corporate identity (taken from the dormakaba MEA marketing collateral policy 2017):
blue #003594 for titles/panels, red #E4002B for kicker lines and emphasis, light grey #E6E6E6 blocks, Arial."""
import os

from . import config

BLUE = "#003594"
RED = "#E4002B"
GREY = "#E6E6E6"
INK = "#1E1E1E"
MUTE = "#6E6E6E"
LINE = "#BFBFBF"
REGION = "Region MEA"


def rgb(hexcol):
    h = hexcol.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def asset(name):
    return os.path.join(config.STATIC_DIR, "brand", name)


LOGO = asset("dormakaba_logo.png")
LOGO_WHITE = asset("dormakaba_logo_white.png")
MARK = asset("dormakaba_mark.png")

# Arial is the house font. PDF output embeds a TrueType font: real Arial on Windows, otherwise the
# metric-compatible Liberation Sans, otherwise reportlab's bundled Vera.
_FONT_SETS = [
    [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", f) for f in ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf")],
    [f"/usr/share/fonts/truetype/liberation/LiberationSans-{s}.ttf" for s in ("Regular", "Bold", "Italic", "BoldItalic")],
    ["/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf", "/Library/Fonts/Arial Italic.ttf", "/Library/Fonts/Arial Bold Italic.ttf"],
]


def pdf_font_family():
    """Register and return (regular, bold, italic) font names for reportlab."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import reportlab
    vera = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
    sets = _FONT_SETS + [[os.path.join(vera, f) for f in ("Vera.ttf", "VeraBd.ttf", "VeraIt.ttf", "VeraBI.ttf")]]
    for files in sets:
        if all(os.path.isfile(f) for f in files):
            try:
                names = ("Brand", "Brand-B", "Brand-I", "Brand-BI")
                for n, f in zip(names, files):
                    pdfmetrics.registerFont(TTFont(n, f))
                pdfmetrics.registerFontFamily("Brand", normal="Brand", bold="Brand-B", italic="Brand-I", boldItalic="Brand-BI")
                return names[0], names[1], names[2]
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
