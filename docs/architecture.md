# Architektura CRT — neutralny pipeline CAN

## Cel

CRT wspiera reverse engineering magistrali CAN. Surowa ramka i kompletna sesja są zawsze źródłem prawdy; dekodowanie tworzy dodatkowe widoki i nigdy nie usuwa ani nie zastępuje materiału wejściowego.

## Granice projektu

CRT nie importuje logiki ECU Platform, ekranów konkretnych ECU ani gotowych procedur dla określonych sterowników. Znane logi mogą służyć jako materiał regresyjny, ale nie definiują architektury narzędzia.

## Przepływ danych

```text
CanFrame
   -> CaptureSession
   -> TransportPipeline
   -> TransportMessage
   -> ProtocolRegistry
   -> DecodedMessage
   -> LogicalMessageAnalyzer
```

## Warstwa sprzętowa `kvaser/`

Adapter Kvaser zna CANlib, kanały, flagi i tryb elektryczny odbioru. Nie udostępnia metod `write` ani `send`.

- `BENCH` — aplikacja nie nadaje ramek, a kontroler potwierdza poprawny odbiór bitem ACK; tryb do pracy z pojedynczym ECU na stole.
- `LISTEN_ONLY` — sprzętowy `SILENT`, bez ramek TX i bez ACK; tryb do kompletnej, aktywnej sieci.

## Neutralny model

- `CanFrame` — surowa ramka zależna wyłącznie od CAN.
- `TransportMessage` — pojedyncza lub zrekonstruowana wiadomość wraz z listą ramek źródłowych, kompletnością i błędami.
- `DecodedMessage` — interpretacja protokołu nałożona na wiadomość transportową.

## Wtyczki transportowe

`TransportReassembler` jest neutralnym interfejsem składacza. Pierwsze implementacje:

- `RAW` — jedna ramka pozostaje jedną wiadomością;
- `J1939 BAM`;
- `J1939 RTS/CTS`;
- `ISO-TP` dla typowych 11-bitowych identyfikatorów diagnostycznych;
- `ISO-TP` dla 29-bitowego normal-fixed addressing z PF `0xDA` i `0xDB`.

Klasyfikacja ISO-TP jest celowo konserwatywna, aby autorska ramka rozpoczynająca się bajtem podobnym do PCI nie została automatycznie uznana za transport diagnostyczny.

## Wtyczki protokołów

`ProtocolDecoder` otrzymuje gotową `TransportMessage`. Rejestr dekoderów działa w określonej kolejności:

1. UDS — tylko po rozpoznanym ISO-TP i tylko dla znanych identyfikatorów usług;
2. J1939 — dla wiadomości zrekonstruowanych przez J1939 TP;
3. reguły użytkownika dla protokołów autorskich;
4. `UNKNOWN` jako bezpieczny fallback.

Rozłożenie 29-bitowego CAN ID na pola przypominające J1939 nie jest dowodem, że protokół jest J1939. Dla nierozpoznanych ramek pola te są zapisywane wyłącznie jako kandydat pomocniczy.

## Protokoły autorskie

`MessageRule` pozwala opisać rodzinę identyfikatorów przez ID i maskę, typ ramki, transport oraz zakres długości payloadu. Reguła może oznaczyć wiadomość jako `PROPRIETARY` bez zmiany rdzenia i bez wymuszania interpretacji J1939 lub UDS.

Późniejsze warstwy reguł będą obejmować sygnały, endian, skalowanie, liczniki i checksumy.

## Pliki wynikowe

Rejestracja tworzy dwa niezależne poziomy danych:

- `*.crt.jsonl`, `*.frames.csv`, `*.summary.csv` — surowe ramki i statystyki CAN ID;
- `*.messages.csv`, `*.messages.summary.csv` — wiadomości po rekonstrukcji transportu i ich rzeczywista okresowość.

Istniejącą sesję można ponownie przeanalizować bez dostępu do interfejsu CAN przez `analyze_session.py`.
