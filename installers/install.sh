#!/bin/sh
# Install focos on macOS (or Linux) without admin rights.
#
#   curl -fsSL https://raw.githubusercontent.com/m-swaney/focos/main/installers/install.sh | sh
#
# Options via environment: FOCOS_DATA_DIR (default ~/focos-home), FOCOS_VERSION (default latest),
# FOCOS_REPO (default m-swaney/focos), FOCOS_DEV=1 (git clone instead of a release), FOCOS_NO_BROWSER=1.
set -eu

DATA_DIR="${FOCOS_DATA_DIR:-$HOME/focos-home}"
VERSION="${FOCOS_VERSION:-latest}"
REPO="${FOCOS_REPO:-m-swaney/focos}"
BASE="$HOME/.focos"
BIN="$BASE/bin"
NODE_DIR="$BASE/node"
mkdir -p "$BASE" "$BIN"
log() { printf '[focos] %s\n' "$*"; }

# ---- uv (Python manager)
if ! command -v uv >/dev/null 2>&1; then
  log "installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
log "ensuring Python 3.13"
uv python install 3.13 >/dev/null

# ---- the app
if [ "${FOCOS_DEV:-0}" = "1" ]; then
  APP="$BASE/app"
  command -v git >/dev/null 2>&1 || { echo "git is required for FOCOS_DEV=1" >&2; exit 1; }
  if [ -d "$APP/.git" ]; then git -C "$APP" pull -q; else git clone -q "https://github.com/$REPO.git" "$APP"; fi
  VER="dev"
else
  if [ "$VERSION" = "latest" ]; then API="https://api.github.com/repos/$REPO/releases/latest"; else API="https://api.github.com/repos/$REPO/releases/tags/$VERSION"; fi
  log "looking up release $VERSION"
  JSON="$(curl -fsSL -H 'User-Agent: focos-installer' "$API")"
  VER="$(printf '%s' "$JSON" | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -1)"
  URL="$(printf '%s' "$JSON" | grep -o '"browser_download_url": *"[^"]*focos-[^"]*\.zip"' | head -1 | sed 's/.*"\(http[^"]*\)"/\1/')"
  SUM="$(printf '%s' "$JSON" | grep -o '"browser_download_url": *"[^"]*focos-[^"]*\.zip\.sha256"' | head -1 | sed 's/.*"\(http[^"]*\)"/\1/')"
  [ -n "$URL" ] || { echo "release $VER has no focos-*.zip asset" >&2; exit 1; }
  APP="$BASE/app-$VER"
  if [ ! -f "$APP/pyproject.toml" ]; then
    ZIP="$BASE/focos-$VER.zip"
    log "downloading focos $VER"
    curl -fsSL "$URL" -o "$ZIP"
    if [ -n "$SUM" ]; then
      EXPECTED="$(curl -fsSL "$SUM" | awk '{print $1}')"
      ACTUAL="$(shasum -a 256 "$ZIP" | awk '{print $1}')"
      [ "$EXPECTED" = "$ACTUAL" ] || { echo "checksum mismatch" >&2; exit 1; }
    fi
    rm -rf "$APP"; mkdir -p "$APP"
    unzip -q "$ZIP" -d "$APP"
    INNER="$(find "$APP" -mindepth 2 -maxdepth 2 -name pyproject.toml | head -1)"
    if [ -n "$INNER" ] && [ ! -f "$APP/pyproject.toml" ]; then D="$(dirname "$INNER")"; mv "$D"/* "$D"/.[!.]* "$APP"/ 2>/dev/null || true; rmdir "$D" 2>/dev/null || true; fi
    rm -f "$ZIP"
  fi
fi
printf '%s\n' "$APP" > "$BASE/app.txt"

# ---- private Node runtime (for the dashboard)
if [ ! -x "$NODE_DIR/bin/node" ]; then
  log "downloading Node.js LTS runtime"
  OS="$(uname -s | tr '[:upper:]' '[:lower:]')"; ARCH="$(uname -m)"
  case "$ARCH" in arm64|aarch64) ARCH=arm64 ;; x86_64) ARCH=x64 ;; esac
  NAME="$(curl -fsSL https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt | grep -o "node-v[0-9.]*-$OS-$ARCH\.tar\.gz" | head -1)"
  [ -n "$NAME" ] || { echo "no Node build for $OS-$ARCH" >&2; exit 1; }
  curl -fsSL "https://nodejs.org/dist/latest-v22.x/$NAME" -o "$BASE/$NAME"
  rm -rf "$BASE/node-tmp"; mkdir -p "$BASE/node-tmp"
  tar -xzf "$BASE/$NAME" -C "$BASE/node-tmp"
  rm -rf "$NODE_DIR"; mv "$BASE/node-tmp"/node-v* "$NODE_DIR"; rm -rf "$BASE/node-tmp" "$BASE/$NAME"
  [ "$OS" = "darwin" ] && xattr -dr com.apple.quarantine "$NODE_DIR" 2>/dev/null || true
fi

# ---- python environment
log "creating the Python environment"
PY="$APP/.venv/bin/python"
[ -x "$PY" ] || uv venv "$APP/.venv" --python 3.13 -q
if [ -f "$APP/uv.lock" ]; then uv sync --project "$APP" --frozen --all-extras --no-dev -q; else uv pip install --python "$PY" -q -e "$APP[all]"; fi

# ---- `focos` command shim
cat > "$BIN/focos" <<'EOF'
#!/bin/sh
APP="$(cat "$HOME/.focos/app.txt")"
exec "$APP/.venv/bin/python" -I -m focos "$@"
EOF
chmod +x "$BIN/focos"
case ":$PATH:" in *":$BIN:"*) ;; *)
  for rc in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.profile"; do
    [ -f "$rc" ] && ! grep -q '.focos/bin' "$rc" && printf '\nexport PATH="$HOME/.focos/bin:$PATH"\n' >> "$rc"
  done
  export PATH="$BIN:$PATH" ;;
esac

# ---- data folder + service
log "initializing your data folder at $DATA_DIR"
"$PY" -I -m focos init --home "$DATA_DIR" --set-default >/dev/null
"$PY" -I -m focos --home "$DATA_DIR" agent render-settings >/dev/null
log "registering the dashboard to start at login"
"$PY" -I -m focos --home "$DATA_DIR" service install >/dev/null || true

log "installed focos $VER"
log "open http://localhost:3100/setup to finish setup (the dashboard may take ~20 s to start the first time)"
if [ "${FOCOS_NO_BROWSER:-0}" != "1" ]; then sleep 5; (open 'http://localhost:3100/setup' 2>/dev/null || xdg-open 'http://localhost:3100/setup' 2>/dev/null || true); fi
