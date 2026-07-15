# Architektura CRT — faza 1

## Cel

CRT ma wspierać reverse engineering magistrali CAN: przechwytywanie materiału badawczego, porządkowanie go, porównywanie sesji oraz wykrywanie zależności w surowych ramkach.

## Granice projektu

CRT nie importuje logiki ECU Platform, ekranów konkretnych ECU ani gotowych procedur UDS. Dane z istniejących projektów mogą być używane jako próbki wejściowe do testów kompatybilności, ale nie definiują modelu domenowego CRT.

## Warstwy

### `kvaser/`

Adapter sprzętowy i import plików. Kod tej warstwy zna CANlib, kanały Kvaser, flagi ramek i formaty eksportu.

W fazie 1 adapter online:

- sprawdza obecność trybu `SILENT`,
- ustawia `Driver.SILENT` przed `busOn()`,
- udostępnia tylko operacje odczytu,
- nie zawiera metody `write`, `send` ani odpowiednika.

### `app/`

Warstwa niezależna od producenta interfejsu:

- model ramki i sesji,
- serializacja sesji,
- statystyki po CAN ID,
- analiza okresowości,
- analiza zmienności bajtów,
- później porównywanie sesji i hipotezy sygnałów.

### Dekodery

ISO-TP, UDS, J1939 i profile własne nie należą do rdzenia. Zostaną dołączone później przez neutralny interfejs dekodera, który konsumuje ramki lub kompletne sesje.

## Zasada bezpieczeństwa

Faza 1 jest pasywna również na poziomie magistrali: urządzenie pracuje w trybie silent/listen-only i nie potwierdza ramek bitem ACK. Jeżeli kanał lub sprzęt nie zgłasza obsługi silent mode, CRT odmawia rozpoczęcia nasłuchu.
