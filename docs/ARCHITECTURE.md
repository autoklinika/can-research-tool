# Architektura

## Granice projektu

CAN Research Tool jest osobną aplikacją badawczą. Nie stanowi modułu ECU Platform i nie powinien współdzielić z nią kodu interfejsu użytkownika ani logiki testera warsztatowego.

## Planowane warstwy

```text
UI / CLI
  ↓
Session Controller
  ↓
Capture and Transmit Services
  ↓
CAN Transport Interface
  ↓
Kvaser CANlib Adapter
```

Warstwa analityczna będzie pracowała na zapisanych, ujednoliconych rekordach ramek, a nie bezpośrednio na API Kvasera.

## Główne moduły

- `transport` — abstrakcja interfejsu CAN i adapter Kvaser CANlib,
- `capture` — odbiór, timestampy, kolejki i zapis surowych danych,
- `transmit` — jawnie kontrolowane nadawanie ramek i sekwencji,
- `sessions` — metadane eksperymentów, zdarzenia i integralność plików,
- `analysis` — statystyki ID, okresowość, zmienność bajtów i porównania,
- `common` — wspólne modele danych, błędy i konfiguracja.

## Zasada referencji

Działający skrypt użytkownika zostanie umieszczony w `reference/` jako dowód poprawnej obsługi sprzętu. Kod docelowy powstanie od zera z jasno określonymi interfejsami.
