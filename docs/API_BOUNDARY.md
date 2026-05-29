# API Boundary

Last updated: 2026-05-29

Status: `reference`

## Goal

Keep the public MissionForge surface small enough that application teams extend
the system through contracts instead of patching runtime internals.

The package root is the stable import surface. Module-level imports may exist
for internal implementation and focused tests, but they should not be treated as
application contracts unless this document says so.

## Stable Root Surface

Application code may depend on these categories from `missionforge`:

- Mission contracts: `MissionIR`, `MissionObjective`, `MissionConstraint`,
  `CapabilityProfileRef`
- Runtime facade: `MissionRuntime`, `MissionResult`
- Freeze and contract outputs: `ExpandedMission`, `FrozenMissionContract`,
  `ContractManifest`, `expand_mission`, `freeze_mission`
- Evidence contracts and stores: `ArtifactRef`, `EvidenceRef`,
  `EvidenceLedger`, `EvidenceRecord`, `EvidenceSnapshot`,
  `FileEvidenceStore`, `InMemoryEvidenceStore`
- Metrics: `MetricEvent`, `MetricProjection`, `MetricTrustLevel`,
  `MetricStore`, `project_metric_events`
- Profiles: `CapabilityProfile`, `VerificationProfile`, `ProfileExpansion`,
  `ProfilePack`, `ProfileRegistry`
- Revision contracts: `MissionRevision`, `MissionRevisionRequest`,
  `MissionRevisionDecision`, `MissionRevisionWorkflow`,
  `MissionRevisionStore`, `apply_mission_revision`
- Store protocols and JSON backend: `RunStore`, `ArtifactStore`,
  `EventLogStore`, `JsonWorkspaceStore`
- Operator-safe audit: `MissionRunAudit`, `build_run_audit`
- Verifier contracts: `VerificationSpec`, `VerificationResult`,
  `ValidatorSpec`, `ValidatorResult`, `Verifier`, `verify_spec`,
  `run_validator`
- Shared enums and errors: `ContractValidationError`, `MissionValidationError`,
  `VerificationStatus`, `ValidatorMode`, `ValidatorSeverity`,
  `EvidenceTrustLevel`

## Formal Authoring Surface

FrontDesk is the formal MissionIR authoring tool. The root surface exposes only
generic authoring contracts and facade methods, not product-specific
SkillFoundry or Codexarium behavior.

Stable categories:

- `FrontDesk` authoring facade
- `FrontDeskAuthoringSession`
- semantic lock, mission brief, profile recommendation, mission plan, audit,
  approval, and freeze manifest contracts
- deterministic compiler from approved FrontDesk artifacts to `MissionIR`
- refs-only inspect and handoff results
- runtime feedback recommendations that may draft revision requests but cannot
  approve or apply them

FrontDesk output must still enter the normal `MissionIR -> expand_mission ->
freeze_mission -> MissionRuntime` path.

## Experimental Root Surface

These are currently exported but should be treated as lower-level or
experimental:

- `RuntimeEngine`
- controlled steering proposal/review contract objects
- work-unit and harness internals

They are useful for MissionForge development and advanced integration tests.
They should not be the default path for product integrations.

## Internal Surface

These are implementation details and should not be re-exported from the package
root:

- `ActiveMissionContract`
- `RuntimeContractView`
- PI Agent adapter classes
- faux PiWorker adapter classes
- product integration compilers such as SkillFoundry
- adapter-private runtime modules

Internal modules may import these directly when needed. Applications should use
`MissionRuntime`, `MissionIR`, profiles, validators, evidence refs, metrics,
and revision contracts instead.

## Adapter Boundary

Adapters may translate an external protocol into core contracts. They must not
carry product-specific MissionForge truth.

Allowed:

- CLI or host shell command envelopes;
- refs-only operator results;
- PI Agent / PiWorker construction boundary;
- external integration code under `integrations/*`;
- adapter contracts that emit `MissionIR`, `WorkUnitContract`, evidence refs,
  metric events, or review decisions.

Not allowed:

- SkillFoundry-specific branches under `src/missionforge`;
- mission-name branches;
- benchmark-name branches;
- customer-specific validators under `missionforge.*`;
- adapter-private metric keys that change runtime routing;
- worker output that closes verification without the verifier.

## Product Integration Rule

Product integrations should depend on MissionForge in this order:

1. Use FrontDesk or external integration code to compile product facts into
   `MissionIR`.
2. Use profile refs and `ProfilePack` for reusable capability semantics.
3. Use validators and manual gates for completion checks.
4. Use evidence refs for proof.
5. Use metric events for diagnostics.
6. Use mission revisions for frozen-contract changes.
7. Use `MissionRuntime` for execution.

If a product needs a branch in runtime code, the product boundary has failed.
