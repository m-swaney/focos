"""focos icon concepts, second pass. Rules, taken from the app itself:
- 4px corners, 1px hairline border, panel surface on page background (a card).
- Thin strokes (2.5 to 3 on a 64 grid), never chunky fills.
- Accent blue for the mark, green only for the live dot or cursor, muted for structure.
- Mono letterforms, a title-rule motif from the card headers.
- One idea per icon.
"""

from pathlib import Path

PAGE, PANEL, PANEL2, HAIR = "#13141c", "#1a1b26", "#24283b", "#292e42"
INK, SEC, MUTED = "#c0caf5", "#a9b1d6", "#565f89"
BLUE, GREEN = "#7aa2f7", "#9ece6a"
MONO = "JetBrains Mono, Cascadia Mono, Consolas, monospace"
OUT = Path(__file__).parent
SW = 3  # stroke width on the 64 grid


def card(inner, title_rule=True):
    """A focos card as the icon body: hairline frame, optional title rule."""
    rule = f'<rect x="7" y="7" width="50" height="11" rx="1" fill="{PANEL2}"/><rect x="7" y="18" width="50" height="1" fill="{HAIR}"/>' if title_rule else ""
    return f'<rect x="6" y="6" width="52" height="52" rx="4" fill="{PANEL}" stroke="{HAIR}" stroke-width="2"/>{rule}{inner}'


def svg(body, bg=PAGE):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64"><rect width="64" height="64" rx="4" fill="{bg}"/>{body}</svg>'


def ring(cx, cy, r, color, w=SW):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{w}"/>'


def label_dots(x, y, n, color=MUTED):
    """Tiny 'uppercase label' suggested by dots, as the title rule text."""
    return "".join(f'<rect x="{x + i * 4}" y="{y}" width="2.5" height="2.5" fill="{color}"/>' for i in range(n))


# mono f as a thin stroked path (not filled)
F_STROKE = f'<path d="M37 21h-4a5 5 0 0 0-5 5v20M23 32h11" fill="none" stroke="{BLUE}" stroke-width="{SW}" stroke-linecap="round" stroke-linejoin="round"/>'
F_STROKE_SMALL = f'<path d="M36 25h-3a4 4 0 0 0-4 4v17M25 35h9" fill="none" stroke="{BLUE}" stroke-width="{SW}" stroke-linecap="round" stroke-linejoin="round"/>'

C = [
    ("a-card-reticle", "Card reticle",
     "A focos card whose content is a thin reticle. The title rule is the app's card header.",
     svg(card(label_dots(11, 11.5, 4) + ring(32, 37, 10, BLUE) + f'<path d="M32 22v6M32 46v6M17 37h6M41 37h6" stroke="{BLUE}" stroke-width="{SW}" stroke-linecap="round"/><circle cx="32" cy="37" r="2.5" fill="{GREEN}"/>'))),
    ("b-card-f", "Card f",
     "The card with a stroked mono f and a green text cursor under it.",
     svg(card(label_dots(11, 11.5, 4) + F_STROKE_SMALL + f'<rect x="24" y="49" width="14" height="2.5" fill="{GREEN}"/>'))),
    ("c-card-brackets", "Card brackets",
     "Focus brackets and a lock dot inside the card.",
     svg(card(label_dots(11, 11.5, 4) + f'<path d="M19 30v-5h5M40 25h5v5M45 44v5h-5M24 49h-5v-5" fill="none" stroke="{BLUE}" stroke-width="{SW}" stroke-linecap="round" stroke-linejoin="round"/><circle cx="32" cy="37" r="2.5" fill="{GREEN}"/>'))),
    ("d-card-prompt", "Card prompt",
     "A terminal card: chevron and a block cursor, thin.",
     svg(card(label_dots(11, 11.5, 4) + f'<path d="M18 29l8 8-8 8" fill="none" stroke="{BLUE}" stroke-width="{SW}" stroke-linecap="round" stroke-linejoin="round"/><rect x="31" y="40" width="12" height="3" fill="{GREEN}"/>'))),
    ("e-card-stat", "Card stat",
     "A stat cell: label, big value bar in accent, sub line. The dashboard in miniature.",
     svg(card(label_dots(11, 11.5, 4) + f'<rect x="14" y="27" width="10" height="2.5" fill="{MUTED}"/><rect x="14" y="34" width="28" height="5" fill="{BLUE}"/><rect x="14" y="45" width="18" height="2.5" fill="{MUTED}"/><rect x="46" y="45" width="4" height="2.5" fill="{GREEN}"/>'))),
    ("f-card-trend", "Card trend",
     "The net worth card: a thin rising line with the last point lit.",
     svg(card(label_dots(11, 11.5, 4) + f'<path d="M14 47l9-7 7 3 9-10 8 3" fill="none" stroke="{BLUE}" stroke-width="{SW}" stroke-linecap="round" stroke-linejoin="round"/><circle cx="47" cy="36" r="3" fill="{GREEN}"/>'))),
    ("g-ring-rule", "Ring on rule",
     "No card. A thin focus ring on the page with the median tick in green, from the Plan chart.",
     svg(f'<rect x="10" y="31.5" width="44" height="1.5" fill="{HAIR}"/>' + ring(32, 32, 13, BLUE) + f'<rect x="30.5" y="22" width="3" height="20" fill="{GREEN}"/>')),
    ("h-fo-thin", "fo, thin",
     "Stroked mono f next to a thin ring o. The name, set in the app's letterforms.",
     svg(f'<path d="M31 17h-4a5 5 0 0 0-5 5v25M16 31h11" fill="none" stroke="{BLUE}" stroke-width="{SW}" stroke-linecap="round" stroke-linejoin="round"/>' + ring(42, 38, 8, BLUE) + f'<circle cx="42" cy="38" r="2" fill="{GREEN}"/>')),
    ("i-hairline-lens", "Hairline lens",
     "Two thin rings, accent outside and muted inside, green core. Quiet.",
     svg(ring(32, 32, 19, BLUE) + ring(32, 32, 10, MUTED, 2) + f'<circle cx="32" cy="32" r="3" fill="{GREEN}"/>')),
    ("j-frame-dot", "Frame dot",
     "The card frame alone with one lit point: the smallest possible focos.",
     svg(card(f'<circle cx="32" cy="32" r="4" fill="{BLUE}"/><circle cx="32" cy="32" r="1.5" fill="{GREEN}"/>', title_rule=False))),
    ("k-grid-card", "Grid card",
     "Four cards in a card, one in focus. The layout as a glyph.",
     svg(card(f'<rect x="13" y="24" width="17" height="12" rx="1.5" fill="none" stroke="{BLUE}" stroke-width="2.5"/><rect x="34" y="24" width="17" height="12" rx="1.5" fill="none" stroke="{HAIR}" stroke-width="2"/><rect x="13" y="40" width="17" height="12" rx="1.5" fill="none" stroke="{HAIR}" stroke-width="2"/><rect x="34" y="40" width="17" height="12" rx="1.5" fill="none" stroke="{HAIR}" stroke-width="2"/><circle cx="21.5" cy="30" r="2" fill="{GREEN}"/>', title_rule=False))),
    ("l-wordmark", "Wordmark",
     "focos with a cursor, for the sidebar and large sizes; pairs with any glyph above.",
     svg(f'<text x="8" y="39" font-family="{MONO}" font-size="17" font-weight="700" fill="{INK}" letter-spacing="-0.6">focos</text><rect x="8" y="44" width="48" height="1.5" fill="{HAIR}"/><rect x="44" y="43" width="12" height="3" fill="{GREEN}"/>')),
]

