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

After the FrontDesk product-context boundary, product workflows also own the
translation from FrontDesk intent bundles to product-domain MissionIR:

```text
FrontDeskIntentBundle
  -> ProductIntegration
  -> ProductRequest
  -> ProductContract
  -> MissionIR
  -> ProductGateSpec
```

FrontDesk core may execute product inquiry metadata, but it must not contain
product branches. Product identity enters FrontDesk through
`ProductInquiryProfile` data supplied by an integration.

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

Recommended product integration shape:

```text
missionforge_<product>/
  frontdesk_context.py     # ProductInquiryProfile
  frontdesk_bridge.py      # FrontDeskIntentBundle -> ProductRequest
  product_contract.py      # ProductContract and acceptance matrix
  compiler.py              # ProductContract -> MissionIR
  validators.py            # product validator helpers
  product_gate.py          # product-specific gate criteria
```

MissionForge core may define common protocol/result schemas:

```text
ProductInquiryProfile
FrontDeskIntentBundle
ProductIntegration
ProductCompileResult
ProductGateResult
```

Core must treat product ids, product check ids, and product slot ids as data.
It must not interpret those ids as runtime behavior switches.

## Verification

Core validation checks that product-specific adapter modules such as
`skillfoundry.py`, `frontdesk.py`, and `codexarium.py` do not exist under
`src/missionforge/adapters/`.

Product integration tests are explicit:

```bash
./scripts/validate_integrations.sh skillfoundry
```

Boundary tests should also assert:

- `src/missionforge` does not import `missionforge_<product>`;
- `src/missionforge/frontdesk` has no product-name branches;
- `src/missionforge/adapters` contains no product-specific adapter modules;
- ProductGate criteria remain product-owned.
