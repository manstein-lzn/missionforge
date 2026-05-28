"""Optional adapter boundary package.

Core MissionForge modules must not import this package. Adapters should import
MissionForge contracts and return refs-only results through the contracts
defined here.
"""

from .contracts import AdapterBoundary, AdapterDiagnostic, AdapterInvocation, AdapterResult

__all__ = [
    "AdapterBoundary",
    "AdapterDiagnostic",
    "AdapterInvocation",
    "AdapterResult",
]
