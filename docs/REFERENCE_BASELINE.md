# Reference application baseline

## Status

The uploaded file `kvaser_can_monitor_v2.7_final_unified_patterns_learning_center_v2.py` is a **read-only reference implementation**.

It must not be refactored into the target application and must not become the starting source tree. The target application will be designed and implemented from scratch.

Reference file identity:

- size: 186628 bytes on upload
- lines: 4486
- SHA-256: `1c318806839cac58cc2aae597affe6585bf2f2ecb97fcaa78aa1c350c9cdcf28`

The checksum is the identity of the reviewed baseline. Any changed copy is a different reference revision and must receive a new record.

## Purpose of the reference

The file proves which workflows already work with the user's Windows/Kvaser environment. It is used to extract:

- verified CANlib initialization patterns,
- channel enumeration and device identification,
- bitrate configuration including custom timing parameters,
- stable receive-loop and GUI queue handling,
- active Tx/Rx workflow,
- ISO-TP behavior,
- UDS/J1939 decoding ideas,
- DBC loading and matching behavior,
- autobaud workflow,
- diagnostic-address scanning workflow,
- transaction history and operator feedback concepts,
- rule and learning-center concepts,
- operational safety requirements.

## Functional inventory observed

### CAN interface

- Kvaser CANlib channel discovery.
- Display of channel name, serial number and EAN.
- Classic CAN predefined bitrates.
- Custom bitrate calculation through time-quanta parameters.
- Standard and extended frame support.
- Normal and silent driver modes.
- Bus on/off lifecycle and error handling.

### Passive monitor

- Dedicated receiver thread.
- Queue-based transfer to the Qt GUI.
- Raw frame log view.
- Grouped-by-CAN-ID view.
- Frame-rate and total-frame counters.
- Standard/extended filtering.
- Wildcard CAN-ID filters.
- CSV capture.
- ASCII and basic UDS interpretation.

### Active Tx/Rx

- Manual CAN-ID, frame type, DLC and payload.
- Expected-response ID.
- Timeout and first-response controls.
- Transaction history.
- Response table and status log.
- Single-frame and multi-frame ISO-TP transmission.
- Flow Control handling.
- Multi-frame ISO-TP response collection.
- UDS request builder.

### Diagnostic helpers

- Common UDS SID descriptions.
- Common UDS subfunctions.
- Common identification DID descriptions.
- Positive and negative response interpretation.
- 29-bit diagnostic request/response ID helpers.
- Destination-address scan.
- Tester source-address manual and automatic ranges.
- Stop-on-first-response option.

### Network discovery

- Passive autobaud over multiple candidate rates.
- Multiple listening rounds.
- Stability scoring.
- Preference for extended frames.
- Custom timing parameters for uncommon rates.

### DBC

- `cantools` database loading.
- Exact CAN-ID lookup.
- J1939 PGN lookup.
- SA/DA wildcard matching concepts.
- Live signal display.

### Pattern and learning concepts

- External JSON pattern file.
- TX/RX byte checks.
- UDS payload checks.
- Rule actions: log, status, timeout extension, stop and follow-up frame.
- Manual creation of learned transaction patterns.
- Good/bad/unknown operator judgement.
- Transaction context storage.
- Optional offline heuristic/local-model analysis.
- Case memory, anomaly detection and rule-learning concepts.

## Architectural lessons

The reference demonstrates valuable behavior, but also confirms why the target application must not remain a single-window monolith.

The new implementation must separate at least:

1. Kvaser transport and channel ownership.
2. CAN frame domain model.
3. Capture/session persistence.
4. Passive monitoring.
5. Active transmission safety policy.
6. ISO-TP transport.
7. UDS interpretation.
8. J1939/DBC interpretation.
9. Discovery tools such as autobaud and address scan.
10. Rule engine and knowledge storage.
11. GUI presentation.

No GUI class may directly own the full protocol, storage and device logic.

## Non-negotiable rule

The reference application is evidence and inspiration, not production source. New modules may reproduce verified behavior only after their responsibilities, interfaces and tests are defined independently.