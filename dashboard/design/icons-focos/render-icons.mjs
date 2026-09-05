// Rasterises the focos mark into every app icon target. Run after wordmark.mjs:
//   node design/icons-focos/wordmark.mjs && node design/icons-focos/render-icons.mjs
//   ..\.venv\Scripts\python design/icons-focos/make-favicon.py
// sharp renders the SVG through libvips at each target size, so the output is a true vector
// render rather than a screenshot crop (an earlier browser-capture pass produced a mis-cropped
// apple-icon). sharp cannot write .ico, so make-favicon.py assembles that from the layers here.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const here = path.dirname(fileURLToPath(import.meta.url));
const dash = path.resolve(here, "..", "..");
const PAGE = "#13141c";

const wordmark = path.join(here, "wordmark.svg");
const maskable = path.join(here, "wordmark-maskable.svg");
const small = path.join(here, "mark-small.svg");

// The SVGs are 64x64 user units; density scales the vector render so no upscaling ever happens.
const render = (src, size) =>
  sharp(src, { density: Math.ceil((72 * size) / 64) }).resize(size, size, { fit: "contain" });

const layers = path.join(here, "favicon-layers");
fs.mkdirSync(layers, { recursive: true });

const targets = [
  // The rounded tile keeps its transparent corners for the web app icons.
  { src: wordmark, size: 192, out: path.join(dash, "public/icons/icon-192.png") },
  { src: wordmark, size: 512, out: path.join(dash, "public/icons/icon-512.png") },
  { src: maskable, size: 512, out: path.join(dash, "public/icons/icon-512-maskable.png") },
  // iOS ignores alpha and composites on black, so apple-icon is flattened onto the page colour.
  { src: wordmark, size: 180, out: path.join(dash, "app/apple-icon.png"), flatten: true },
  // favicon.ico layers: the wordmark is illegible at 16px, so that slot uses the zoomed "o".
  { src: small, size: 16, out: path.join(layers, "16.png"), flatten: true },
  { src: wordmark, size: 32, out: path.join(layers, "32.png"), flatten: true },
  { src: wordmark, size: 48, out: path.join(layers, "48.png"), flatten: true },
  { src: wordmark, size: 256, out: path.join(layers, "256.png"), flatten: true },
];

for (const t of targets) {
  let img = render(t.src, t.size);
  if (t.flatten) img = img.flatten({ background: PAGE });
  const info = await img.png({ compressionLevel: 9 }).toFile(t.out);
  console.log(`${path.relative(dash, t.out).replace(/\\/g, "/")}  ${info.width}x${info.height}  ${info.size}b`);
}

// app/icon.svg is the same artwork, served straight to the browser.
fs.copyFileSync(wordmark, path.join(dash, "app/icon.svg"));
console.log("app/icon.svg  <- wordmark.svg");
