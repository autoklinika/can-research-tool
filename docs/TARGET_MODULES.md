# Target modules

This document converts the proven workflows from the reference application into boundaries for a new implementation. It is not a migration map and does not prescribe copying any reference code.

## Core

### `core/frame`

Immutable CAN frame model:

- timestamp,
- channel,
- CAN ID,
- standard/extended format,
- DLC,
- payload,
- flags,
- direction RX/TX.

### `core/events`

Typed application events for frames, device state, session state, warnings, operator markers and analysis results.

## Hardware and transport

### `transport/kvaser`

Only Kvaser CANlib integration:

- enumerate channels,
- describe hardware,
- open/close channel,
- configure bitrate,
- bus on/off,
- receive,
- controlled transmit,
- expose error/status information.

The module must not know about Qt widgets, CSV, UDS, DBC or learned rules.

### `transport/bit_timing`

Predefined and custom Classic CAN timing calculation and validation.

## Sessions and storage

### `sessions/manager`

Creates a research session and controls its lifecycle.

### `sessions/writer`

Writes raw captures and metadata without interpreting protocol meaning.

### `sessions/events`

Stores operator markers and experiment annotations.

### `sessions/integrity`

Calculates hashes and records source-file identity.

## Monitoring

### `monitor/statistics`

Counts frames, rates, IDs, DLC distributions and timing properties.

### `monitor/filtering`

Exact IDs, masks and wildcard filters independent of GUI.

### `monitor/projection`

Produces raw-log and grouped-ID views from the same frame stream.

## Active communication

### `tx/policy`

Central safety gate. No frame may be transmitted without passing this layer.

Responsibilities:

- explicit active-mode state,
- channel ownership,
- rate limits,
- confirmation requirements for dangerous sequences,
- cancellation,
- audit records.

### `tx/transactions`

Request/response lifecycle, expected IDs, timeouts and transaction history.

### `tx/sequences`

Controlled multi-step sequences. Follow-up behavior must be explicit data, not hidden GUI callbacks.

## Protocols

### `protocol/isotp`

Tested ISO-TP state machines for TX and RX, including Flow Control, block size, STmin, sequence validation and timeouts.

### `protocol/uds`

UDS services, positive/negative responses, DID/subfunction metadata and transaction interpretation.

### `protocol/j1939`

29-bit identifier decomposition, PGN extraction and address semantics.

### `protocol/dbc`

DBC loading, message matching and signal decoding behind a stable interface.

## Discovery tools

### `tools/autobaud`

Passive candidate-rate testing with repeatable scoring and complete result records.

### `tools/address_scan`

Controlled diagnostic-address discovery with strict stop/cancel behavior and complete TX/RX audit.

## Knowledge and analysis

### `knowledge/rules`

Versioned, schema-validated rules stored separately from runtime code.

### `knowledge/cases`

Operator-confirmed transaction cases with provenance.

### `analysis/timing`

Periodicity, jitter, heartbeat candidates and missing-frame detection.

### `analysis/payload`

Byte-change statistics, counters, correlations and candidate checksums.

### `analysis/anomaly`

Comparison against known sessions/cases. Results are hypotheses until confirmed by an operator.

### `analysis/assistant`

Optional local-model integration. It may explain or rank evidence but must never transmit frames directly.

## GUI

### `ui/shell`

Application shell, navigation and common status.

### `ui/monitor`

Raw/grouped views and capture controls.

### `ui/transactions`

Manual Tx/Rx and transaction history.

### `ui/discovery`

Autobaud and address-scan workflows.

### `ui/knowledge`

Rules, learned cases and evidence review.

The GUI consumes services and view models. It does not implement CANlib, ISO-TP, persistence or rule matching.