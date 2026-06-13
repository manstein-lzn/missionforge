# Integration: SkillFoundry

SkillFoundry is an external product integration. It depends on MissionForge;
MissionForge core does not depend on SkillFoundry.

```text
missionforge_skillfoundry -> missionforge
missionforge -> does not import missionforge_skillfoundry
```

## Goal

Compile SkillFoundry product meaning into MissionForge primitives without adding
SkillFoundry branches to `src/missionforge`.

The active SkillFoundry facade is:

```python
from missionforge_skillfoundry import run_skillfoundry_task_contract_bundle_build
```

## Current Path

```text
SkillFoundryRequest
  -> SkillProductContract
  -> ProductAcceptanceMatrix
  -> TaskContract + WorkspacePolicy + PermissionManifest
  -> MissionForge executor/judge boundary
  -> SkillBundleManifest
  -> ProductGradeGate
  -> refs-only product report
```

## Public Contracts

- `SkillFoundryRequest`
- `SkillProductContract`
- `ProductAcceptanceMatrix`
- `SkillBundleManifest`
- `validate_skill_bundle`
- `evaluate_product_grade`
- `register_skill_bundle`
- `run_skillfoundry_task_contract_bundle_build`
- `run_skillfoundry_live_dogfood`

## Non-Goals

- no SkillFoundry imports from `src/missionforge`;
- no product-specific runtime branch;
- no deterministic core logic that infers skill semantics;
- no default live LLM dependency;
- no raw transcript ingestion unless represented by explicitly allowed source
  refs.

## Invariants

- Product semantics stay in this integration.
- MissionForge receives product meaning as data: task contracts, policies,
  rubrics, hard checks, artifact refs, and product gates.
- Default tests use faux execution.
- Live dogfood is explicit opt-in.
- Product reports and registry entries are refs-first.

## Validation

Run from the repository root:

```bash
PYTHONPATH=src:integrations/skillfoundry/src \
  python3 -m unittest discover -s integrations/skillfoundry/tests

./scripts/validate_integrations.sh skillfoundry
```
