from pathlib import Path

from acmm.experiment_package import load_experiment_package


REPO_ROOT = Path(__file__).resolve().parents[2]
QUALIFICATION = REPO_ROOT / "github_mcp_integration_qualification_v1"
# Filled after repository test-boundary refactor.
QUALIFICATION_PACKAGE_SHA256 = "913a9d966b3782cf67b7039d9297b498256c167d172c495b6f118af5ef8bc7b7"


def test_github_mcp_qualification_package_contract_is_unchanged() -> None:
    package = load_experiment_package(QUALIFICATION)

    assert package.package_sha256 == QUALIFICATION_PACKAGE_SHA256
    assert package.schema_version == "0.2"
    assert package.experiment_id == "github_mcp_integration_qualification_v1"
    assert package.runtime is not None
    assert len(package.integrations) == 1
    integration = package.integrations[0]
    assert integration.integration_id == "github_mcp"
    assert tuple(secret.secret_id for secret in integration.secrets) == ("access_token",)
    assert tuple(integration.configuration["tools"]) == (
        "issue_read",
        "issue_write",
        "add_issue_comment",
    )
