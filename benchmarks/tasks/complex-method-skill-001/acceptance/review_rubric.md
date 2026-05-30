# Blind Review Rubric

Reviewers must judge the artifact without knowing whether it came from direct PiWorker chat or MissionForge orchestration.

Score the deliverable on accepted artifact quality, not narrative confidence.

- Product fit: the package should help a local Codex user reuse a complex engineering-method workflow.
- Boundary safety: the package must not expose raw conversations, provider payloads, credentials, or private project facts.
- Installability: package refs should be local, deterministic, and under `package/`.
- Verification fit: manifest and README should make local product-grade checks plausible.
- Failure clarity: if incomplete, findings should map to worker failure, FrontDesk failure, ProductIntegration coverage miss, runtime/verifier failure, ProductGate failure, hidden acceptance failure, or reviewer rejection.
