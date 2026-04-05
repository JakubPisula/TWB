# GEMINI.md — TWB Agent Instructions

> Plik instrukcji dla Gemini CLI (lub Claude Code).
> Umieść go w katalogu głównym repozytorium TWB obok `AGENTS.md`.

---

## 1. Kontekst projektu

**TWB** to Python-owy bot do gry przeglądarkowej „Plemiona" (Tribal Wars, serwer `pl227.plemiona.pl`).
Bot działa jako usługa systemowa na LXC (Linux, dużo RAM).
Autentykacja odbywa się przez ciasteczka pobrane z rozszerzenia przeglądarki.

Zanim napiszesz cokolwiek — przeczytaj `AGENTS.md` (konwencje, testy, styl) oraz `config.example.json`
(pełna struktura konfiguracji). Kod musi pasować do istniejącej architektury.

---

## 2. Zadanie: Zaimplementuj moduł Zbieractwa (Scavenging)

### 2.1 Co już istnieje w konfiguracji

W `config.example.json` → `village_template` są już klucze:

```json
"gather_enabled": false,
"gather_selection": 1,
"advanced_gather": true,
"prioritize_gathering": false
```

Te klucze MUSZĄ pozostać wstecznie kompatybilne. Rozbuduj ich znaczenie wg opisu poniżej.

### 2.2 Nowe klucze konfiguracyjne do dodania

Dodaj do sekcji `village_template` w `config.example.json`:

```json
"gather_enabled": false,
"gather_levels": [1, 2, 3],
"gather_unit_priority": ["sword", "spear", "axe"],
"gather_min_fill_ratio": 0.85,
"gather_reserve_for_farm": {
  "light": 1.0,
  "marcher": 1.0
},
"gather_cooldown_minutes": 5,
"advanced_gather": true,
"prioritize_gathering": false
```

**Semantyka:**
- `gather_levels` — lista aktywnych poziomów zbieractwa (1–3; poziom 4 jest pominięty jako zbyt kosztowny).
- `gather_unit_priority` — jednostki wysyłane do zbieractwa (defensywne: miecze, piki, topory). Jednostki **niewylistowane** (LK, marcher) są w pełni rezerwowane dla farmienia.
- `gather_min_fill_ratio` — minimalny stopień wypełnienia poziomu, poniżej którego nie opłaca się wysyłać (default 0.85).
- `gather_reserve_for_farm` — frakcja jednostek rezerwowanych wyłącznie dla farmienia (1.0 = 100% rezerwowane).
- `gather_cooldown_minutes` — minimalna przerwa między rundami zbieractwa.

---

## 3. Pliki do stworzenia

### 3.1 `game/scavenging.py`

Utwórz klasę `ScavengingManager` zgodnie z poniższą specyfikacją.

```
class ScavengingManager:
    """
    Zarządza automatycznym zbieractwem dla jednej wioski.
    Pobiera dane z gry przez HTTP (ciasteczka z core/), parsuje
    dostępne poziomy zbieractwa i optymalnie rozdziela jednostki
    defensywne pomiędzy poziomami, maksymalizując surowce/h.
    """
```

**Metody wymagane:**

#### `__init__(self, village_id: int, config: dict, wrapper)`
- `village_id` — ID wioski (int) z `config["villages"]`
- `config` — słownik `village_template` z config.json
- `wrapper` — instancja istniejącego HTTP wrappera z `core/` (używa ciasteczek)

#### `fetch_scavenge_page(self) -> BeautifulSoup`
- Pobiera stronę: `https://{server}/game.php?village={village_id}&screen=place&mode=scavenge`
- Używa `wrapper.get(url)` — NIE twórz własnego `requests.Session`
- Parsuje HTML przez `BeautifulSoup(response.text, "html.parser")`
- Rzuca `ScavengingUnavailableError` jeśli zakładka jest niedostępna

#### `parse_available_units(self, soup: BeautifulSoup) -> dict[str, int]`
- Wyciąga aktualnie dostępne (nie w drodze) jednostki wioski ze strony zbieractwa
- Format zwracany: `{"sword": 450, "spear": 300, "axe": 200, ...}`
- Pomija jednostki z `gather_reserve_for_farm` (LK, marcher — 100% zarezerwowane)
- Pomija jednostki nieobecne w `gather_unit_priority`

#### `parse_scavenge_levels(self, soup: BeautifulSoup) -> list[ScavengeLevel]`
- Wyciąga dostępne poziomy zbieractwa z HTML
- Zwraca listę `ScavengeLevel(level_id, capacity, duration_seconds, is_locked, is_running)`
- Filtruje do poziomów z `gather_levels` (domyślnie [1,2,3])
- Pomija poziomy, które już trwają (`is_running=True`)

