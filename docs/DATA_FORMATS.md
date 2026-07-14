# Formaty danych

## Sesja badawcza

Każda sesja powinna posiadać własny katalog poza repozytorium Git:

```text
YYYY-MM-DD_DEVICE_NNN/
├── raw/
│   └── capture.csv
├── session.json
├── events.json
├── checksums.sha256
└── report.md
```

## Minimalny rekord ramki

Planowany format logiczny:

- monotoniczny timestamp,
- czas UTC,
- kanał,
- kierunek `RX` lub `TX`,
- CAN ID,
- format 11- lub 29-bit,
- DLC,
- dane,
- flagi CANlib,
- opcjonalny identyfikator zdarzenia.

## Metadane sesji

`session.json` powinien zawierać co najmniej:

- identyfikator sesji,
- typ i oznaczenie badanego urządzenia,
- operatora,
- interfejs i kanał Kvasera,
- bitrate,
- tryb pracy,
- ścieżkę magazynu danych,
- wersję aplikacji,
- hash pliku źródłowego po zakończeniu zapisu.

Dokładny schemat zostanie ustalony po analizie działającego skryptu referencyjnego i pierwszych rzeczywistych sesji.
