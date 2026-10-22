# Native macOS integration — candidate, not production qualified

Base: official ATVLoadly v0.7.3 (`533aee4`). PlumeImpactor is derived from
that release's Dockerfile (v2.7.1-patch.3), never from a Linux executable.
Requires Apple Silicon, macOS 13+, Go, Node/npm, Rust/Cargo and Command Line Tools.

Build: `./macos/build.sh`. The script compiles and tests the frontend and Go
backend, compiles the locked Rust signing engine, compiles the Cocoa controller,
bundles Sparkle 2.10.0 and verifies code signatures. The signed app is staged
under `/private/tmp/atvloadly-build.*` to avoid cloud file-provider FinderInfo
attributes contaminating signatures. The portable ZIP and SHA256SUMS are in
`output/`. Extract the ZIP outside cloud-synced folders before running it.
Ad-hoc signing provides local integrity, not Developer ID identity/notarization.

The menu app supervises a direct Go executable through a per-user launch agent;
SMAppService controls menu-app login startup. It does not replace a loaded
`local.atvloadly.agent` service. No startup delay has been attributed to a root
cause, and no cold-login result is claimed. Native service setup must not be
activated until the existing service and data migration have been reviewed.

Discovery now handles address-update events and omits raw mDNS TXT records from
logs. Tests cover the stale-address regression. Existing upstream pairing,
refresh, deduplication, source tracking and secret-store code is retained.
An isolated copy of the existing pairing records discovered two Apple TVs,
and read-only device-info commands succeeded against both. New pairing,
sleep/reconnection, IPA installation and Nuvio refresh remain unverified. No live signing/installation was initiated during the build.

## Updates

Sparkle is bundled with signed-feed and verify-before-extraction settings.
Set ATV_UPDATE_FEED and ATV_UPDATE_PUBLIC_KEY together to embed a trusted feed.
The UI fails closed when no feed/key exists. Installation is deliberately
blocked by a delegate until application/data backup, install-job quiescing,
replacement health validation and automatic rollback are implemented and tested.
This is an explicit incomplete requirement, not a functioning self-updater.

The macOS candidate workflow polls official releases every six hours, selects
stable SemVer versions, checks macOS patches against a fresh release, runs the
native build and uploads candidates. Patch conflicts/build failures fail the
job. It does not publish appcasts or releases, and it is not enabled until this
repository is hosted on GitHub. Scheduled Actions may be disabled by GitHub after
inactivity and must be monitored; a workflow file alone is not permanent hosting.

## Data and migration

Private backups live outside this source tree in ../output/backups/initial.
They include SQLite snapshots (integrity checked), settings, data encryption keys,
PlumeImpactor records and lockdown records found at the time of backup.
Files have restrictive permissions and are excluded from Git. Do not publish
backup contents, production logs, keys or configuration. Backup hashes cover the
copied snapshots; they do not claim to freeze a still-running production service.

The installed application, launch agents and live databases have not been
replaced. A production migration must first quiesce the old service, take a final
consistent backup, validate migrated data in isolation, and retain the old app.
Do not point two backends at the same production database.

## Remaining release gates

- GitHub authentication and a dedicated release repository.
- Secure update-signing key provisioning and signed release publication.
- Installation interlock, transactional backup and tested health-based rollback.
- Full signed update installation test using old and new bundles.
- Physical Apple TV discovery/pair/reconnect/install and Nuvio renewal tests.
- Real cold-login startup measurement and investigation of the reported delay.
- Review/approval before replacing the existing installation.

`python3 -m unittest discover -s macos/tests -v` validates release selection.
`python3 macos/smoke.py /path/to/ATVLoadly.app` tests three isolated backend
starts and HTTP routes. It does not represent a reboot or real-device test.
