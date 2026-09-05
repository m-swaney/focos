"""Ten icon concepts for focos in the Tokyo Night / Omarchy language. Writes SVGs and a contact sheet."""

from pathlib import Path

BG = "#1a1b26"
BG2 = "#24283b"
BORDER = "#292e42"
INK = "#c0caf5"
MUTED = "#565f89"
BLUE = "#7aa2f7"
GREEN = "#9ece6a"
ORANGE = "#ff9e64"
LIME = "#b9f27c"
YELLOW = "#e0af68"
MONO = "JetBrains Mono, Cascadia Mono, Consolas, monospace"

OUT = Path(__file__).parent


def svg(body: str, bg: str = BG, rx: int = 10) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">'
        f'<rect width="64" height="64" rx="{rx}" fill="{bg}"/>{body}</svg>'
    )


# Hand-drawn glyph paths (no font dependency).
F_GLYPH = "M36 16h-4a7 7 0 0 0-7 7v4h-5v6h5v15h7V33h7v-6h-7v-3a1 1 0 0 1 1-1h3z"

CONCEPTS = [
    (
        "01-prompt",
        "Prompt",
        "The shell prompt with a live cursor block. Pure Omarchy.",
        svg(
            f'<path d="M14 20l12 12-12 12" fill="none" stroke="{BLUE}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<rect x="32" y="36" width="18" height="10" fill="{GREEN}"/>'
        ),
    ),
    (
        "02-ledger-f",
        "Ledger f",
        "The current mark, refined: mono f inside a hairline frame, green tick in the corner.",
        svg(
            f'<rect x="6" y="6" width="52" height="52" rx="4" fill="none" stroke="{BORDER}" stroke-width="2"/>'
            f'<path d="{F_GLYPH}" fill="{BLUE}"/>'
            f'<rect x="42" y="44" width="6" height="6" fill="{GREEN}"/>'
        ),
    ),
    (
        "03-bracket-f",
        "Bracket f",
        "A TUI pane title: [f] in square brackets.",
        svg(
            f'<path d="M20 14h-6v36h6" fill="none" stroke="{MUTED}" stroke-width="4" stroke-linejoin="round"/>'
            f'<path d="M44 14h6v36h-6" fill="none" stroke="{MUTED}" stroke-width="4" stroke-linejoin="round"/>'
            f'<path d="M37 19h-3a5 5 0 0 0-5 5v3h-4v5h4v13h6V32h5v-5h-5v-2a1 1 0 0 1 1-1h1z" fill="{BLUE}"/>'
        ),
    ),
    (
        "04-sparkline",
        "Sparkline",
        "Net worth over time: a rising line with a lit end point, inside a hairline frame.",
        svg(
            f'<rect x="6" y="6" width="52" height="52" rx="4" fill="none" stroke="{BORDER}" stroke-width="2"/>'
            f'<path d="M14 44l10-8 8 4 10-14 8 2" fill="none" stroke="{BLUE}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="50" cy="28" r="4" fill="{GREEN}"/>'
        ),
    ),
    (
        "05-entities",
        "Entities",
        "Three bars in the entity colours: Personal, Business, Rental.",
        svg(
            f'<rect x="13" y="30" width="10" height="20" fill="{BLUE}"/>'
            f'<rect x="27" y="40" width="10" height="10" fill="{ORANGE}"/>'
            f'<rect x="41" y="18" width="10" height="32" fill="{LIME}"/>'
            f'<rect x="12" y="52" width="40" height="2" fill="{MUTED}"/>'
        ),
    ),
    (
        "06-grid",
        "Grid",
        "The dashboard itself: four cards, one lit.",
        svg(
            f'<rect x="12" y="12" width="18" height="18" rx="2" fill="{BLUE}"/>'
            f'<rect x="34" y="12" width="18" height="18" rx="2" fill="none" stroke="{MUTED}" stroke-width="2"/>'
            f'<rect x="12" y="34" width="18" height="18" rx="2" fill="none" stroke="{MUTED}" stroke-width="2"/>'
            f'<rect x="34" y="34" width="18" height="18" rx="2" fill="none" stroke="{MUTED}" stroke-width="2"/>'
        ),
    ),
    (
        "07-dollar-prompt",
        "Dollar prompt",
        "The $ shell prompt, which happens to be a dollar sign, with a cursor.",
        svg(
            f'<text x="13" y="47" font-family="{MONO}" font-size="40" font-weight="700" fill="{BLUE}">$</text>'
            f'<rect x="38" y="36" width="14" height="10" fill="{GREEN}"/>'
        ),
    ),
    (
        "08-range",
        "Range",
        "The retirement range mark: a band, a darker core, and the median tick.",
        svg(
            f'<rect x="10" y="27" width="44" height="10" rx="1" fill="{BLUE}" opacity="0.35"/>'
            f'<rect x="20" y="27" width="22" height="10" rx="1" fill="{BLUE}"/>'
            f'<rect x="30" y="21" width="4" height="22" fill="{INK}"/>'
            f'<rect x="10" y="44" width="44" height="2" fill="{MUTED}"/>'
        ),
    ),
    (
        "09-window",
        "Window",
        "An Omarchy window: hairline frame, title bar, the f glyph as content.",
        svg(
            f'<rect x="6" y="8" width="52" height="48" rx="3" fill="{BG2}" stroke="{BORDER}" stroke-width="2"/>'
            f'<rect x="6" y="8" width="52" height="10" rx="3" fill="{BORDER}"/>'
            f'<rect x="11" y="12" width="3" height="3" fill="{GREEN}"/><rect x="16" y="12" width="3" height="3" fill="{YELLOW}"/>'
            f'<path d="M35 24h-3a5 5 0 0 0-5 5v3h-4v5h4v13h6V37h5v-5h-5v-2a1 1 0 0 1 1-1h1z" fill="{BLUE}"/>'
        ),
    ),
    (
        "10-focos-cursor",
        "focos cursor",
        "The word set small in mono with a block cursor, like a terminal title.",
        svg(
            f'<text x="9" y="41" font-family="{MONO}" font-size="19" font-weight="700" fill="{INK}" letter-spacing="-0.5">focos</text>'
            f'<rect x="9" y="46" width="46" height="2" fill="{BORDER}"/>'
            f'<rect x="43" y="46" width="10" height="2" fill="{GREEN}"/>'
        ),
    ),
]

