---
applyTo: "app/**/*capture*.py,gui/**/*capture*.py,kvaser/**/*.py,app/**/*can*.py"
---

# Capture, Kvaser i CAN — dodatkowe reguły

- Traktuj kolejność, kompletność i czas zapisu surowych ramek jako kontrakt danych.
- Nie zmieniaj ownership lifecycle CANlib, kolejności open/start/stop/close ani obsługi kanałów bez jawnego zakresu zadania i testu sprzętowego.
- Nie dodawaj CAN TX, probe, resetu ECU ani automatycznych komend diagnostycznych jako skutku otwarcia widoku, projektu lub aplikacji.
- Nie wykonuj pracy blokującej w wątku GUI. Zachowuj istniejące workery, sygnały Qt i mechanizmy anulowania.
- Nie zastępuj ograniczonych modeli pełnym buforem sesji i nie wykonuj pełnego skanowania przy każdym odświeżeniu.
- Każdą zmianę w tym obszarze opisz jako ryzyko sprzętowe i wskaż wymagany test Kvaser/CANlib na właściwym runnerze.
- Przy review sprawdzaj podwójne zamknięcia, użycie nieaktualnego kanału, utratę ramek, zmianę kolejności zapisu oraz wysyłanie ramek bez świadomej akcji użytkownika.