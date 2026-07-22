---
applyTo: "app/project.py,app/**/*session*.py,gui/project*.py,gui/**/*session*.py"
---

# Projekt CRT i zapisane sesje — dodatkowe reguły

- Jeden folder projektu reprezentuje jedno ECU. Nie mieszaj sesji różnych ECU i nie zamieniaj projektu w katalog luźnych logów.
- Surowe pliki sesji są niezmienne. Analizy, indeksy i metadane mają być zapisane obok jako osobne artefakty.
- Zachowuj `project.crt.json`, identyfikator projektu, ścieżki względne sesji i istniejący schemat `.crt/project.sqlite`, chyba że zadanie jawnie obejmuje migrację.
- Wszystkie zapisy manifestów i artefaktów wykonuj atomowo przez plik tymczasowy i zamianę docelową.
- Waliduj, że ścieżki pozostają wewnątrz katalogu projektu. Nie ufaj ścieżkom pochodzącym z GUI, importu ani manifestu.
- Błąd lub anulowanie nie może pozostawić częściowo zarejestrowanej sesji, uszkodzonego manifestu ani osieroconego wpisu SQLite.
- Nie przeliczaj całej sesji w wątku GUI. Wykorzystuj istniejące indeksy, cache, pagination i workery.
- Testy muszą potwierdzać ponowne otwarcie projektu, zachowanie ID i danych istniejących oraz brak modyfikacji SHA-256 surowej sesji.