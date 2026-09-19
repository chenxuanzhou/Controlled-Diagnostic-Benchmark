"""Overview figure (Fig. 2 of the paper), generated as editable SVG and converted
to PDF for \\includegraphics. Layout follows the academic-figures skill: raw SVG,
every element in a named group, all text as <text>, coordinates rounded to 0.1 mm,
colour-blind-safe Wong palette, smallest font 2.1 mm = 6 pt at full text width.
The worked example is a real benchmark item (1598-2025-ghg_scope1-P-scope and its
record-level twin in the 95-item panel).

usage: python scripts/make_overview_figure.py        -> variant A (used in the paper)
       python scripts/make_overview_figure.py B      -> variant B (two rows, minimal style)
Output: paper/figures/fig_overview_<variant>.svg / .pdf / .png
"""
import math, pathlib, sys
import pymupdf

OUT = pathlib.Path("paper/figures")
FONT = "Helvetica, Arial, Liberation Sans, sans-serif"
BLUE, ORANGE, GREEN, VERM, GREY = "#0072B2", "#E69F00", "#009E73", "#D55E00", "#5F5F5F"
T_BLUE, T_ORANGE, T_GREEN, T_VERM = "#E3F0F8", "#FCF1D9", "#DFF3EC", "#FBE6D9"
MIN = 2.1   # smallest font, mm


def R(v):
    return round(v, 1)


