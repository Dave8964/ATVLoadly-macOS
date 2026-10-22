# Native integration

Build from the integration repository with `./build.sh v0.7.3`. The build derives
PlumeImpactor's tag from upstream's Dockerfile, verifies the Sparkle distribution
checksum, runs Go/frontend/helper tests, compiles native binaries, verifies arm64
architecture and bundle signatures, and runs isolated HTTP startup smoke tests.
No Linux binaries or Docker runtime are used. Upstream worktrees/build caches
and output are excluded from Git.

The menu app installs a direct-executable user launch agent at
`~/Library/LaunchAgents/local.atvloadly.native.backend.plist`. It preserves an
existing `local.atvloadly.agent` service and will not silently take over its live
database. Login startup uses SMAppService. The agent declares the main app in
`AssociatedBundleIdentifiers` so macOS can attribute Local Network permission
to it, following Apple TN3179. Service data lives in
`~/Library/Application Support/ATVLoadly/data`; pairing data retains upstream's
`~/.config/PlumeImpactor` and lockdown locations. The initial transition from an
existing installation requires an approved final backup and service cutover.

## Update transaction

Sparkle handles HTTPS retrieval, signature verification, compatible-architecture
selection, version comparison, notification state, replacement and relaunch.
A dedicated Ed25519 public key is embedded in every app; its private counterpart
is stored in Keychain locally and as an Actions secret for the isolated signing job.
Feeds, archives and release notes are signed and checked before extraction.

The app's termination delegate runs the native update agent before allowing a
replacement. Its authenticated control endpoint atomically rejects an update
while installations are queued or active, or pairing/login/install sessions are
open. The agent stops launchd supervision, waits for backend exit, copies the app,
data, settings and pairing records, checks code signatures and SQLite integrity,
and records expected app/source/signing-identity counts. Shutdown flushes settings
and checkpoints SQLite before backup. The old app is retained.

The replacement starts in probation, with installations and scheduled jobs blocked.
The independent watchdog verifies bundle build, upstream version, DB-backed HTTP
readiness, record counts and code signatures before committing. It also checks
every original database column and row, protected key/configuration files, and
existing settings values; additive upstream migrations are allowed. Unhealthy builds
time out and restore the previous app and data. Failed replacement data is retained
for diagnosis. Once jobs may have resumed, ambiguous commit failures are reported
for attention rather than rolling back underneath a signing operation. Interrupted
transactions restart their locked watchdog when the backend or menu app launches.
The standard database layout `data/app.db` is required; unsupported layouts fail
preparation safely. Backups and watchdog diagnostics live in the private `updates/`
directory alongside application data.

## Automation and qualification

The workflow detects official stable upstream releases, applies checked patches
to fresh source and builds on Apple Silicon macOS runners. Failed patches/tests
prevent publication. Versions and an integration fingerprint suppress repeat builds.
Candidate releases are prereleases. Only after end-to-end qualification should
`MACOS_RELEASES_QUALIFIED=true` be set in repository Actions variables; thereafter
compatible releases automatically update the stable feed without a manual rebuild.

Source release notes are included. A successful-sync record is refreshed every
14 days to keep repository activity current. Workflow/auth/signing failures remain
visible in Actions. Hosting and account access remain prerequisites for delivery.

## Verification limits

Local checks cover Go/frontend/Rust/Swift compilation, code-signing integrity,
isolated HTTP startup, mDNS address updates and resume decisions, stable release
selection, installation exclusion, probation, healthy commit and failed-update
filesystem rollback. Two Apple TVs were discovered from copied pairing records,
and read-only communication succeeded. No live configuration was reset.

Live qualification on October 22 verified a full signed Sparkle update to stable
build 8 through the permanent feed, healthy relaunch with all 12 app/history records
preserved, Nuvio download/sign/install and renewals on both TVs, and pairing across
user-confirmed sleep/wake and a Mac restart. Cold-login startup appeared very fast
to the user; process launch and first backend-ready response share the same logged
second. Exact login-to-ready latency was not instrumented. The previous pre-main
delay's original cause was not established. The sleep test retained connectivity,
so forced network-outage recovery and destructive live rollback are not claimed.

Normal workflow 39780384671 passed every stage. Qualified detection run
39782213025 correctly skipped unchanged inputs. The repository qualification
variable is enabled; the installed app uses the permanent stable feed with no
candidate override. Failures on incompatible future upstream changes preserve the
last published release. No paid Developer ID certificate is assumed: bundles use
ad-hoc code signatures and updates are authenticated by Sparkle Ed25519 signatures.
