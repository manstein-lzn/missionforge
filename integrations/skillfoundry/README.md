# MissionForge SkillFoundry Integration

This integration is intentionally outside the `missionforge` Python package.

It uses the TaskContract-centered MissionForge path. MissionForge core adapters
remain generic and product-neutral.

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
PermissionManifest refs under `runs/{bundle_id}/`.

For TaskContract-native product execution, use:

```python
from missionforge_skillfoundry import run_skillfoundry_task_contract_bundle_build

report = run_skillfoundry_task_contract_bundle_build(request, workspace=".")
```

This path compiles SkillFoundry into `TaskContract`, runs the MissionForge
executor/judge boundary, validates the generated package, evaluates the
product-grade gate, and writes refs-only product reports.

Planning:

- [SkillFoundry TaskContract path](docs/task_contract_path.md)
- [SkillFoundry integration contract](docs/skillfoundry_integration.md)
