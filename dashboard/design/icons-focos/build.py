"""Twenty icon concepts for focos (pronounced "focus"). Tokyo Night language."""

from pathlib import Path

BG, BG2, BORDER = "#1a1b26", "#24283b", "#292e42"
INK, MUTED = "#c0caf5", "#565f89"
BLUE, GREEN, ORANGE, LIME, YELLOW = "#7aa2f7", "#9ece6a", "#ff9e64", "#b9f27c", "#e0af68"
MONO = "JetBrains Mono, Cascadia Mono, Consolas, monospace"
OUT = Path(__file__).parent

F = "M36 16h-4a7 7 0 0 0-7 7v4h-5v6h5v15h7V33h7v-6h-7v-3a1 1 0 0 1 1-1h3z"
F_SMALL = "M35 24h-3a5 5 0 0 0-5 5v3h-4v5h4v13h6V37h5v-5h-5v-2a1 1 0 0 1 1-1h1z"


def svg(body, bg=BG):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64"><rect width="64" height="64" rx="10" fill="{bg}"/>{body}</svg>'


def ring(cx, cy, r, color, w=4, extra=""):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{w}" {extra}/>'


def corners(x, y, w, h, l, color, sw=4):
    x2, y2 = x + w, y + h
    return (
        f'<path d="M{x} {y+l}V{y}h{l}M{x2-l} {y}h{l}v{l}M{x2} {y2-l}v{l}h-{l}M{x+l} {y2}h-{l}v-{l}" '
        f'fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>'
    )


C = [
    ("01-reticle", "Reticle", "Ring, four ticks, centre dot. Focus, literally.",
     ring(32, 32, 16, BLUE) + f'<path d="M32 8v8M32 48v8M8 32h8M48 32h8" stroke="{BLUE}" stroke-width="4" stroke-linecap="round"/><circle cx="32" cy="32" r="4" fill="{GREEN}"/>'),
    ("02-viewfinder", "Viewfinder", "Camera focus brackets with the lock-on dot.",
     corners(12, 12, 40, 40, 10, BLUE) + f'<circle cx="32" cy="32" r="4" fill="{GREEN}"/>'),
    ("03-bullseye", "Bullseye", "Three rings, green centre.",
     ring(32, 32, 22, MUTED, 3) + ring(32, 32, 13, BLUE) + f'<circle cx="32" cy="32" r="5" fill="{GREEN}"/>'),
    ("04-crosshair-f", "Crosshair f", "The f glyph caught in a crosshair.",
     f'<path d="M32 6v10M32 48v10M6 32h10M48 32h10" stroke="{MUTED}" stroke-width="3" stroke-linecap="round"/>' + ring(32, 32, 19, BORDER, 2) + f'<path d="{F_SMALL}" fill="{BLUE}"/>'),
    ("05-lens", "Lens", "A lens element: thick ring with a highlight and a green core.",
     ring(32, 32, 18, BLUE, 6) + f'<path d="M20 24a14 14 0 0 1 12-6" stroke="{INK}" stroke-width="3" stroke-linecap="round" fill="none"/><circle cx="32" cy="32" r="6" fill="{GREEN}"/>'),
    ("06-viewfinder-f", "Viewfinder f", "Brackets framing the f, like a subject locked in focus.",
     corners(10, 10, 44, 44, 10, MUTED, 3) + f'<path d="{F_SMALL}" fill="{BLUE}"/>'),
    ("07-prompt-ring", "Prompt ring", "Shell chevron pointing at a focus ring.",
     f'<path d="M12 20l10 12-10 12" fill="none" stroke="{BLUE}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>' + ring(42, 32, 10, GREEN, 4) + f'<circle cx="42" cy="32" r="3" fill="{GREEN}"/>'),
    ("08-target-cursor", "Target cursor", "Bullseye with a terminal cursor block.",
     ring(28, 28, 16, BLUE) + f'<circle cx="28" cy="28" r="5" fill="{BLUE}"/><rect x="40" y="42" width="14" height="10" fill="{GREEN}"/>'),
    ("09-spotlight", "Spotlight", "A cone of light landing on one point.",
     f'<path d="M14 10l36 0-14 30h-8z" fill="{BLUE}" opacity="0.22"/><path d="M14 10h36" stroke="{BLUE}" stroke-width="4" stroke-linecap="round"/><circle cx="32" cy="46" r="6" fill="{GREEN}"/>'),
    ("10-depth", "Depth of field", "Three dots, only one in focus.",
     f'<circle cx="16" cy="40" r="7" fill="{MUTED}" opacity="0.5"/><circle cx="48" cy="24" r="7" fill="{MUTED}" opacity="0.5"/><circle cx="32" cy="32" r="9" fill="{BLUE}"/><circle cx="32" cy="32" r="3" fill="{GREEN}"/>'),
    ("11-eye", "Eye", "An eye with a blue iris and green pupil. Watchful chief of staff.",
     f'<path d="M8 32c8-12 16-16 24-16s16 4 24 16c-8 12-16 16-24 16S16 44 8 32z" fill="none" stroke="{INK}" stroke-width="3"/><circle cx="32" cy="32" r="9" fill="{BLUE}"/><circle cx="32" cy="32" r="4" fill="{GREEN}"/>'),
    ("12-magnifier", "Magnifier", "Loupe with a square handle, terminal-blocky.",
     ring(28, 28, 14, BLUE, 5) + f'<path d="M38 38l12 12" stroke="{BLUE}" stroke-width="7" stroke-linecap="round"/><circle cx="28" cy="28" r="4" fill="{GREEN}"/>'),
    ("13-house-ring", "Family office", "A house held in a focus ring.",
     ring(32, 32, 24, BORDER, 2) + f'<path d="M32 16L16 30h5v16h22V30h5z" fill="none" stroke="{BLUE}" stroke-width="4" stroke-linejoin="round"/><rect x="29" y="36" width="6" height="10" fill="{GREEN}"/>'),
    ("14-orbit", "Orbit", "Three entities around one centre.",
     ring(32, 32, 17, BORDER, 2) + f'<circle cx="32" cy="32" r="6" fill="{INK}"/><circle cx="32" cy="15" r="5" fill="{BLUE}"/><circle cx="17" cy="41" r="5" fill="{ORANGE}"/><circle cx="47" cy="41" r="5" fill="{LIME}"/>'),
    ("15-fo", "fo", "The f and o as a mono ligature; the o is the focus ring.",
     f'<path d="M26 18h-3a5 5 0 0 0-5 5v3h-4v5h4v15h6V31h4v-5h-4v-2a1 1 0 0 1 1-1h1z" fill="{BLUE}"/>' + ring(40, 36, 8, GREEN, 5)),
    ("16-grid-focus", "Grid focus", "Nine dots; the centre one is lit and larger.",
     "".join(f'<circle cx="{x}" cy="{y}" r="3" fill="{MUTED}"/>' for x in (18, 32, 46) for y in (18, 32, 46) if (x, y) != (32, 32)) + f'<circle cx="32" cy="32" r="7" fill="{BLUE}"/><circle cx="32" cy="32" r="2.5" fill="{GREEN}"/>'),
    ("17-aperture", "Aperture", "Six blades around an opening.",
     "".join(f'<path d="M32 32L{32+18*__import__("math").cos(a)} {32+18*__import__("math").sin(a)}A18 18 0 0 1 {32+18*__import__("math").cos(a+1.0472)} {32+18*__import__("math").sin(a+1.0472)}z" fill="{BLUE}" opacity="{0.9 if i % 2 else 0.55}"/>' for i, a in enumerate([k * 1.0472 - 1.5708 for k in range(6)])) + f'<circle cx="32" cy="32" r="7" fill="{BG}"/><circle cx="32" cy="32" r="3" fill="{GREEN}"/>'),
    ("18-scope", "Scope", "Reticle with a rising line inside: focus on the trend.",
     ring(32, 32, 20, BLUE) + f'<path d="M32 6v8M32 50v8M6 32h8M50 32h8" stroke="{BLUE}" stroke-width="4" stroke-linecap="round"/><path d="M21 39l7-6 5 3 10-10" fill="none" stroke="{GREEN}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>'),
    ("19-bracket-dot", "Bracket dot", "Square brackets around a single point.",
     f'<path d="M22 14h-8v36h8M42 14h8v36h-8" fill="none" stroke="{MUTED}" stroke-width="4" stroke-linejoin="round"/><circle cx="32" cy="32" r="7" fill="{BLUE}"/><circle cx="32" cy="32" r="2.5" fill="{GREEN}"/>'),
    ("20-ring-cursor", "Ring cursor", "A single focus ring with the cursor block inside, blinking.",
     ring(32, 30, 18, BLUE, 5) + f'<rect x="25" y="26" width="14" height="9" fill="{GREEN}"/>'),
]

