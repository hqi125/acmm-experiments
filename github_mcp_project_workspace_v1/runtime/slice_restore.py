from __future__ import annotations

from typing import Any, Mapping

from .controller import github_controller_client, github_repository_identity


def restore_branch_refs(
    client: github_controller_client,
    identity: github_repository_identity,
    initial: Mapping[str, Any],
    non_restorable: list[str],
    *,
    allowed_new_history: bool,
) -> None:
    expected = {
        str(item["name"]): str(item["sha"])
        for item in initial.get("branches", [])
        if isinstance(item, Mapping)
        and isinstance(item.get("name"), str)
        and isinstance(item.get("sha"), str)
    }
    current = {
        str(item.get("name")): _branch_sha(item)
        for item in client.list_branches(identity.owner, identity.name)
        if isinstance(item.get("name"), str)
    }
    baseline_shas = set(expected.values())
    for name in sorted(set(current) - set(expected)):
        if name == identity.default_branch:
            non_restorable.append(f"unexpected default branch {name}")
            continue
        client.delete_ref(identity.owner, identity.name, name)
    for name, sha in expected.items():
        value = current.get(name)
        if value is None:
            client.create_ref(identity.owner, identity.name, name, sha)
        elif value != sha:
            client.update_ref(identity.owner, identity.name, name, sha, force=True)
            if not allowed_new_history and value not in baseline_shas:
                non_restorable.append(f"branch {name} advanced to unexpected Git history")


def restore_issue_snapshot(
    client: github_controller_client,
    identity: github_repository_identity,
    number: int,
    expected: Mapping[str, Any],
) -> None:
    client.update_issue(
        identity.owner,
        identity.name,
        number,
        {
            "title": expected.get("title"),
            "body": expected.get("body"),
            "state": expected.get("state"),
            "labels": list(expected.get("labels", [])),
        },
    )
    expected_comments = {
        int(item["id"]): item
        for item in expected.get("comments", [])
        if isinstance(item, Mapping) and isinstance(item.get("id"), int)
    }
    current_comments = {
        int(item["id"]): item
        for item in client.issue_comments(identity.owner, identity.name, number)
        if isinstance(item.get("id"), int)
    }
    for comment_id in sorted(set(current_comments) - set(expected_comments)):
        client.delete_issue_comment(identity.owner, identity.name, comment_id)
    for comment_id, item in expected_comments.items():
        current = current_comments.get(comment_id)
        if isinstance(current, Mapping) and current.get("body") != item.get("body"):
            client.update_issue_comment(
                identity.owner,
                identity.name,
                comment_id,
                str(item.get("body") or ""),
            )


def restore_repository_labels(
    client: github_controller_client,
    identity: github_repository_identity,
    expected_items,
) -> None:
    expected = {
        str(item["name"]): item
        for item in expected_items
        if isinstance(item, Mapping) and isinstance(item.get("name"), str)
    }
    current = {
        str(item.get("name")): item
        for item in client.list_labels(identity.owner, identity.name)
        if isinstance(item.get("name"), str)
    }
    for name in sorted(set(current) - set(expected)):
        client.delete_label(identity.owner, identity.name, name)
    for name, item in expected.items():
        color = str(item.get("color") or "000000")
        description = item.get("description") if isinstance(item.get("description"), str) else None
        if name not in current:
            client.create_label(
                identity.owner,
                identity.name,
                label=name,
                color=color,
                description=description,
            )
            continue
        current_item = current[name]
        if (
            current_item.get("color") != item.get("color")
            or current_item.get("description") != item.get("description")
        ):
            client.update_label(
                identity.owner,
                identity.name,
                name,
                new_name=name,
                color=color,
                description=description,
            )


def _branch_sha(item: Mapping[str, Any]) -> str | None:
    commit = item.get("commit")
    if isinstance(commit, Mapping) and isinstance(commit.get("sha"), str):
        return commit.get("sha")
    return None
