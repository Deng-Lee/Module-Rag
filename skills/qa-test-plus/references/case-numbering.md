# Case Numbering

`qa-test-plus` uses project-specific groups instead of `QA_TEST.md`.

- `A`: environment and provider preflight
- `B`: CLI ingest with real fixture documents
- `C`: CLI query and query trace
- `D`: CLI eval and persisted history/trends
- `E`: dashboard API and frontend-contract consistency
- `F`: MCP stdio tool chain
- `G`: fixed profile compare
- `H`: data lifecycle
- `I`: fault injection and recovery diagnostics

Each case should map to one dominant entrypoint. If a case spans multiple entrypoints, record the primary one in `entry` and list the rest in `evidence`.
