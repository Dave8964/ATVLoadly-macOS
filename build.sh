#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
TAG="${1:-v0.7.3}"
[[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Stable upstream tag required' >&2; exit 1; }
mkdir -p "$ROOT/.build" "$ROOT/output/releases"
SOURCE="$(mktemp -d "$ROOT/.build/upstream.XXXXXX")"
git clone --depth 1 --branch "$TAG" https://github.com/bitxeno/atvloadly.git "$SOURCE"
cp -R "$ROOT/macos" "$SOURCE/macos"
cd "$SOURCE"
git apply --check macos/patches/backend.patch
git apply macos/patches/backend.patch
./macos/build.sh
cp output/*.zip output/SHA256SUMS "$ROOT/output/releases/"
