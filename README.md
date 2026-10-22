# ATVLoadly for macOS — test candidate

Native Apple Silicon integration for [bitxeno/atvloadly](https://github.com/bitxeno/atvloadly).
Current verified base: **v0.7.3**. Requires macOS 13 or newer.

**This is not yet a finished self-updating distribution.** The candidate compiles
the Go backend, Vue frontend, Swift menu-bar application and matching Rust
PlumeImpactor. Sparkle is bundled, but installation stays disabled until update
backup, install-job exclusion, backend health validation and automatic rollback
are implemented and qualified. Do not replace a working installation with this
candidate expecting unattended updates.

Build on an Apple Silicon Mac with Command Line Tools, Go, Node/npm and Rust:

```sh
./build.sh v0.7.3
```

This checks out clean upstream source, checks/applies the macOS patch, runs tests,
builds native components and writes a ZIP to `output/releases/`. An extracted
signed app is staged under `/private/tmp/atvloadly-build.*` because cloud file
providers can add metadata which invalidates macOS bundle signatures.

The GitHub Actions workflow detects stable upstream releases and builds candidates.
It uploads test artifacts rather than publishing production updates. Patch or
build failures stop the workflow. It has not been qualified as a release service.

The discovery patch handles changed mDNS addresses and removes raw TXT records
from discovery logs. Local tests found two paired Apple TVs with copies of
existing records; read-only device-information requests succeeded on both.
This does not establish successful IPA installation, renewal, or reconnection
after sleep. Manual isolated backend starts were below one second; cold-login
startup and the reported pre-main delay remain unverified.

Private configuration, databases, logs, Apple IDs, pairing files, signing keys and
local backups are excluded from this repository. Existing installations must be
backed up and migrated with explicit user approval. See [integration notes](macos/README.md)
for limitations and release gates.

Code from ATVLoadly and its macOS integration is distributed under the included
AGPL-3.0 license. Sparkle and PlumeImpactor retain their respective upstream licenses.