for key, name, blurb, markup in CONCEPTS:
    (OUT / f"concept-{key}.svg").write_text(markup, encoding="utf-8")

cards = "\n".join(
    f"""<div class="c">
      <div class="row"><img src="concept-{key}.svg" width="128" height="128"><img src="concept-{key}.svg" width="48" height="48"><img src="concept-{key}.svg" width="24" height="24"></div>
      <div class="n">{i + 1:02d} · {name}</div>
      <div class="b">{blurb}</div>
    </div>"""
    for i, (key, name, blurb, _) in enumerate(CONCEPTS)
)

(OUT / "index.html").write_text(
    f"""<!doctype html><html><head><meta charset="utf-8"><title>focos icon concepts</title>
<style>
  body{{margin:0;background:#13141c;color:#c0caf5;font-family:{MONO};padding:28px}}
  h1{{font-size:14px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#565f89;margin:0 0 20px}}
  .g{{display:grid;grid-template-columns:repeat(5,1fr);gap:16px}}
  .c{{background:#1a1b26;border:1px solid #292e42;border-radius:4px;padding:16px}}
  .row{{display:flex;align-items:flex-end;gap:14px;margin-bottom:12px}}
  .row img{{display:block;border-radius:14px}} .row img[width="48"]{{border-radius:8px}} .row img[width="24"]{{border-radius:4px}}
  .n{{font-size:13px;font-weight:700;margin-bottom:4px}}
  .b{{font-size:11px;line-height:1.5;color:#a9b1d6}}
</style></head><body>
<h1>focos icon concepts · Tokyo Night</h1>
<div class="g">{cards}</div>
</body></html>""",
    encoding="utf-8",
)
print("wrote", len(CONCEPTS), "concepts")
