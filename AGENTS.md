# Repository Guidelines

## Project Structure & Module Organization
- `twb.py` boots the bot, reads `config.json`, and wires the managers.
- `core/` hosts shared services for HTTP, caching, I/O, and notifications.
- `game/` implements farming, defence, recruitment, and simulation logic.
- `webmanager/` contains the Flask dashboard plus its `static/` and `templates/`.
- `templates/` holds build/troop presets.
- `tests/` stores `pytest` suites; `cache/` is runtime-only and should remain ignored.
- `tools/` contains developer helper scripts and utilities.
- `scripts/` holds system scripts like backend restart or activation.

## Build, Test, and Development Commands
- `python -m venv env` with the platform-appropriate activate script creates an isolated environment.
- `pip install -r requirements.txt` installs bot and dashboard dependencies.
- `python twb.py` runs the bot and, if needed, triggers the first-run wizard.
- `python -m webmanager.server` serves the local dashboard for monitoring.
- `python -m unittest discover -s tests -p "test_*.py"` runs all tests; add `-v` while debugging.

## Coding Style & Naming Conventions
- Adhere to PEP 8, 4-space indentation, and snake_case module and member names.
- Add type hints and focused docstrings where modules in `core/`, `game/`, and `webmanager/` interact.
- Use the existing `logging.getLogger(...)` pattern; avoid stray prints.
- Keep configuration keys lower_snake_case as shown in `config.example.json`.

## Testing Guidelines
- Expand `unittest` cases to cover new parsing paths and automation branches.
- Name files and methods `test_*`; keep realistic HTML/JSON fixtures near the tests.
- Run `python -m unittest` before each PR and add targeted assertions for new logic.

## Commit & Pull Request Guidelines
- Write concise imperative subjects (e.g., `Handle missing API responses`) and elaborate in the body if required.
- Flag config or template changes so reviewers can validate behaviour.
- In PRs, link issues, attach dashboard screenshots for UI tweaks, and state the test command executed.

## Configuration & Security Tips
- Copy `config.example.json` when onboarding; never commit personal credentials or village data.
- Treat `config.bak` as local only and purge `cache/` artifacts before sharing branches.
- Store secrets in environment variables or ignored `.env` files.