for key, name, blurb, body in C:
    (OUT / f"concept-{key}.svg").write_text(svg(body), encoding="utf-8")

cards = "\n".join(
    f'<div class="c"><div class="row"><img src="concept-{k}.svg" width="112" height="112"><img src="concept-{k}.svg" width="40" height="40"><img src="concept-{k}.svg" width="22" height="22"></div><div class="n">{i+1:02d} · {n}</div><div class="b">{b}</div></div>'
    for i, (k, n, b, _) in enumerate(C)
)
(OUT / "index.html").write_text(
    f"""<!doctype html><html><head><meta charset="utf-8"><title>focos icon concepts</title><style>
body{{margin:0;background:#13141c;color:#c0caf5;font-family:{MONO};padding:24px}}
h1{{font-size:13px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#565f89;margin:0 0 16px}}
.g{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px}}
.c{{background:#1a1b26;border:1px solid #292e42;border-radius:4px;padding:14px}}
.row{{display:flex;align-items:flex-end;gap:12px;margin-bottom:10px}}
.row img{{display:block;border-radius:12px}} .row img[width="40"]{{border-radius:7px}} .row img[width="22"]{{border-radius:4px}}
.n{{font-size:12px;font-weight:700;margin-bottom:3px}} .b{{font-size:11px;line-height:1.45;color:#a9b1d6}}
</style></head><body><h1>focos icon concepts · pronounced focus</h1><div class="g">{cards}</div></body></html>""",
    encoding="utf-8",
)
print("wrote", len(C))
