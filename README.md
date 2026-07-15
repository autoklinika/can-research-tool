# CAN Research Tool (CRT)

CRT to niezależne narzędzie do **reverse engineeringu komunikacji CAN**. Nie jest kopią ECU Platform i nie zawiera procedur diagnostycznych konkretnych sterowników.

## Aktualny zakres

- wykrywanie interfejsów i kanałów Kvaser,
- odbiór bez udostępniania metod `write` / `send`,
- `BENCH` z aktywnym ACK do pojedynczego ECU na stole,
- `LISTEN_ONLY` bez TX i bez ACK do kompletnej aktywnej sieci,
- zapis surowej sesji CRT i eksport CSV,
- statystyki CAN ID, okresowości, DLC i zmienności bajtów,
- neutralny model `CanFrame -> TransportMessage -> DecodedMessage`,
- rekonstrukcja J1939 TP: BAM oraz RTS/CTS,
- rekonstrukcja ISO-TP dla typowych 11- i 29-bitowych adresów diagnostycznych,
- konserwatywna klasyfikacja UDS po ISO-TP,
- bezpieczny fallback `UNKNOWN` dla ramek nierozpoznanych,
- reguły użytkownika do oznaczania protokołów autorskich,
- statystyki rzeczywistych wiadomości po rekonstrukcji transportu.

Surowe ramki pozostają źródłem prawdy. Dekodery tworzą dodatkowy widok i nie usuwają danych nierozpoznanych. Znane logi z SAC służą wyłącznie jako materiał testowy do sprawdzania kompatybilności.

## Struktura

- `app/` — modele, zapis sesji, transporty, dekodery i analiza,
- `kvaser/` — izolowana integracja z Kvaser CANlib oraz import logów,
- `sessions/` — lokalne sesje badawcze, pomijane przez Git,
- `docs/` — architektura i decyzje projektowe,
- `tests/` — testy parserów, transportów i analizy.

## Rejestracja sesji Kvaser

Domyślny zapis 10 sekund na kanale 0, 250 kbit/s, w trybie stanowiskowym `BENCH`:

```powershell
.\.venv\Scripts\python.exe .\capture_session.py --duration 10 --name pierwszy_test
```

Nasłuch bez limitu czasu, kończony przez `Ctrl+C`:

```powershell
.\.venv\Scripts\python.exe .\capture_session.py --duration 0 --name long_capture
```

Podgląd każdej ramki w terminalu:

```powershell
.\.venv\Scripts\python.exe .\capture_session.py --duration 10 --live
```

Tryb pełnego listen-only dla kompletnej sieci:

```powershell
.\.venv\Scripts\python.exe .\capture_session.py --mode listen-only
```

Po zakończeniu powstaje pięć plików:

- `*.crt.jsonl` — pełna sesja CRT z metadanymi,
- `*.frames.csv` — surowe ramki,
- `*.summary.csv` — statystyka według CAN ID,
- `*.messages.csv` — wiadomości po rekonstrukcji transportu i dekodowaniu,
- `*.messages.summary.csv` — statystyka rzeczywistych wiadomości logicznych.

## Ponowna analiza istniejącej sesji

Nie trzeba ponownie podłączać Kvasera:

```powershell
.\.venv\Scripts\python.exe .\analyze_session.py sessions\pierwszy_test.crt.jsonl
```

## Testy

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Szczegóły architektury: `docs/architecture.md`.
