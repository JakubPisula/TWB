### Unreleased
- **Kritischer Dorf-Erkennungs-Bug behoben**: Dörfer werden jetzt zuverlässig erkannt, auch wenn der Server unterschiedliche Seitentypen zurückgibt
  - Mehrstufiges Fallback-System für Dorf-ID-Extraktion hinzugefügt
  - Primär: `quickedit-vn` Elemente von der `overview_villages` Seite parsen
  - Fallback 1: Dorf-IDs aus `TribalWars.updateGameData()` JSON extrahieren
    - **Multi-Dorf-Unterstützung**: Iteriert jetzt über `game_data["villages"]` Mapping um ALLE eigenen Dörfer zu extrahieren
    - Single-Dorf-Fallback: Verwendet `game_data["village"]["id"]` wenn kein villages-Mapping verfügbar ist
    - Behebt Problem bei dem Multi-Dorf-Accounts nur das aktuell ausgewählte Dorf erkannt haben (identifiziert durch Codex Code-Review)
  - Fallback 2: Dorf-IDs aus Config-Datei als letzter Ausweg
  - Regex verbessert um verschiedene HTML-Attribut-Reihenfolgen zu unterstützen (class/data-id und data-id/class)
    - Unterstützt sowohl einfache als auch doppelte Anführungszeichen
    - Groß-/Kleinschreibung unabhängig für mehr Robustheit
    - Erhält Reihenfolge während Duplikate entfernt werden
  - Response-Validierung hinzugefügt um zu erkennen wenn Server falschen Seitentyp zurückgibt
  - Error-Logging mit detaillierter Diagnose für Troubleshooting erweitert
  - Problem behoben bei dem 1-Dorf-Accounts ignoriert wurden wegen Server-Redirect
  - **Ergebnis**: Bot funktioniert jetzt korrekt mit Single- und Multi-Dorf-Accounts unabhängig davon welche Seite der Server zurückgibt
- Added configurable Farm-Beutelimit-Schutz – der Farm-Manager stoppt Farm- und Scout-Läufe automatisch, sobald das Weltlimit erreicht ist (inkl. Margin/Overrides).
- **Automatisches Freischalten von Ressourcen-Sammel-Optionen**: Der Bot schaltet jetzt automatisch höhere Sammel-Slots (2, 3, 4) frei, wenn genügend Ressourcen verfügbar sind
  - Prüft Ressourcenverfügbarkeit vor dem Freischalten
  - Fordert fehlende Ressourcen vom Balancer an, falls aktiviert
  - Aktualisiert Spielstatus automatisch nach erfolgreichem Freischalten
  - Verwendet neue Sammel-Slots sofort nach dem Freischalten
- **Konfigurierbare Sammel-/Farm-Priorität**: Neuer Parameter `prioritize_gathering` im Village-Template
  - Standard (false): Farm-Läufe werden vor Sammel-Operationen ausgeführt
  - Aktiviert (true): Sammel-Operationen haben Vorrang vor Farming
  - Ermöglicht bessere Ressourcen-Management-Strategien pro Dorf
- **Sammel-Optimierung**: Truppen-Status wird nach Sammel-Operationen persistiert
  - Verhindert unnötige API-Aufrufe
  - Verbessert Koordination zwischen Farming und Gathering
  - Reduziert Server-Last und erhöht Effizienz
- **Defence-Flag-Bugfix**: Behebt Endlosschleife beim Setzen von Verteidigungs-Flaggen
  - Interner State wird jetzt manuell aktualisiert nach Flag-Änderung
  - Verhindert wiederholte Flag-Set-Versuche für bereits gesetzte Flags
- Code-Formatierung und Einrückung in mehreren Dateien verbessert

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
