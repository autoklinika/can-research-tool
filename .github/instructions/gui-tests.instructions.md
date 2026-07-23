---
applyTo: "gui/**/*.py,tests_gui/**/*.py,tests/**/*.py,.github/workflows/*.yml,.github/workflows/*.yaml"
---

# Qt GUI, testy i CI — dodatkowe reguły

- Nie blokuj wątku GUI operacjami plikowymi, SQLite, dekodowaniem całej sesji ani oczekiwaniem na sprzęt.
- Zachowuj ograniczone modele, stronicowanie, asynchroniczne workery oraz istniejące sygnały i kontrolery.
- Przy tworzeniu lub zastępowaniu widgetów dopilnuj rozłączenia sygnałów, zatrzymania workerów, `deleteLater()` i zwolnienia uchwytów SQLite.
- Smoke test GUI ma jawnie zamknąć okna, zakładki i wątki, przetworzyć `DeferredDelete` oraz działać na Linux offscreen i Windows.
- Test domenowy nie może importować PySide6, jeżeli workflow instaluje tylko zależności `dev`; testy Qt umieszczaj w `tests_gui`.
- Nie osłabiaj istniejących regresji, nie usuwaj asercji integralności i nie zwiększaj timeoutów zamiast naprawić lifecycle.
- Zmianę GUI dodaj do odpowiedniego `GUI Regressions` i `Windows GitHub-Hosted CI`. Runner self-hosted jest przeznaczony tylko dla testów wymagających Kvasera, CANlib lub fizycznego CAN.
- Przy review sprawdzaj różnice Linux/Windows, żywotność wrapperów PySide, pozostawione uchwyty plików oraz pracę wykonywaną podczas konstruktora okna.