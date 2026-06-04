# MissionForge SkillFoundry Integration

This integration is intentionally outside the `missionforge` Python package.

It now defaults to the TaskContract-centered MissionForge runtime path while
preserving the older SkillFoundry/FrontDesk-to-`MissionIR` bridge as an explicit
compatibility surface. MissionForge core adapters remain generic and
product-neutral.

Dependency direction:

```text
missionforge_skillfoundry -> missionforge
missionforge -> does not import missionforge_skillfoundry
```

Run the integration tests from the repository root:

```bash
PYTHONPATH=src:integrations/skillfoundry/src python3 -m unittest discover -s integrations/skillfoundry/tests
```

The default SkillFoundry compile path emits TaskContract, WorkspacePolicy, and
PermissionManifest refs under `runs/{bundle_id}/`; MissionIR APIs are retained
for migration compatibility only.

Planning:

- [SkillFoundry TaskContract path](docs/task_contract_path.md)
- [SkillFoundry integration contract](docs/skillfoundry_integration.md)
- [SkillFoundry on MissionForge plan](docs/skillfoundry_on_missionforge_plan.md)
- [SkillFoundry product shell validation plan](docs/skillfoundry_product_shell_validation_plan.md)
