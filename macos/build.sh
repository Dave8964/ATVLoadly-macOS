#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ "$(uname -s)" = Darwin ]]
[[ "$(uname -m)" = arm64 ]] || { echo "This build currently supports Apple Silicon only" >&2; exit 1; }
VERSION="$(git describe --tags --exact-match HEAD)"
PLUME_TAG="$(python3 macos/select-plume.py "$VERSION" Dockerfile)"
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
if [[ "$PLUME_TAG" = v2.7.1-patch.4 ]]; then
 [[ "$(git -C "$BUILD/PlumeImpactor" rev-parse HEAD)" = edec5b665d1d2a1dcb51a519079c2012e359dddf ]]
 (cd "$BUILD/PlumeImpactor" && cargo test --locked -p plume_store --lib anisette_paths)
fi
if [[ ! -f "$BUILD/Sparkle.tar.xz" ]]; then
 curl -fL https://github.com/sparkle-project/Sparkle/releases/download/2.10.0/Sparkle-2.10.0.tar.xz -o "$BUILD/Sparkle.tar.xz"
fi
printf '%s  %s\n' c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c "$BUILD/Sparkle.tar.xz" | shasum -a 256 -c -
mkdir -p "$SPARKLE"
tar -xf "$BUILD/Sparkle.tar.xz" -C "$SPARKLE"
(cd web/static && npm ci --no-audit --no-fund && npm test && npm run build)
go test ./...
go test -race ./internal/nativeupdate ./internal/task ./web
(cd "$BUILD/PlumeImpactor" && cargo build --locked --release -p plumesign)
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/bin" "$APP/Contents/Frameworks"
MACOSX_DEPLOYMENT_TARGET=13.0 CGO_CFLAGS="-mmacosx-version-min=13.0" CGO_LDFLAGS="-mmacosx-version-min=13.0" GOOS=darwin GOARCH=arm64 CGO_ENABLED=1 go build -trimpath -ldflags "-X github.com/bitxeno/atvloadly/internal/app/build.Version=$VERSION -X github.com/bitxeno/atvloadly/internal/app/build.Commit=$(git rev-parse HEAD) -X github.com/bitxeno/atvloadly/internal/app/build.Mode=production" -o "$APP/Contents/Resources/bin/atvloadly" .
(cd macos/update-agent && go test -race ./... && go build -trimpath -o "$APP/Contents/Resources/bin/update-agent" .)
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
codesign --force --sign - "$APP/Contents/Resources/bin/update-agent"
codesign --force --sign - "$APP"
codesign --verify --deep --strict "$APP"
for executable in "$APP/Contents/MacOS/ATVLoadly" "$APP/Contents/Resources/bin/atvloadly" "$APP/Contents/Resources/bin/plumesign" "$APP/Contents/Resources/bin/update-agent"; do lipo "$executable" -verify_arch arm64; done
python3 macos/smoke.py "$APP"
file "$APP/Contents/Resources/bin/atvloadly" "$APP/Contents/Resources/bin/plumesign" "$APP/Contents/MacOS/ATVLoadly"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$OUT/ATVLoadly-${VERSION}-macos-arm64.zip"
shasum -a 256 "$OUT/ATVLoadly-${VERSION}-macos-arm64.zip" > "$OUT/SHA256SUMS"

printf "Verified application: %s\n" "$APP"
