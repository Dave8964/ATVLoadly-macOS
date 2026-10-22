# ATVLoadly macOS test candidate

This release is for qualification and is not yet a production distribution.
It includes native Apple Silicon binaries built from the newest official stable
ATVLoadly source selected by the workflow. The archive, appcast and release notes
are authenticated with the dedicated Sparkle Ed25519 key.

The native update transaction implements job exclusion, application/data backup,
probation, health verification and rollback. Local tests include healthy commit
and forced failed-update rollback. A complete Sparkle installation/relaunch,
cold-login startup and actual IPA installation/renewal still need qualification.
Production update publication remains off until those checks pass.

Back up existing configuration and pairing records. Do not replace a working
installation without an approved final backup and service cutover.