#### `calculate_optimal_split(self, units: dict[str, int], levels: list[ScavengeLevel]) -> list[ScavengeAssignment]`
- **Serce modułu** — algorytm optymalnego podziału wojsk.
- Dane wejściowe: dostępne jednostki + lista wolnych poziomów
- Dane jednostek (nośność w Plemionach PL):
  ```
  UNIT_CARRY = {
      "spear":   25,
      "sword":   15,
      "axe":     10,
      "archer":  10,
      "light":  80,   # LK — zarezerwowana, nie używana
      "marcher": 50,  # zarezerwowana, nie używana
      "heavy":   50,
      "ram":      0,
      "catapult": 0,
      "knight":  100,
      "snob":     0,
  }
  ```
- **Algorytm:**
  1. Policz łączną nośność dostępnych jednostek: `total_carry = sum(count * UNIT_CARRY[u] for u, count in units.items())`
  2. Posortuj poziomy malejąco po `capacity` (wyższy poziom = większa pojemność = więcej surowców).
  3. Przydziel jednostki zachłannie: zacznij od najwyższego poziomu, wypełnij go do `gather_min_fill_ratio * capacity`, resztę przekaż niżej.
  4. Dla każdego poziomu oblicz liczbę jednostek potrzebną do osiągnięcia `fill_ratio`:
     `units_needed = ceil(level.capacity * fill_ratio / avg_carry_per_unit)`
  5. Jeśli po podziale jakiś poziom ma < `gather_min_fill_ratio` wypełnienia — pomiń go.
  6. Zwróć `list[ScavengeAssignment(level_id, units_dict)]`

#### `send_scavenge(self, assignment: ScavengeAssignment) -> bool`
- Wysyła POST do gry dla danego poziomu zbieractwa
- URL: `https://{server}/game.php?village={village_id}&screen=place&mode=scavenge`
- Payload: `{"option": level_id, "sword": N, "spear": N, "axe": N, ...}`
- Loguje wynik przez `logging.getLogger(__name__)`
- Zwraca `True` jeśli sukces (HTTP 200, brak komunikatu o błędzie)

#### `run(self) -> None`
- Główna pętla wywoływana przez schedulera bota
- Sprawdza cooldown (`gather_cooldown_minutes`)
- Wywołuje kolejno: `fetch_scavenge_page → parse_available_units → parse_scavenge_levels → calculate_optimal_split → send_scavenge` dla każdego assignmentu
- Obsługuje wyjątki bez crashowania bota (loguj ERROR, nie rzucaj dalej)

**Dataclassy pomocnicze** (zdefiniuj na górze pliku):

```python
from dataclasses import dataclass, field

@dataclass
class ScavengeLevel:
    level_id: int
    capacity: int          # maks. surowce do zebrania
    duration_seconds: int  # czas podróży w sekundach
    is_locked: bool
    is_running: bool

@dataclass
class ScavengeAssignment:
    level_id: int
    units: dict  # {"sword": N, "spear": N, ...}

class ScavengingUnavailableError(Exception):
    pass
```

---

### 3.2 `core/world_data.py`

Utwórz klasę `WorldDataManager` do pobierania i cachowania plików TXT świata.

```python
class WorldDataManager:
    """
    Pobiera pliki TXT świata Plemion i udostępnia je jako pandas DataFrames.
    Cache lokalny w cache/world/ z TTL 1 godzina.
    """
    BASE_URL = "https://{server}.plemiona.pl/map/{filename}"

    WORLD_FILES = {
        "village":   ("village.txt",   ["village_id","name","x","y","player_id","points","rank"]),
        "player":    ("player.txt",    ["player_id","name","ally_id","villages","points","rank"]),
        "tribe":     ("tribe.txt",     ["tribe_id","name","tag","members","villages","points","rank"]),
        "kill_att":  ("kill_att.txt",  ["rank","player_id","score"]),
        "kill_def":  ("kill_def.txt",  ["rank","player_id","score"]),
        "kill_all":  ("kill_all.txt",  ["rank","player_id","score"]),
        "conquer":   ("conquer.txt",   ["village_id","timestamp","new_owner","old_owner"]),
    }
```

**Metody:**

#### `__init__(self, server: str, cache_dir: str = "cache/world")`
- `server` — nazwa serwera z config (np. `"pl227"`)
- Tworzy `cache_dir` jeśli nie istnieje

#### `_is_cache_valid(self, filename: str, ttl_seconds: int = 3600) -> bool`
- Sprawdza czy plik cache istnieje i jest młodszy niż `ttl_seconds`

#### `_fetch_and_cache(self, key: str) -> str`
- Pobiera plik przez `requests.get(url, timeout=15)`
- Dekoduje przez `urllib.parse.unquote` (pliki są URL-encoded)
- Zapisuje surowy tekst do `cache/world/{key}.txt`
- Rzuca `WorldDataFetchError` przy błędzie HTTP

#### `get_dataframe(self, key: str, force_refresh: bool = False) -> pd.DataFrame`
- Zwraca `pd.DataFrame` dla danego klucza (np. `"village"`, `"player"`)
- Używa cache jeśli ważny, inaczej pobiera świeżo
- Parsuje CSV przez `pd.read_csv(..., header=None, names=columns, sep=",")`
- Ustawia właściwy `dtype` dla kolumn ID (int64)

