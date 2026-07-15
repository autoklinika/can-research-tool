# CAN Research Tool (CRT)

Desktopowa aplikacja Windows do **pasywnego** badania komunikacji CAN. Pierwsza faza projektu nie wysyła żadnych ramek i nie wykonuje procedur diagnostycznych.

## Zakres fazy 1

- import i później nasłuch ramek CAN,
- zapis sesji badawczej,
- rekonstrukcja ISO-TP wyłącznie na podstawie obserwowanych ramek,
- dekodowanie UDS i profili ECU,
- raport z sesji,
- pierwszy profil referencyjny: **DAF SAC**.

CRT nie zastępuje ECU Platform. ECU Platform wykonuje diagnostykę i sterowanie, natomiast CRT służy do obserwacji, analizy i dokumentowania komunikacji.

## Aktualny PoC

Pierwszy etap implementuje analizę offline:

- GUI PySide6 dla Windows,
- import typowych logów CSV z Kvaser,
- tabela surowych ramek,
- pasywna rekonstrukcja ISO-TP Single Frame / First Frame / Consecutive Frame,
- dekoder podstawowych usług UDS,
- rozpoznawanie znanych identyfikatorów SAC:
  - tester → SAC: `0x18DA30F9`,
  - SAC → tester: `0x18DAF930`,
- dekodowanie DID:
  - `F190` — VIN,
  - `F188` — wersja software,
  - `F192` — wersja hardware,
- eksport raportu JSON.

## Uruchomienie

Wymagany Python 3.11 lub nowszy.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
crt
```

Testy:

```powershell
pytest
```

## Zasada bezpieczeństwa fazy 1

Warstwa analizy nie posiada interfejsu nadawania CAN. Rekonstruktor ISO-TP obserwuje Flow Control, ale nigdy go nie generuje. Obsługa aktywnej diagnostyki pozostaje poza CRT.

## Kolejne kroki

1. Przetestowanie importera na rzeczywistych logach Kvaser z SAC.
2. Zapis kompletnej sesji CRT wraz z metadanymi i ostrzeżeniami parsera.
3. Pasywny adapter Kvaser CANlib / `python-can` w trybie odbioru.
4. Widok rozmów request/response i osi czasu.
5. Rozszerzalne profile kolejnych ECU i protokołów.
