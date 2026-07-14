# Bezpieczeństwo pracy z magistralą CAN

## Domyślny tryb

Aplikacja ma uruchamiać się bez automatycznego nadawania. Odbiór i zapis ramek powinny być możliwe niezależnie od funkcji TX.

## Wysyłanie ramek

Nadawanie wymaga:

- jawnego włączenia przez operatora,
- wybranego kanału i bitrate,
- potwierdzonego formatu CAN ID,
- ograniczenia do zdefiniowanej listy ramek lub sekwencji,
- pełnego zapisu wszystkich ramek TX w logu,
- możliwości natychmiastowego zatrzymania transmisji.

## Zasady dla SecurityAccess i prób aktywnych

- po negatywnej odpowiedzi wskazującej błędny klucz nie wykonywać kolejnych prób automatycznie,
- respektować czasy opóźnień i blokady ECU,
- nie uruchamiać pętli nadawczych bez limitu ramek i czasu,
- przed aktywnym testem zapisać konfigurację i cel eksperymentu.

## Dane i repozytorium

Pełne logi, zrzuty pamięci, klucze, pliki producenta oraz lokalne ścieżki nie powinny trafiać do Git. Do repozytorium można dodawać wyłącznie małe, świadomie wybrane próbki testowe.