for key, name, blurb, markup in C:
    (OUT / f"v2-{key}.svg").write_text(markup, encoding="utf-8")


def mock(key):
    """Show the icon where it will live: sidebar wordmark and a tab-bar cell."""
    return f"""<div class="mock">
      <div class="side"><img src="v2-{key}.svg" width="18" height="18"><span class="wm">focos</span><span class="lab">chief of staff</span></div>
      <div class="tabs"><div class="tab on"><img src="v2-{key}.svg" width="18" height="18"><span>Today</span></div><div class="tab"><span class="ph"></span><span>Wealth</span></div><div class="tab"><span class="ph"></span><span>Plan</span></div></div>
    </div>"""


cards = "\n".join(
    f'<div class="c"><div class="row"><img src="v2-{k}.svg" width="112" height="112"><img src="v2-{k}.svg" width="44" height="44"><img src="v2-{k}.svg" width="22" height="22"></div>{mock(k)}<div class="n">{chr(65+i)} · {n}</div><div class="b">{b}</div></div>'
    for i, (k, n, b, _) in enumerate(C)
)
(OUT / "index2.html").write_text(
    f"""<!doctype html><html><head><meta charset="utf-8"><title>focos icons, second pass</title><style>
body{{margin:0;background:#13141c;color:#c0caf5;font-family:{MONO};padding:24px}}
h1{{font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#565f89;margin:0 0 16px}}
.g{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
.c{{background:#1a1b26;border:1px solid #292e42;border-radius:4px;padding:14px}}
.row{{display:flex;align-items:flex-end;gap:12px;margin-bottom:12px}} .row img{{display:block}}
.mock{{border:1px solid #292e42;border-radius:4px;background:#13141c;margin-bottom:10px;overflow:hidden}}
.side{{display:flex;align-items:baseline;gap:8px;padding:8px 10px;border-bottom:1px solid #292e42}} .side img{{align-self:center}}
.wm{{font-size:14px;font-weight:700}} .lab{{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:#565f89}}
.tabs{{display:grid;grid-template-columns:repeat(3,1fr)}} .tab{{display:flex;flex-direction:column;align-items:center;gap:3px;padding:6px 0;font-size:9px;color:#565f89;position:relative}}
.tab.on{{color:#c0caf5}} .tab.on::before{{content:"";position:absolute;top:0;left:12px;right:12px;height:2px;background:#7aa2f7}}
.ph{{display:block;width:18px;height:18px;border:1.5px solid #565f89;border-radius:3px;opacity:.5}}
.n{{font-size:12px;font-weight:700;margin-bottom:3px}} .b{{font-size:11px;line-height:1.45;color:#a9b1d6}}
</style></head><body><h1>focos icons · second pass · card language, thin strokes, accent + live green</h1><div class="g">{cards}</div></body></html>""",
    encoding="utf-8",
)
print("wrote", len(C))
