"""Mission contract compatibility surface."""

from __future__ import annotations

from .freeze import ContractManifest, ExpandedMission, FrozenMissionContract, expand_mission, freeze_mission
from .ir import CapabilityProfileRef, MissionConstraint, MissionIR, MissionObjective
from .profiles import CapabilityProfile, ProfileExpansion, ProfileRegistry, VerificationProfile
from .runner import MissionResult

__all__ = [
    "CapabilityProfileRef",
    "CapabilityProfile",
    "ContractManifest",
    "ExpandedMission",
    "FrozenMissionContract",
    "MissionConstraint",
    "MissionIR",
    "MissionObjective",
    "MissionResult",
    "ProfileExpansion",
    "ProfileRegistry",
    "VerificationProfile",
    "expand_mission",
    "freeze_mission",
]
