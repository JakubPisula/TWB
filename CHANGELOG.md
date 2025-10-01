### Unreleased
- **Fixed critical village detection bug**: Villages are now reliably detected even when the server returns different page types
  - Added multi-layer fallback system for village ID extraction
  - Primary: Parse `quickedit-vn` elements from `overview_villages` page
  - Fallback 1: Extract village ID from `TribalWars.updateGameData()` JSON
  - Fallback 2: Use village IDs from config file as last resort
  - Improved regex to handle different HTML attribute orders (class/data-id)
  - Added response validation to detect when server returns wrong page type
  - Enhanced error logging with detailed diagnostics for troubleshooting
  - Fixed issue where 1-village accounts would have villages ignored due to server redirect
- Added configurable Farm-Beutelimit-Schutz – der Farm-Manager stoppt Farm- und Scout-Läufe automatisch, sobald das Weltlimit erreicht ist (inkl. Margin/Overrides).

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
