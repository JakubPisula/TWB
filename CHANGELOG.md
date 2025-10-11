### Unreleased
- Added configurable Farm-Beutelimit-Schutz – der Farm-Manager stoppt Farm- und Scout-Läufe automatisch, sobald das Weltlimit erreicht ist (inkl. Margin/Overrides).
- Hardened Forced-Peace-Handling und Village-Initialisierung, damit Läufe bei fehlenden Spieldaten sauber abbrechen und Peace-Zeiten zuverlässig greifen.
- WebWrapper mit konfigurierbaren Timeouts & Retries ausgestattet und externe Abfragen (Updater, TWStats) mit HTTP-Timeouts versehen.
- Konsole auf konsistente Logger-Ausgaben umgestellt (statt `print`) und neue Tests für Extractors, Forced-Peace sowie WebWrapper-Retries ergänzt.

### New in 1.6
- Bugfixes
- Found the bug where villages were not detected automatically

### New in 1.5
- Nice configuration dashboard
- Various bug fixes

### New in 1.4.4
- Fixed snob (both systems working again)
- Fixed various crashes and bugs
- Configurable delay between requests (0.7 for fast, 2.0 for very slow)

### New in 1.4.2
- Automatically add new villages once conquered
- Working attack simulator (partially)
- Integrated farm manager into core code
- Few bug fixes

### New in v1.4.1
- Automatic upgrading of out-dated config files
- Removed selenium (inc. Web Driver)
- How-To readme
- Minor bug-fixes

### New in v1.4
- Reworked config methods so the bot works with all config versions (with warnings tho)
- Automatic requesting and sending support
- Attack / resource flag management
- Automatic evacuation of high-profile units (snob, axe)
- Found out why snob recruiting was not working (fix in progress)
- Minor bug-fixes