class Svg:
    def __init__(self, w, h):
        self.w, self.h, self.parts, self.depth = w, h, [], 1

    def add(self, s):
        self.parts.append("  " * self.depth + s)

    def open(self, gid):
        self.add(f'<g id="{gid}">'); self.depth += 1

    def close(self):
        self.depth -= 1; self.add("</g>")

    def rect(self, x, y, w, h, fill="#FFFFFF", stroke="#333333", sw=0.3, rx=1.2, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<rect x="{R(x)}" y="{R(y)}" width="{R(w)}" height="{R(h)}" rx="{rx}" ry="{rx}" '
                 f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def text(self, x, y, s, size=MIN, weight="normal", fill="#222222", anchor="start", style="normal"):
        s = s.replace("&", "&amp;").replace("<", "&lt;")
        self.add(f'<text x="{R(x)}" y="{R(y)}" font-family="{FONT}" font-size="{size}" '
                 f'font-weight="{weight}" font-style="{style}" fill="{fill}" text-anchor="{anchor}">{s}</text>')

    def line(self, x1, y1, x2, y2, stroke="#444444", sw=0.35, arrow=False, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{R(x1)}" y1="{R(y1)}" x2="{R(x2)}" y2="{R(y2)}" stroke="{stroke}" '
                 f'stroke-width="{sw}"{d}/>')
        if arrow:   # explicit triangle: some SVG->PDF converters ignore <marker>
            a = math.atan2(y2 - y1, x2 - x1); L, Wd = 1.9, 0.75
            bx, by = x2 - L * math.cos(a), y2 - L * math.sin(a)
            p1 = (bx - Wd * math.sin(a), by + Wd * math.cos(a)); p2 = (bx + Wd * math.sin(a), by - Wd * math.cos(a))
            self.add(f'<path d="M {R(x2)} {R(y2)} L {R(p1[0])} {R(p1[1])} L {R(p2[0])} {R(p2[1])} Z" '
                     f'fill="{stroke}" stroke="none"/>')

    def path(self, d, stroke="#444444", sw=0.35, fill="none"):
        self.add(f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def render(self):
        head = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
                f'width="{self.w}mm" height="{self.h}mm" viewBox="0 0 {self.w} {self.h}" version="1.1">\n')
        return head + "\n".join(self.parts) + "\n</svg>\n"


def chip(g, x, y, w, label, fill, stroke, size=MIN, weight="bold", h=3.8):
    g.rect(x, y, w, h, fill=fill, stroke=stroke, sw=0.25, rx=1.9)
    g.text(x + w / 2, y + h / 2 + size * 0.36, label, size=size, weight=weight, anchor="middle")


def record_card(g, gid, x, y, w, title, indicator, value, meta, hi_ind=False, hi_val=False, h=16.2):
    """A filing record as the system sees it; changed fields are boxed in vermillion."""
    g.open(gid)
    g.rect(x, y, w, h, fill=T_ORANGE, stroke=ORANGE, sw=0.35)
    g.text(x + 1.4, y + 3.1, title, fill=GREY, style="italic")
    if hi_ind:
        g.rect(x + 0.8, y + 4.3, w - 1.6, 3.7, fill=T_VERM, stroke=VERM, sw=0.3, rx=0.6)
    g.text(x + 1.5, y + 7.0, indicator, size=2.3, weight="bold")
    if hi_val:
        g.rect(x + 0.8, y + 8.4, w - 1.6, 3.7, fill=T_VERM, stroke=VERM, sw=0.3, rx=0.6)
    g.text(x + 1.5, y + 11.1, value, size=2.3)
    g.text(x + 1.5, y + 14.7, meta, fill=GREY)
    g.close()


def page_icon(g, x, y, w, h, token):
    g.open("narrative-page")
    fold = 3.0
    g.path(f"M {R(x)} {R(y)} L {R(x + w - fold)} {R(y)} L {R(x + w)} {R(y + fold)} L {R(x + w)} {R(y + h)} "
           f"L {R(x)} {R(y + h)} Z", stroke=BLUE, sw=0.35, fill=T_BLUE)
    g.path(f"M {R(x + w - fold)} {R(y)} L {R(x + w - fold)} {R(y + fold)} L {R(x + w)} {R(y + fold)}",
           stroke=BLUE, sw=0.3)
    g.text(x + 1.4, y + 3.2, "Report, p. 56", fill=GREY, style="italic")
    for k, ww in enumerate((0.78, 0.62)):
        g.line(x + 1.6, y + 5.2 + 1.5 * k, x + 1.6 + (w - 3.2) * ww, y + 5.2 + 1.5 * k, stroke="#9BB7C9", sw=0.45)
    g.rect(x + 0.9, y + 8.0, w - 1.8, 7.0, fill="#FFFFFF", stroke=BLUE, sw=0.3, rx=0.6)
    g.text(x + 1.6, y + 10.8, "GHG Scope 1", size=2.3, weight="bold")
    g.text(x + 1.6, y + 13.9, token, size=2.3, fill=BLUE, weight="bold")
    for k, ww in enumerate((0.7, 0.5)):
        g.line(x + 1.6, y + 16.8 + 1.5 * k, x + 1.6 + (w - 3.2) * ww, y + 16.8 + 1.5 * k, stroke="#9BB7C9", sw=0.45)
    g.close()


def lock_icon(g, x, y, s=1.0):
    g.open("sealed-ledger-icon")
    g.path(f"M {R(x + 0.9 * s)} {R(y + 2.0 * s)} L {R(x + 0.9 * s)} {R(y + 1.2 * s)} "
           f"A {R(1.1 * s)} {R(1.1 * s)} 0 0 1 {R(x + 3.1 * s)} {R(y + 1.2 * s)} L {R(x + 3.1 * s)} {R(y + 2.0 * s)}",
           stroke="#333333", sw=0.35)
    g.rect(x, y + 2.0 * s, 4.0 * s, 3.0 * s, fill="#333333", stroke="#333333", sw=0.2, rx=0.4)
    g.close()


# ----------------------------------------------------------------------------- variant A
def variant_a():
    W, H = 122.0, 64.0
    g = Svg(W, H)
    xa0, xa1 = 1.0, 27.4
    xb0, xb1 = 30.0, 88.4
    xc0, xc1 = 91.0, 121.0

    g.open("frame")
    g.rect(0.4, 0.4, W - 0.8, H - 0.8, fill="#FFFFFF", stroke="#555555", sw=0.35, rx=0.8)
    g.line(28.7, 0.4, 28.7, H - 0.4, stroke="#555555", sw=0.3)
    g.line(89.7, 0.4, 89.7, H - 0.4, stroke="#555555", sw=0.3)
    g.close()

    g.open("panel-titles")
    g.text((xa0 + xa1) / 2, 5.0, "A. Sources", size=2.8, weight="bold", anchor="middle")
    g.text((xb0 + xb1) / 2, 5.0, "B. What the system is shown", size=2.8, weight="bold", anchor="middle")
    g.text((xc0 + xc1) / 2, 5.0, "C. Systems", size=2.8, weight="bold", anchor="middle")
    g.close()

    # ---------------- A
    g.open("panel-a")
    pw = 23.4; px = (xa0 + xa1) / 2 - pw / 2
    page_icon(g, px, 8.4, pw, 20.4, "1,150.4962 t")
    g.open("anchor-link")
    lx = px + 3.2
    g.line(lx, 29.4, lx, 38.8, stroke=GREEN, sw=0.5)
    g.line(lx - 1.3, 29.4, lx + 1.3, 29.4, stroke=GREEN, sw=0.5)
    g.line(lx - 1.3, 38.8, lx + 1.3, 38.8, stroke=GREEN, sw=0.5)
    g.text(lx + 2.2, 33.2, "anchor A1–A4", fill=GREEN, weight="bold")
    g.text(lx + 2.2, 36.2, "same digits (G-B)", fill=GREEN)
    g.close()
    record_card(g, "true-filing", px, 39.6, pw, "Filing record (G-A)", "GHG Scope 1",
                "1,150.4962 tCO2e", "consolidated · 2025")
    g.text((xa0 + xa1) / 2, 59.0, "885 companies,", anchor="middle", fill="#333333")
    g.text((xa0 + xa1) / 2, 61.8, "3,483 anchors", anchor="middle", fill="#333333")
    g.close()

    # ---------------- B
    g.open("panel-b")
    cw, gap = 18.2, 1.9
    xs = [xb0, xb0 + cw + gap, xb0 + 2 * (cw + gap)]
    heads = [("Control", "P-none"), ("Value swap", "3,000 items"), ("Record swap", "95-item panel")]
    for x, (h1, h2) in zip(xs, heads):
        g.text(x + cw / 2, 9.4, h1, size=2.3, weight="bold", anchor="middle")
        g.text(x + cw / 2, 12.3, h2, fill=GREY, anchor="middle", style="italic")
    g.open("claim-row")
    for k, x in enumerate(xs):
        if k < 2:
            g.rect(x, 14.0, cw, 6.4, fill="#FFFFFF", stroke="#9BB7C9", sw=0.3, rx=0.8, dash="1.2,0.9")
            g.text(x + cw / 2, 16.7, "claim implicit", fill=GREY, anchor="middle")
            g.text(x + cw / 2, 19.4, "in page text", fill=GREY, anchor="middle")
        else:
            g.rect(x, 14.0, cw, 6.4, fill=T_BLUE, stroke=BLUE, sw=0.35, rx=0.8)
            g.text(x + cw / 2, 16.7, "claim: Scope 1", anchor="middle")
            g.text(x + cw / 2, 19.4, "= 1,150.4962", anchor="middle")
    g.close()
    record_card(g, "card-control", xs[0], 21.8, cw, "record shown", "GHG Scope 1", "1,150.4962 t", "consol. · 2025")
    record_card(g, "card-value-level", xs[1], 21.8, cw, "record shown", "GHG Scope 1", "2,087.1121 t",
                "consol. · 2025", hi_val=True)
    record_card(g, "card-record-level", xs[2], 21.8, cw, "record shown", "GHG Scope 2", "2,087.1121 t",
                "consol. · 2025", hi_ind=True, hi_val=True)
    g.open("card-notes")
    g.text(xs[0] + cw / 2, 40.9, "unchanged", fill=GREY, anchor="middle")
    g.text(xs[1] + cw / 2, 40.9, "Scope-2 value,", fill=VERM, anchor="middle")
    g.text(xs[1] + cw / 2, 43.6, "label unchanged", fill=VERM, anchor="middle")
    g.text(xs[2] + cw / 2, 40.9, "Scope-2 record,", fill=VERM, anchor="middle")
    g.text(xs[2] + cw / 2, 43.6, "own label", fill=VERM, anchor="middle")
    g.close()
    g.open("admissible-row")
    g.text(xb0, 47.6, "verdicts the task rules admit:", fill="#333333", style="italic")
    chip(g, xs[0] + 0.6, 48.8, cw - 1.2, "Supported", T_GREEN, GREEN)
    chip(g, xs[1] + 0.6, 48.8, cw - 1.2, "C  or  NC", T_GREEN, GREEN)
    chip(g, xs[2], 48.8, cw, "NotComparable", T_GREEN, GREEN)
    g.text(xs[1] + cw / 2, 55.4, "(ledger alone says NC)", fill=GREY, anchor="middle")
    g.close()
    g.open("sealed-ledger")
    g.line(xb0, 57.2, xb1, 57.2, stroke="#BBBBBB", sw=0.25)
    lock_icon(g, xb0 + 0.4, 57.8, s=0.62)
    g.text(xb0 + 3.8, 60.9, "sealed ledger = gold (G-C); other types: Table 1", fill="#333333")
    g.close()
    g.close()

    # ---------------- C
    g.open("panel-c")
    bw = xc1 - xc0
    rows = [("C0", ["anchor page as text"]), ("C1", ["+ neighbouring pages"]),
            ("C3", ["one agent + 4 tools"]),
            ("C4", ["extractor → retriever", "→ adversarial auditor", "→ adjudicator"])]
    y = 8.0
    for cid, lines in rows:
        h = 5.0 + 2.6 * (len(lines) - 1)
        g.rect(xc0, y, bw, h, fill="#F4F4F4", stroke="#555555", sw=0.3, rx=1.0)
        g.text(xc0 + 1.3, y + 3.4, cid, size=2.3, weight="bold")
        for k, t in enumerate(lines):
            g.text(xc0 + 6.4, y + 3.4 + 2.6 * k, t)
        y += h + 1.1
    g.text(xc0 + bw / 2, y + 1.9, "same model, same record", fill=GREY, anchor="middle", style="italic")
    ya = y + 3.0
    g.line(xc0 + bw / 2, ya, xc0 + bw / 2, ya + 4.4, arrow=True)
    yv = ya + 5.0
    g.rect(xc0, yv, bw, H - 1.6 - yv, fill=T_GREEN, stroke=GREEN, sw=0.35, rx=1.0)
    g.text(xc0 + bw / 2, yv + 3.3, "verdict + mismatch type", weight="bold", anchor="middle")
    for k, v in enumerate(("Supported", "Contradicted", "NotComparable", "NotApplicable")):
        g.text(xc0 + bw / 2, yv + 6.6 + 2.75 * k, v, anchor="middle")
    g.close()
    return g


# ----------------------------------------------------------------------------- variant B
def variant_b():
    """Two rows, clean/minimal: sources and systems on top, the three records below."""
    W, H = 122.0, 76.0
    g = Svg(W, H)
    g.open("panel-titles")
    g.text(1.0, 4.4, "a", size=3.2, weight="bold"); g.text(5.0, 4.4, "Sources and anchor", size=2.6, weight="bold")
    g.text(64.0, 4.4, "b", size=3.2, weight="bold"); g.text(68.0, 4.4, "Systems and verdict", size=2.6, weight="bold")
    g.text(1.0, 38.4, "c", size=3.2, weight="bold"); g.text(5.0, 38.4, "What the system is shown", size=2.6, weight="bold")
    g.close()
    g.open("panel-a")
    page_icon(g, 1.0, 7.0, 23.4, 20.4, "1,150.4962 t")
    g.line(25.4, 17.0, 35.0, 17.0, stroke="#333333", sw=0.4, arrow=True)
    g.text(30.0, 14.6, "A1–A4", anchor="middle", weight="bold")
    g.text(30.0, 20.6, "same digits", anchor="middle", fill=GREY)
    record_card(g, "true-filing", 36.0, 9.0, 24.0, "Filing record (G-A)", "GHG Scope 1", "1,150.4962 tCO2e", "consolidated · 2025")
    g.text(1.0, 32.0, "885 companies, 14,622 pairs, 3,483 anchors", fill="#333333")
    g.close()
    g.open("panel-b")
    x = 64.0
    for cid, lab, w in (("C0", "page text", 12.4), ("C1", "+ pages", 11.4), ("C3", "agent + tools", 15.4), ("C4", "adversarial roles", 16.0)):
        g.rect(x, 7.0, w, 8.6, fill="#FFFFFF", stroke="#333333", sw=0.3, rx=0.8)
        g.text(x + w / 2, 10.4, cid, size=2.3, weight="bold", anchor="middle")
        g.text(x + w / 2, 13.8, lab, anchor="middle", fill="#333333", size=1.9)
        x += w + 0.6
    g.line(92.5, 16.2, 92.5, 21.4, arrow=True)
    g.rect(64.0, 22.0, 57.0, 10.0, fill="#FFFFFF", stroke="#333333", sw=0.3, rx=0.8)
    g.text(92.5, 25.8, "Supported · Contradicted · NotComparable · NotApplicable", size=1.9, anchor="middle")
    g.text(92.5, 29.6, "+ mismatch type; scored against admissible verdicts", size=1.9, anchor="middle", fill=GREY, style="italic")
    g.close()
    g.open("panel-c")
    xs = [1.0, 42.0, 83.0]
    heads = ["Control (P-none)", "Value swap (3,000 items)", "Record swap (95-item panel)"]
    cards = [("GHG Scope 1", "1,150.4962 t", False, False, "admits: Supported", "claim implicit in page text"),
             ("GHG Scope 1", "2,087.1121 t", False, True, "admits: Contradicted or NotComparable", "Scope-2 value, label unchanged"),
             ("GHG Scope 2", "2,087.1121 t", True, True, "admits: NotComparable", "claim stated; record keeps its label")]
    for x, hd, (ind, val, hi, hv, adm, note) in zip(xs, heads, cards):
        g.text(x, 43.0, hd, weight="bold")
        record_card(g, "card-" + hd.split()[0].lower(), x, 45.0, 24.0, "record shown", ind, val, "consolidated · 2025", hi_ind=hi, hi_val=hv)
        g.text(x, 65.4, adm)
        g.text(x, 69.2, note, fill=GREY if x == 1.0 else VERM, size=1.9)
    g.close()
    return g


def main(v):
    g = {"A": variant_a, "B": variant_b}[v]()
    svg = OUT / f"fig_overview_{v}.svg"
    svg.write_text(g.render(), encoding="utf-8")
    doc = pymupdf.open(svg)
    pdf = pymupdf.open("pdf", doc.convert_to_pdf())
    pdf.save(OUT / f"fig_overview_{v}.pdf")
    pdf[0].get_pixmap(dpi=260).save(OUT / f"fig_overview_{v}.png")
    print("->", svg, pdf[0].rect)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "A")
