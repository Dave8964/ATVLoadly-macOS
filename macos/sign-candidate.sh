#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARCHIVES="${1:?archive directory required}"
TAG="${2:?release tag required}"
REPOSITORY="${GITHUB_REPOSITORY:-Dave8964/ATVLoadly-macOS}"
[[ "$TAG" =~ ^macos-v[0-9]+\.[0-9]+\.[0-9]+-(candidate|build)\.[0-9]+$ ]]
[[ "$REPOSITORY" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]
TOOLS="$ROOT/.build/signing-tools"
mkdir -p "$TOOLS"
if [[ ! -f "$TOOLS/Sparkle.tar.xz" ]]; then
 curl -fL https://github.com/sparkle-project/Sparkle/releases/download/2.10.0/Sparkle-2.10.0.tar.xz -o "$TOOLS/Sparkle.tar.xz"
fi
printf '%s  %s\n' c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c "$TOOLS/Sparkle.tar.xz" | shasum -a 256 -c -
tar -xf "$TOOLS/Sparkle.tar.xz" -C "$TOOLS"
KEY_ARGS=(--account ATVLoadly-macOS-Dave8964)
if [[ -n "${SPARKLE_PRIVATE_KEY:-}" ]]; then
 umask 077
 KEY_FILE="$(mktemp /private/tmp/atv-update-key.XXXXXX)"
 trap 'rm -f "$KEY_FILE"' EXIT
 printf '%s' "$SPARKLE_PRIVATE_KEY" > "$KEY_FILE"
 unset SPARKLE_PRIVATE_KEY
 KEY_ARGS=(--ed-key-file "$KEY_FILE")
fi
NOTES="$ROOT/macos/candidate-notes.md"
if [[ "${QUALIFIED_RELEASES:-}" == true ]]; then NOTES="$ROOT/macos/release-notes.md"; fi
cp "$NOTES" "$ARCHIVES/release-body.md"
if [[ -f "$ARCHIVES/upstream-notes.md" ]]; then cat "$ARCHIVES/upstream-notes.md" >> "$ARCHIVES/release-body.md"; fi
for archive in "$ARCHIVES"/*.zip; do
 cp "$ARCHIVES/release-body.md" "${archive%.zip}.md"
done
"$TOOLS/bin/generate_appcast" "${KEY_ARGS[@]}" --download-url-prefix "https://github.com/$REPOSITORY/releases/download/$TAG/" --release-notes-url-prefix "https://github.com/$REPOSITORY/releases/download/$TAG/" "$ARCHIVES"
"$TOOLS/bin/sign_update" "${KEY_ARGS[@]}" --verify "$ARCHIVES/appcast.xml"
(cd "$ARCHIVES" && shasum -a 256 ./*.zip > SHA256SUMS)
