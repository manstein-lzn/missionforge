# Module: Adapter Contracts

## Goal

Define shared refs-only contracts for optional MissionForge adapters without
making adapter code part of the core runtime import graph.

These contracts are the boundary layer for follow-on PiWorker, SkillFoundry,
and host adapter goals. They do not implement any adapter behavior.

## Scope

- adapter boundary declarations
- adapter invocation refs
- adapter result refs
- adapter diagnostic refs
- import-boundary protection
- raw payload field rejection

## Non-Goals

- this module does not implement the faux PiWorker adapter
- no real PiWorker execution
- no SkillFoundry compiler behavior
- no LangGraph adapter
- no HTTP service
- no live LLM
- no provider credentials

## Current Status

Goal 6.0 implemented the adapter package boundary and shared adapter contract
objects.

Goal 6A builds on these contracts with `missionforge.adapters.piworker` and
`missionforge.workers` while keeping MissionForge core adapter-free.

Implemented:

- `src/missionforge/adapters/__init__.py`
- `src/missionforge/adapters/contracts.py`
- `AdapterBoundary`
- `AdapterInvocation`
- `AdapterDiagnostic`
- `AdapterResult`

The root `missionforge` package does not import or re-export adapter contracts.
Core runtime modules must remain adapter-free.

## Public Contracts

- `AdapterBoundary`
- `AdapterInvocation`
- `AdapterDiagnostic`
- `AdapterResult`

## Invariants

- Adapter contracts are refs-only.
- Adapter contracts are JSON-compatible.
- Raw body, raw payload, raw prompt, raw transcript, and secret-shaped fields
  are rejected.
- Adapter modules may import MissionForge contracts.
- MissionForge core modules must not import `missionforge.adapters`.
- Adapter results are evidence or diagnostics, not acceptance.
- Completion remains owned by `VerificationResult.status`.

## Dependencies

- shared contract helpers
- safe ref validation
- stable JSON hashing

## Verification Strategy

- adapter contract round-trip tests
- unsafe ref rejection tests
- raw payload field rejection tests
- provider-secret-shaped field rejection tests
- import-boundary AST tests
- package-root export tests
- absence of concrete adapter implementation modules in Goal 6.0

## Verification Evidence

Goal 6.0:

```bash
PYTHONPATH=src python3 -m unittest tests/test_adapter_contracts.py tests/test_adapter_import_boundaries.py
# Ran 10 tests: OK
```

Goal 6A:

```bash
PYTHONPATH=src python3 -m unittest tests/test_piworker_adapter_contracts.py tests/test_faux_piworker_adapter.py tests/test_piworker_import_boundaries.py tests/test_adapter_import_boundaries.py
# Ran 16 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 106 tests: OK
```

Goal 6B:

```bash
PYTHONPATH=src python3 -m unittest tests/test_skillfoundry_adapter_contracts.py tests/test_skillfoundry_compiler.py tests/test_skillfoundry_import_boundaries.py tests/test_adapter_import_boundaries.py tests/test_piworker_import_boundaries.py
# Ran 24 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 124 tests: OK
```

Goal 6C:

```bash
PYTHONPATH=src python3 -m unittest tests/test_host_cli_adapter.py tests/test_host_observation_adapter.py tests/test_host_import_boundaries.py tests/test_adapter_import_boundaries.py tests/test_piworker_import_boundaries.py tests/test_skillfoundry_import_boundaries.py
# Ran 17 tests: OK

PYTHONPATH=src python3 -m unittest discover -s tests
# Ran 131 tests: OK
```

## Open Questions

- Should adapter contracts live entirely under `missionforge.adapters`, or
  should stable protocol types move to a future `missionforge.boundaries`
  namespace?
- Should `AdapterResult.metrics` get a stricter numeric-only schema before
  live adapters exist?
- Should adapter diagnostics be stored directly as evidence records before
  live adapters exist?
