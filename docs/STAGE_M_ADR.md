# Stage M M0/M1/M4: CRT integration boundary

Decision: CRT owns project/session identifiers, capture files, imported originals,
markers, decoder configuration, deterministic analyses and their provenance. Raw
frames and original files remain immutable source evidence. AI Platform owns
provider execution, prompt orchestration and remote transport. ERS owns its own
engineering records. Link ERS records using external identifiers (system, record
type, record id) associated with CRT project/session/artifact ids in the integrating
system; do not substitute ERS ids for CRT ids or copy ERS authoritative records
into CRT. No ERS synchronization or network transport is implemented here.

The boundary is a versioned local JSON export, not access to hardware or an
extension permission that allows writes. The new exporter has no CAN dependency,
TX operation or remote execution hook. Existing passive capture safeguards are
unchanged. A recorded capture mode is metadata, not proof of hardware silence;
missing modes must remain unknown, never inferred from project defaults.

Use an existing, ready session in a quiescent project. The exporter opens SQLite
read-only with immutable mode to avoid SQLite creating WAL/SHM files, rejects a
nonempty WAL (close writers/checkpoint using normal CRT tooling first), and does
not call CrtProject.open, migrate databases or build session indexes. Immutable
mode requires callers to stop concurrent project writes. File hashing detects
ordinary concurrent changes, but does not provide a transaction across all files
or defend against a hostile process replacing filesystem entries during export.
Missing files, traversal, absolute paths, escaping symlinks and hash mismatches
fail the operation. No source repair is attempted.

## Version 1 wire contracts

`app.platform_export` is the producer contract. Objects always contain `schema_id`
and integer `schema_version` (currently 1). Consumers must reject unknown major
versions, tolerate additive fields, and preserve source ids as opaque strings.
Breaking field/meaning changes require a new version. JSON is UTF-8 with sorted
keys, compact separators, no NaN and no trailing newline for hashing. SHA-256
covers those bytes; the CLI adds a newline only for display. There is no export
creation timestamp or random export id. Identical inputs/selections produce
identical bytes. JSON hashes are integrity identifiers, not signatures.

| Schema id | Required content |
| --- | --- |
| `crt.platform.session-export` | algorithm_version, project_id, session_id, source, capture_mode, time_bounds, frame_count, catalog_frame_count, files, artifacts, provenance, omitted_data, limitations |
| `crt.platform.ai-context` | algorithm_version, project_id, session_id, manifest_sha256, source_files, question, evidence, maximum_bytes, omitted_data, limitations |
| `crt.platform.ai-finding` | status, provider, model, context_sha256, project_id, session_id, sources, artifacts, title, description |

File references contain `relative_path` (portable POSIX project-relative path),
`sha256` (lowercase hex), `bytes` (nonnegative integer), `media_type` and `role`.
Roles currently include raw_capture, original_import and analysis_artifact.
Manifests reference raw session and linked original import files without embedding
them. Source metadata includes kind/header_source, adapter, bitrate, channel and
started_at_utc. Null bitrate/channel mean unavailable. Time bounds are minimum and
maximum frame timestamp_ns (null for empty sessions), not assumed UTC. Counts are
computed by streaming raw frames; catalog_frame_count preserves the stored count.
Decoder identity is explicitly unknown unless recorded in selected artifact
metadata; current project decoder configuration must not be mistaken for the
configuration used by an earlier analysis.

Artifacts preserve existing ids, analysis_run_id, artifact_type, schema_version,
provider_id/version, algorithm_version, sources, metadata and created_at_utc, plus
a verified file reference and hash. Source references retain the existing domain
semantics (session/frame/frame range). Artifacts must reference only the selected
session; comparison artifacts involving other sessions require a future explicit
multi-session contract. No artifact is selected automatically. Missing historical
hashes are replaced in the export by hashes of current bytes; this establishes
export-time integrity only, not historical integrity.

Context packages primarily consume explicitly selected deterministic artifact
JSON payloads. Each evidence entry has `artifact` (the manifest reference) and
`selected_payload` (the selected artifact's entire JSON payload). Callers should
select bounded deterministic summaries; this builder does not establish whether
a third-party provider is deterministic or trustworthy. No raw frames or whole
project content is silently embedded. Selection includes artifact metadata and
source references, so callers should inspect these before external disclosure.
The default total canonical package limit is 1 MiB; oversized selections fail
instead of silently truncating evidence. Empty selection is allowed and explicit.
Questions change the context hash. Manifest hashes bind the source snapshot;
context hashes bind exactly the package provided to the AI.

## Advisory findings and existing storage

`ai_finding` builds a payload only, always with status `suggested`. Provider/model,
context hash, source file hashes and selected artifact ids/hashes are retained.
There is no automated finding ingestion or fact update. Persist this payload with
the existing ArtifactWriter as artifact_type `crt.platform.ai-finding`, schema
version 1, using an existing analysis run and ArtifactSource records; persist the
context as a separate artifact for reproducibility. Do not introduce parallel
AI tables or overwrite an existing artifact. If surfaced as a domain Finding,
use `FindingStatus.TO_VERIFY`, ai_provider/ai_model and artifact evidence referring
to the advisory payload. Review uses existing status history. Confirmation is an
operator decision and never rewrites raw evidence or deterministic results.

## Local CLI

```sh
crt-platform-export /path/to/project SESSION_ID > /tmp/manifest.json
crt-platform-export /path/to/project SESSION_ID --artifact ARTIFACT_ID \
  --question 'Which candidate merits review?' > /tmp/context.json
# Without installing the script:
python -m app.platform_export_cli /path/to/project SESSION_ID
```

Repeat --artifact to select more evidence; --maximum-bytes sets the context limit.
Choose a new output destination outside source evidence. The CLI writes stdout
only; no upload, GUI, production change or vehicle control is implemented.
