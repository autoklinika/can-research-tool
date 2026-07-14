# Roadmap

## Etap 0 — materiał referencyjny

- dodać działający skrypt Kvasera do `reference/`,
- opisać środowisko, model interfejsu, wersję CANlib i sposób testu,
- wyodrębnić potwierdzone wymagania sprzętowe i zachowania API.

## Etap 1 — stabilny rejestrator

- enumeracja kanałów Kvaser,
- konfiguracja bitrate i 11/29-bit,
- odbiór ramek z timestampami,
- zapis sesji i metadanych,
- bezpieczne zamknięcie kanału,
- tryb domyślnie bez TX.

## Etap 2 — kontrolowane nadawanie

- pojedyncze ramki,
- sekwencje z limitami czasu i liczby powtórzeń,
- rejestracja wszystkich ramek TX,
- natychmiastowe zatrzymanie transmisji.

## Etap 3 — analiza podstawowa

- lista aktywnych CAN ID,
- statystyki okresów i jittera,
- rozkład DLC,
- maski zmienności bajtów,
- wykrywanie prostych liczników.

## Etap 4 — porównywanie sesji

- znaczniki zdarzeń,
- synchronizacja eksperymentów,
- różnice ramek przed i po zdarzeniu,
- raporty Markdown i JSON.

## Etap 5 — analiza zaawansowana

- kandydaci CRC/checksum,
- dekodowanie ISO-TP/UDS,
- analiza J1939,
- profile badanych urządzeń,
- eksport potwierdzonej wiedzy do dokumentacji właściwych projektów.
