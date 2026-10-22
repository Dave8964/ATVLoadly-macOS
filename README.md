# ATVLoadly for macOS — release qualification in progress

Native Apple Silicon integration for [bitxeno/atvloadly](https://github.com/bitxeno/atvloadly).
Verified base: **v0.7.3**. Requires macOS 13 or newer.

The application includes a Swift menu-bar controller, supervised Go backend,
compiled Vue frontend, native PlumeImpactor and Sparkle 2.10.0. The updater uses
signed manifests and archives, excludes active installations/pairing/login sessions,
backs up the stopped application's data, validates the replacement in probation,
and restores the prior application/data after failed health checks.

Live qualification has verified a signed Sparkle replacement/relaunch, preservation
of all current app records and pairing data, Nuvio installation and renewal on two
Apple TVs, and startup after a real Mac restart. The backend answered ready in the
same logged second as process launch; exact login-to-ready latency was not measured.
Rollback is covered by isolated filesystem tests; destructive live rollback has
not been forced. The permanent stable feed remains gated until the full normal
publication workflow passes. Existing installations require explicit cutover approval.

Build on an Apple Silicon Mac with Command Line Tools, Go 1.26.6, Node/npm and
Rust 1.97.1:

```sh
./build.sh v0.7.3
```

The build checks out clean upstream source, applies the macOS patch, tests and
builds all native components and writes ZIP/source archives to `output/releases/`.
Apps are staged outside cloud-synced folders to prevent file-provider metadata
from invalidating signatures. The local signing identity is ad-hoc; no paid Apple
Developer certificate is assumed. Sparkle Ed25519 signatures authenticate updates.

The GitHub workflow polls official releases every six hours and compares stable
semantic versions. Unchanged upstream/integration inputs do not rebuild. New
inputs must pass patch application, compilation, tests, packaging and signing on
fresh runners. Signing credentials are available only in a separate signing job.
Until `MACOS_RELEASES_QUALIFIED=true`, releases are explicitly marked prereleases.
After one-time end-to-end qualification, successful builds publish the stable
signed feed used by installed applications. Incompatible changes stop publication
and preserve the last working release. A periodic successful-sync record keeps
scheduled-workflow repository activity current; failures remain visible in Actions.

Discovery handles address updates and rebuilds its browsers after interface
changes or sleep. Two paired Apple TVs were discovered using copied records, and
read-only device-information requests succeeded on both. Apple TV reconnects can
retry pending signature renewal; transient device failures do not permanently
blacklist IPA source builds. IPA updates remain separate from signature renewal.

Private configuration, databases, logs, Apple IDs, pairing files, signing keys and
backups are excluded from this repository. See [integration notes](macos/README.md)
for operating details and remaining verification gates.

ATVLoadly and the integration use the included AGPL-3.0 license. Sparkle and
PlumeImpactor retain their upstream licenses, included in packaged applications.
