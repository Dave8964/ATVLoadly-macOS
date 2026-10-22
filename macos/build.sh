#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ "$(uname -s)" = Darwin ]]
[[ "$(uname -m)" = arm64 ]] || { echo "This build currently supports Apple Silicon only" >&2; exit 1; }
VERSION="$(git describe --tags --exact-match HEAD)"
PLUME_TAG="$(sed -nE 's@.*PlumeImpactor/releases/download/([^/]+)/.*@\1@p' Dockerfile | head -1)"
[[ "$PLUME_TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+-patch\.[0-9]+$ ]]
BUILD="$ROOT/.macos-build"
OUT="$ROOT/output"
STAGE="$(mktemp -d /private/tmp/atvloadly-build.XXXXXX)"
APP="$STAGE/ATVLoadly.app"
SPARKLE="$BUILD/Sparkle"
mkdir -p "$BUILD" "$OUT"
if [[ ! -d "$BUILD/PlumeImpactor/.git" ]]; then
 git clone --depth 1 --branch "$PLUME_TAG" https://github.com/bitxeno/PlumeImpactor.git "$BUILD/PlumeImpactor"
fi
[[ "$(git -C "$BUILD/PlumeImpactor" describe --tags --exact-match HEAD)" = "$PLUME_TAG" ]]
if [[ ! -f "$BUILD/Sparkle.tar.xz" ]]; then
 curl -fL https://github.com/sparkle-project/Sparkle/releases/download/2.10.0/Sparkle-2.10.0.tar.xz -o "$BUILD/Sparkle.tar.xz"
fi
printf '%s  %s\n' c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c "$BUILD/Sparkle.tar.xz" | shasum -a 256 -c -
mkdir -p "$SPARKLE"
tar -xf "$BUILD/Sparkle.tar.xz" -C "$SPARKLE"
(cd web/static && npm ci && npm test && npm run build)
go test ./...
(cd "$BUILD/PlumeImpactor" && cargo build --locked --release -p plumesign)
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/bin" "$APP/Contents/Frameworks"
CGO_ENABLED=1 go build -trimpath -ldflags "-X github.com/bitxeno/atvloadly/internal/app/build.Version=$VERSION -X github.com/bitxeno/atvloadly/internal/app/build.Commit=$(git rev-parse HEAD) -X github.com/bitxeno/atvloadly/internal/app/build.Mode=production" -o "$APP/Contents/Resources/bin/atvloadly" .
cp "$BUILD/PlumeImpactor/target/release/plumesign" "$APP/Contents/Resources/bin/"
ditto "$SPARKLE/Sparkle.framework" "$APP/Contents/Frameworks/Sparkle.framework"
swiftc -O -target arm64-apple-macos13 -module-cache-path "$BUILD/swift-cache" -F "$SPARKLE" -framework Cocoa -framework ServiceManagement -framework Sparkle -Xlinker -rpath -Xlinker @executable_path/../Frameworks macos/ATVLoadly.swift -o "$APP/Contents/MacOS/ATVLoadly"
mkdir -p "$APP/Contents/Resources/Licenses"
cp "$ROOT/LICENSE" "$APP/Contents/Resources/Licenses/ATVLoadly.txt"
cp "$BUILD/PlumeImpactor/LICENSE" "$APP/Contents/Resources/Licenses/PlumeImpactor.txt"
cp "$SPARKLE/LICENSE" "$APP/Contents/Resources/Licenses/Sparkle.txt"
export ATV_BUILD_VERSION="${VERSION#v}" ATV_APP_PATH="$APP"
ATV_UPDATE_FEED="${ATV_UPDATE_FEED:-https://github.com/Dave8964/ATVLoadly-macOS/releases/latest/download/appcast.xml}" \
ATV_UPDATE_PUBLIC_KEY="${ATV_UPDATE_PUBLIC_KEY:-$(cat macos/UpdatePublicKey.txt)}" \
python3 macos/info.py
xattr -cr "$APP"
codesign --force --sign - "$APP/Contents/Resources/bin/atvloadly"
codesign --force --sign - "$APP/Contents/Resources/bin/plumesign"
codesign --force --sign - "$APP"
codesign --verify --deep --strict "$APP"
file "$APP/Contents/Resources/bin/atvloadly" "$APP/Contents/Resources/bin/plumesign" "$APP/Contents/MacOS/ATVLoadly"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$OUT/ATVLoadly-${VERSION}-macos-arm64.zip"
shasum -a 256 "$OUT/ATVLoadly-${VERSION}-macos-arm64.zip" > "$OUT/SHA256SUMS"

printf "Verified application: %s\n" "$APP"