#### `get_village_info(self, village_id: int) -> dict | None`
- Shortcut: zwraca słownik dla konkretnej wioski z `village` DataFrame

#### `get_player_villages(self, player_id: int) -> pd.DataFrame`
- Zwraca wszystkie wioski danego gracza

#### `refresh_all(self) -> None`
- Odświeża wszystkie pliki naraz (wywołuj przy starcie bota)

---

### 3.3 Integracja z `twb.py`

Znajdź w `twb.py` miejsce gdzie inicjalizowane są managery wiosek (szukaj pętli po `config["villages"]`).
Dodaj inicjalizację `ScavengingManager` dla każdej wioski gdzie `gather_enabled: true`:

```python
from game.scavenging import ScavengingManager

# wewnątrz pętli inicjalizacji wioski:
if village_config.get("gather_enabled", False):
    village.scavenging = ScavengingManager(
        village_id=vid,
        config=village_config,
        wrapper=wrapper
    )
```

W głównej pętli schedulera — wywołaj `village.scavenging.run()` jeśli `scavenging` istnieje.
Nie przerywaj pętli przy wyjątku ze scavenging — loguj i kontynuuj.

---

## 4. Testy jednostkowe

Utwórz `tests/test_scavenging.py`:

```python
"""
Testy dla ScavengingManager.
Używaj unittest + mock dla HTTP wrappera.
NIE wykonuj prawdziwych requestów HTTP.
"""
```

**Wymagane przypadki testowe:**

1. `test_calculate_optimal_split_basic` — 500 mieczy + 300 pik → 3 poziomy, sprawdź że suma units ≤ input
2. `test_calculate_optimal_split_not_enough_units` — za mało jednostek → pomiń poziom z niskim fill_ratio
3. `test_calculate_optimal_split_single_level` — tylko 1 wolny poziom → wszystko do niego
4. `test_parse_available_units_excludes_reserved` — LK w HTML → nie powinna trafić do wyniku
5. `test_cooldown_respected` — `run()` wywołane dwa razy szybko → drugi call nie wysyła requestów

Fixtures HTML dla testów umieść w `tests/fixtures/scavenge_page.html`.

---

## 5. Wymagania implementacyjne (must-have)

- [ ] Używaj `logging.getLogger(__name__)` — zero `print()`
- [ ] Wszystkie zewnętrzne requesty przez istniejący `wrapper` z `core/` — NIE twórz własnego Session
- [ ] Pełne type hints na wszystkich metodach publicznych
- [ ] Docstring na każdej klasie i metodzie publicznej (PEP 257)
- [ ] Obsługa przypadku gdy zbieractwo nie jest odblokowane (brak zakładki w HTML)
- [ ] Obsługa gdy wszystkie poziomy już trwają (brak wolnych slotów)
- [ ] `world_data.py` musi działać niezależnie od bota (można importować standalone)
- [ ] Żadnych hardcodowanych URL-ów — server zawsze z `config["server"]["server"]`

---

## 6. Zakaz zmian

- NIE modyfikuj `core/http_wrapper.py` ani analogicznego wrappera HTTP
- NIE zmieniaj istniejących kluczy w `config.example.json` (tylko dodawaj nowe)
- NIE usuwaj istniejących kluczy `gather_enabled`, `gather_selection`, `advanced_gather`
- NIE zmieniaj sygnatury `twb.py::main()`

---

## 7. Kolejność implementacji (dla agenta)

1. Przeczytaj `AGENTS.md` i `config.example.json`
2. Przejrzyj `core/` — znajdź klasę HTTP wrappera i sposób jej użycia
3. Przejrzyj `game/` — znajdź analogiczny manager (np. farming) jako wzorzec stylu
4. Zaimplementuj `core/world_data.py` (niezależny, łatwy do przetestowania)
5. Zaimplementuj `game/scavenging.py` (dataclassy → parser → algorytm → send)
6. Napisz testy w `tests/test_scavenging.py`
7. Zintegruj z `twb.py`
8. Zaktualizuj `config.example.json` o nowe klucze
9. Uruchom `python -m unittest discover -s tests -p "test_*.py"` — wszystkie muszą przejść

---

## 8. Jak uruchomić Gemini CLI

```bash
# Zainstaluj Gemini CLI (jeśli jeszcze nie masz)
npm install -g @google/gemini-cli

# Wejdź do katalogu repo
cd /path/to/TWB

# Uruchom agenta z tym plikiem jako kontekstem
gemini --context GEMINI.md "Zaimplementuj moduł zbieractwa zgodnie z instrukcjami w GEMINI.md"
```

Alternatywnie dla **Claude Code**:
```bash
claude "Zaimplementuj moduł zbieractwa zgodnie z instrukcjami w GEMINI.md"
```

---

*Wygenerowano na podstawie analizy repo JakubPisula/TWB i wymagań zebranych 2026-04-02*
