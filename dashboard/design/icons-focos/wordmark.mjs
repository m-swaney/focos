// Builds the focos wordmark icon from real JetBrains Mono Bold outlines.
// The green cursor sits exactly under the second "o", measured from the glyph.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import opentype from "opentype.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const font = opentype.loadSync(path.join(here, "fonts", "JetBrainsMono-Bold.ttf"));

const PAGE = "#13141c", HAIR = "#292e42", INK = "#c0caf5", GREEN = "#9ece6a";
const WORD = "focos";
const SIZE = 16; // px per em on the 64 grid; mono advance is 0.6em so the word is 48 wide
const X0 = 8;
const BASE = 38;
const scale = SIZE / font.unitsPerEm;

// Glyph advance positions.
const glyphs = font.stringToGlyphs(WORD);
let x = X0;
const spans = glyphs.map((g) => {
  const bb = g.getBoundingBox();
  const s = { x, adv: g.advanceWidth * scale, inkL: x + bb.x1 * scale, inkR: x + bb.x2 * scale };
  x += s.adv;
  return s;
});
const secondO = spans[3];

const textPath = font.getPath(WORD, X0, BASE, SIZE).toPathData(2);
const RULE_Y = BASE + 5.5;
const cursorX = secondO.inkL;
const cursorW = secondO.inkR - secondO.inkL;

const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect width="64" height="64" rx="4" fill="${PAGE}"/>
  <path d="${textPath}" fill="${INK}"/>
  <rect x="${X0}" y="${RULE_Y}" width="${(x - X0).toFixed(2)}" height="1.5" fill="${HAIR}"/>
  <rect x="${cursorX.toFixed(2)}" y="${(RULE_Y - 0.75).toFixed(2)}" width="${cursorW.toFixed(2)}" height="3" fill="${GREEN}"/>
</svg>
`;
fs.writeFileSync(path.join(here, "wordmark.svg"), svg);

// Maskable variant: same mark inside the centre 80% safe zone on a full-bleed background.
const maskable = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect width="64" height="64" fill="${PAGE}"/>
  <g transform="translate(6.4 6.4) scale(0.8)">
    <path d="${textPath}" fill="${INK}"/>
    <rect x="${X0}" y="${RULE_Y}" width="${(x - X0).toFixed(2)}" height="1.5" fill="${HAIR}"/>
    <rect x="${cursorX.toFixed(2)}" y="${(RULE_Y - 0.75).toFixed(2)}" width="${cursorW.toFixed(2)}" height="3" fill="${GREEN}"/>
  </g>
</svg>
`;
fs.writeFileSync(path.join(here, "wordmark-maskable.svg"), maskable);

// Small mark: a single zoomed "o" with the cursor beneath it, for the 16px favicon slot where the
// five-glyph wordmark collapses into a smear. Same motif, same measuring approach.
const O_SIZE = 52, O_BASE = 44;
const oScale = O_SIZE / font.unitsPerEm;
const oGlyph = font.stringToGlyphs("o")[0];
const oBB = oGlyph.getBoundingBox();
const oInkW = (oBB.x2 - oBB.x1) * oScale;
const oX = (64 - oInkW) / 2 - oBB.x1 * oScale; // centre the ink, not the advance
const oPath = font.getPath("o", oX, O_BASE, O_SIZE).toPathData(2);
const oInkL = oX + oBB.x1 * oScale;
const O_RULE_Y = O_BASE + 6;
const smallMark = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect width="64" height="64" rx="4" fill="${PAGE}"/>
  <path d="${oPath}" fill="${INK}"/>
  <rect x="${oInkL.toFixed(2)}" y="${(O_RULE_Y - 1.5).toFixed(2)}" width="${oInkW.toFixed(2)}" height="4" fill="${GREEN}"/>
</svg>
`;
fs.writeFileSync(path.join(here, "mark-small.svg"), smallMark);

const MONO = "JetBrains Mono, Cascadia Mono, Consolas, monospace";
const html = `<!doctype html><html><head><meta charset="utf-8"><title>focos wordmark</title><style>
@font-face{font-family:"JetBrains Mono";src:url("fonts/JetBrainsMono-Bold.ttf");font-weight:700}
body{margin:0;background:#13141c;color:#c0caf5;font-family:${MONO};padding:28px;width:900px}
h1{font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#565f89;margin:0 0 16px}
.row{display:flex;align-items:flex-end;gap:20px;margin-bottom:20px} .row img{display:block}
.mock{border:1px solid #292e42;border-radius:4px;background:#13141c;overflow:hidden;width:420px}
.side{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid #292e42}
.wm{font-size:15px;font-weight:700;letter-spacing:-.02em}.lab{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#565f89}
.tabs{display:grid;grid-template-columns:repeat(6,1fr)}.tab{display:flex;flex-direction:column;align-items:center;gap:4px;padding:8px 0;font-size:10px;color:#565f89;position:relative}
.tab.on{color:#c0caf5}.tab.on::before{content:"";position:absolute;top:0;left:12px;right:12px;height:2px;background:#7aa2f7}
.ph{display:block;width:18px;height:18px;border:1.5px solid #565f89;border-radius:3px;opacity:.5}
.home{display:flex;gap:28px;align-items:flex-end;padding:20px;background:#0b0b10;border-radius:4px;width:fit-content}
.app{display:flex;flex-direction:column;align-items:center;gap:6px;font-size:11px;color:#ddd}.app img{border-radius:14px}
.note{font-size:11px;color:#a9b1d6;margin-top:8px}
</style></head><body>
<h1>focos wordmark · cursor under the second o · JetBrains Mono Bold outlines</h1>
<div class="row"><img src="wordmark.svg" width="192" height="192"><img src="wordmark.svg" width="112" height="112"><img src="wordmark.svg" width="64" height="64"><img src="wordmark.svg" width="44" height="44"><img src="wordmark.svg" width="22" height="22"></div>
<div class="row">
  <div class="mock">
    <div class="side"><img src="wordmark.svg" width="20" height="20"><span class="wm">focos</span><span class="lab">family office chief of staff</span></div>
    <div class="tabs"><div class="tab on"><img src="wordmark.svg" width="18" height="18"><span>Today</span></div>${["Wealth", "Portfolio", "Plan", "Sandbox", "Briefs"].map((t) => `<div class="tab"><span class="ph"></span><span>${t}</span></div>`).join("")}</div>
  </div>
  <div class="home"><div class="app"><img src="wordmark.svg" width="60" height="60"><span>focos</span></div><div class="app"><img src="wordmark-maskable.svg" width="60" height="60" style="border-radius:30px"><span>maskable</span></div></div>
</div>
<div class="note">second o ink span: ${secondO.inkL.toFixed(1)} to ${secondO.inkR.toFixed(1)} of 64; cursor placed at the same span.</div>
</body></html>`;
fs.writeFileSync(path.join(here, "wordmark.html"), html);
console.log("second o", secondO.inkL.toFixed(2), secondO.inkR.toFixed(2), "word width", (x - X0).toFixed(2));
