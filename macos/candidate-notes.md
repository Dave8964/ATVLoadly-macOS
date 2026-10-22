# ATVLoadly macOS test candidate

This release is for verification and is not a finished self-updating distribution.
It includes native Apple Silicon binaries built from the newest official stable
ATVLoadly source detected by the workflow. The update archive and manifest are
signed with the dedicated Sparkle Ed25519 key.

Update installation remains disabled until application/data backup, job quiescing,
health validation and automatic rollback are implemented and tested. Cold-login
startup and actual IPA installation/renewal have not yet been qualified.

Back up your existing configuration and pairing records. Do not replace a working
installation expecting unattended updates from this candidate.
