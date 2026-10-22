# ATVLoadly for macOS

This release contains the native menu-bar app, Go backend, compiled web frontend,
native PlumeImpactor signing engine and Sparkle updater. Updates use signed
manifests and archives. Installation waits for signing, pairing and login work to
finish, backs up the application and persistent data, and validates the replacement
before scheduled jobs resume. A failed replacement restores the previous app and
data automatically. Existing records and schedules remain outside the bundle.
