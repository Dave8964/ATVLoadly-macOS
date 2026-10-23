# Apple sign-in compatibility candidate

Uses official PlumeImpactor v2.7.1-patch.4 (edec5b665d1d2a1dcb51a519079c2012e359dddf)
with macOS authentication identity and per-account Anisette state. This is an
experimental repair for initial Apple ID sign-in failures; error -80046 has not
been verified resolved. No live Apple ID login or new Anisette service test was
performed during preparation.

New sign-ins use upstream's new default service https://mac-ani.jkcoxson.com.
Only proceed if you agree to its use for authentication provisioning data.
Existing legacy provisioning state remains supported; no automatic account or
pairing reset is performed. Keep a backup before trying this candidate.

The old global Reset Anisette Data dashboard button is incompatible with the
new engine's requirement to select an account; do not use it. No reset is needed
merely to install this candidate. If targeted reset is needed, stop and obtain
account-specific instructions; it invalidates that account's prior login state.

This candidate is a prerelease and does not replace the stable automatic feed.
