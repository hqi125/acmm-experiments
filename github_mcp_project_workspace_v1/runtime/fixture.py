from __future__ import annotations

from acmm.experiment_api import prepared_environment


class github_workspace_fixture:
    def __init__(self, fixture_id: str) -> None:
        self.fixture_id = fixture_id

    def prepare(self, scenario, reset) -> prepared_environment:
        del scenario
        del reset
        raise RuntimeError(
            f"Fixture '{self.fixture_id}' is declared but materialization is not "
            "implemented in this package revision."
        )
