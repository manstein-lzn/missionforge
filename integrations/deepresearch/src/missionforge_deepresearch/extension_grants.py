"""Extension declarations for DeepResearch product integrations.

This module declares tool surfaces. It does not implement search strategy,
source ranking, synthesis, or acceptance.
"""

from __future__ import annotations

from missionforge.task_contract import ExtensionAdapterMode, ExtensionCapability, ExtensionGrant

from .product_contract import AcademicResearchRequest


ACADEMIC_SOURCES_EXTENSION_PACKAGE = "local:extensions/pi-academic-sources"
ACADEMIC_SOURCES_EXTENSION_VERSION = "0.1.0"


def academic_deepresearch_extension_grants(request: AcademicResearchRequest) -> list[ExtensionGrant]:
    """Declare the default live tool surface for academic DeepResearch."""

    return [
        ExtensionGrant(
            grant_id=f"deepresearch-{request.request_id}-academic-sources",
            package=ACADEMIC_SOURCES_EXTENSION_PACKAGE,
            version_spec=ACADEMIC_SOURCES_EXTENSION_VERSION,
            capability=ExtensionCapability.WEB,
            requires_network=True,
            adapter_mode=ExtensionAdapterMode.UNTRUSTED_PI_EXTENSION,
            metadata={"purpose": "academic_search_fetch_citation_and_repo_lookup"},
        ),
        ExtensionGrant(
            grant_id=f"deepresearch-{request.request_id}-web",
            package="npm:pi-web-access",
            version_spec="0.10.7",
            capability=ExtensionCapability.WEB,
            requires_network=True,
            adapter_mode=ExtensionAdapterMode.UNTRUSTED_PI_EXTENSION,
            metadata={"purpose": "general_web_search_and_fetch"},
        ),
        ExtensionGrant(
            grant_id=f"deepresearch-{request.request_id}-code-search",
            package="npm:@juicesharp/rpiv-web-tools",
            version_spec="0.1.0",
            capability=ExtensionCapability.CODE_SEARCH,
            requires_network=True,
            adapter_mode=ExtensionAdapterMode.UNTRUSTED_PI_EXTENSION,
            metadata={"purpose": "github_and_repository_search"},
        ),
    ]
