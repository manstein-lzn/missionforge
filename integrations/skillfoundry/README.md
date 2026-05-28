# MissionForge SkillFoundry Integration

This integration is intentionally outside the `missionforge` Python package.

It preserves the migration bridge from SkillFoundry/FrontDesk-style source refs
to MissionForge `MissionIR`, while keeping MissionForge core adapters generic
and product-neutral.

Dependency direction:

```text
missionforge_skillfoundry -> missionforge
missionforge -> does not import missionforge_skillfoundry
```

Run the integration tests from the repository root:

```bash
PYTHONPATH=src:integrations/skillfoundry/src python3 -m unittest discover -s integrations/skillfoundry/tests
```

The default MissionForge validation path does not run product integrations.
