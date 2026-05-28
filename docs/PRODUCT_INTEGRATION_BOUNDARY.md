# Product Integration Boundary

MissionForge core adapters are protocol boundaries. They translate external
processes, providers, hosts, or command protocols into MissionForge contracts.
They must not carry product-specific task semantics.

## Rule

```text
Task instance facts -> MissionIR
Reusable task features -> profiles
Executable checks -> validators
Facts and artifacts -> evidence refs
External protocol conversion -> adapters
Product workflows -> external integrations
```

## Allowed In `src/missionforge/adapters`

- CLI/RPC host shells
- read-only observation surfaces
- explicit control request writers
- worker/process adapters that consume committed `WorkUnitContract` objects
- provider adapters that emit core proposal/review contracts
- shared refs-only adapter contracts

## Not Allowed In `src/missionforge/adapters`

- product-specific source compilers
- task-specific workflow branches
- benchmark-specific adapters
- registry or package publishing flows
- product profile policy
- product names as runtime behavior switches

## Integration Shape

Product integrations depend on MissionForge:

```text
missionforge_<product> -> missionforge
missionforge -> does not import missionforge_<product>
```

The SkillFoundry migration bridge now follows this rule under
`integrations/skillfoundry/`.

## Verification

Core validation checks that product-specific adapter modules such as
`skillfoundry.py`, `frontdesk.py`, and `codexarium.py` do not exist under
`src/missionforge/adapters/`.

Product integration tests are explicit:

```bash
./scripts/validate_integrations.sh skillfoundry
```
