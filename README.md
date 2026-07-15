# CAN Research Tool (CRT)

CRT to niezależne narzędzie do **reverse engineeringu komunikacji CAN**. Nie jest kopią ECU Platform i nie zawiera procedur diagnostycznych konkretnych sterowników.

## Faza 1 — odbiór bez ramek aplikacyjnych TX

- wykrywanie interfejsów i kanałów Kvaser,
- odbiór surowych ramek CAN bez udostępniania metod `write` / `send`,
- dwa tryby elektryczne odbioru:
  - `BENCH` — kontroler potwierdza poprawne ramki bitem ACK; wymagany na stole, gdy obserwowane ECU jest jedynym nadajnikiem,
  - `LISTEN_ONLY` — sprzętowy `SILENT`, bez TX i bez ACK; do kompletnej sieci, w której inne aktywne węzły zapewniają ACK,
- wyłączenie lokalnego echa transmisji innych uchwytów CANlib,
- zapis kompletnej sesji z metadanymi,
- import istniejących logów Kvaser CSV,
- neutralna analiza ramek: ID, częstotliwość, okresowość, DLC i zmienność bajtów,
- filtrowanie, oznaczanie i porównywanie sesji,
- opcjonalne dekodery protokołów dodawane później jako osobne moduły.

Znane logi z SAC służą wyłącznie jako materiał testowy do sprawdzania kompatybilności importu i zapisu Kvaser.

## Struktura

- `app/` — modele sesji i neutralny silnik analizy,
- `kvaser/` — izolowana integracja z Kvaser CANlib oraz import logów,
- `sessions/` — lokalne sesje badawcze, pomijane przez Git,
- `docs/` — architektura i decyzje projektowe,
- `tests/` — testy parserów i analizy.

## Uruchomienie testów

```powershell
py -m pip install -e ".[dev]"
pytest
```

Sterownik Kvaser i pakiet `canlib` są zależnościami opcjonalnymi wymaganymi dopiero do nasłuchu online.
