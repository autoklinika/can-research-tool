# CAN Research Tool

CAN Research Tool (CRT) is a research application for capturing, organizing and analysing CAN traffic without modifying the source session data.

## Current implementation

The repository currently contains **Stage 1 of the Global Filter Engine**:

- framework-independent C++20 domain model,
- nested `AND`, `OR` and `NOT` groups,
- three-state evaluation: `MATCH`, `NO_MATCH`, `UNAVAILABLE`,
- basic CAN ID, STD/EXT, DLC and relative-time conditions,
- validation and compilation into an executable predicate,
- unit tests and GitHub Actions CI.

The detailed design is available in [`docs/global-filter-engine-stage1.md`](docs/global-filter-engine-stage1.md).

## Build and test

```bash
cmake -S . -B build -DCRT_BUILD_TESTS=ON
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

## Core rule

Filtering never controls capture or storage. The complete CAN stream remains the source of truth; filters only select records for presentation, analysis, comparison and export.
