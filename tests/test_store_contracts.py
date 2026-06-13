from __future__ import annotations

import unittest

from missionforge.json_store import JsonWorkspaceStore
from missionforge.stores import ArtifactStore, EventLogStore, RunStore


class StoreContractTests(unittest.TestCase):
    def test_json_workspace_store_satisfies_store_protocols(self) -> None:
        store = JsonWorkspaceStore(".")

        self.assertIsInstance(store, RunStore)
        self.assertIsInstance(store, ArtifactStore)
        self.assertIsInstance(store, EventLogStore)


if __name__ == "__main__":
    unittest.main()
