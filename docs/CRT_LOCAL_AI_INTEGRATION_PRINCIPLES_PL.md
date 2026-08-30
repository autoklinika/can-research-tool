# CRT — zasady integracji z lokalnym AI

Data decyzji: 2026-08-31

Status: **obowiązujący kontrakt architektoniczny dla przyszłej integracji AI w CAN Research Tool**

## 1. Rola lokalnego AI

CRT może i powinien wykorzystywać lokalny model AI wtedy, gdy daje to realną przewagę w reverse engineeringu CAN, szczególnie przy:

- interpretacji wyników Signal Discovery,
- ocenie i opisywaniu kandydatów sygnałów,
- analizie Experiment Diff i korelacji ze znacznikami,
- grupowaniu i opisywaniu nieznanych wzorców,
- tworzeniu propozycji Signal Hypothesis,
- proponowaniu nazw, jednostek, skali i kolejnych eksperymentów,
- analizie profilu heavy-duty, J1939, UDS i przyszłego Diagnostic Discovery,
- generowaniu roboczych opisów oraz propozycji Draft DBC.

AI ma otrzymywać przede wszystkim **ustrukturyzowane wyniki analiz, hipotezy, statystyki i wybrane dowody**, a nie nieograniczony strumień milionów surowych ramek.

## 2. AI nie może być zależnością krytyczną

Najważniejsza zasada:

> **Awaria, brak odpowiedzi, wyłączenie lub niedostępność lokalnego AI nie może przeszkadzać w normalnej pracy CRT.**

W szczególności niedostępność AI nie może blokować:

- uruchomienia CRT,
- otwierania projektów,
- Live Capture,
- zapisu sesji,
- filtrowania i wyszukiwania,
- dekodowania DBC/J1939/ISO-TP/UDS,
- Signal Discovery,
- Experiment Diff,
- deterministycznego Signal Candidate Engine,
- pracy z artefaktami i dowodami,
- eksportów,
- przyszłych funkcji aktywnych po ich świadomym uruchomieniu.

CRT ma pozostawać w pełni użyteczny bez AI.

## 3. Architektura fail-open dla analizy, fail-safe dla sterowania

Integracja AI ma być wykonana jako **opcjonalny adapter/usługa pomocnicza**, odseparowana od krytycznego pipeline CRT.

Zasady:

1. CRT uruchamia się i działa bez połączenia z AI.
2. Każde wywołanie AI ma mieć timeout i kontrolowane anulowanie.
3. Brak odpowiedzi AI daje stan typu `AI unavailable` / `AI skipped`, nie błąd całej operacji.
4. Wyniki AI są dodatkowymi sugestiami lub artefaktami, a nie źródłem prawdy.
5. Deterministyczne wyniki CRT muszą istnieć niezależnie od modelu.
6. AI nie modyfikuje surowych sesji.
7. AI nie może niejawnie uruchamiać CAN TX, UDS requestów ani innych funkcji aktywnych.
8. Dla przyszłych funkcji aktywnych obowiązuje istniejące rozdzielenie `PASSIVE` / `ACTIVE ARMED`; AI może najwyżej zaproponować działanie, ale nie może samodzielnie uzbroić ani wykonać transmisji.

## 4. Model danych

Preferowany przepływ:

```text
RAW CAN / zapisane sesje
        ↓
deterministyczna analiza CRT
        ↓
trwały artefakt + source_row evidence
        ↓
opcjonalny adapter AI
        ↓
AI suggestion / AI hypothesis
        ↓
ręczna weryfikacja użytkownika
```

Wynik AI powinien zachowywać co najmniej:

- identyfikator modelu,
- wersję/konfigurację modelu, jeżeli dostępna,
- timestamp,
- fingerprint wejściowego artefaktu,
- referencje do sesji i dowodów,
- treść sugestii,
- status: sugestia / zaakceptowana / odrzucona / niezweryfikowana.

## 5. Integracja sieciowa

Lokalny AI może działać poza komputerem CRT, np. na osobnym serwerze w LAN. Warstwa integracyjna nie może zakładać stałej dostępności sieci ani serwera AI.

Wymagania:

- krótkie health-checki,
- timeouty,
- retry tylko w kontrolowanych miejscach,
- brak blokowania głównego wątku GUI,
- brak blokowania zapisu sesji i pipeline CAN,
- możliwość całkowitego wyłączenia AI w ustawieniach CRT,
- czytelny status połączenia AI, ale bez traktowania go jak stanu krytycznego programu.

## 6. Priorytet implementacyjny

AI nie jest częścią Signal Discovery Stage 1.

Pierwszy sensowny moment integracji AI pojawi się po uzyskaniu stabilnych, ustrukturyzowanych artefaktów z:

1. Signal Discovery,
2. Experiment Diff / marker correlation,
3. Signal Candidate Engine.

Dopiero wtedy AI będzie miało dobre, ograniczone i dowodowe wejście, na podstawie którego może proponować interpretację i następny eksperyment.

## 7. Zasada produktowa

> **CRT ma być lepszy dzięki lokalnemu AI, ale nigdy zależny od lokalnego AI.**

AI jest warstwą wspomagającą inżyniera. Rdzeń CRT, deterministyczne analizy i evidence chain pozostają niezależne i zawsze dostępne.
