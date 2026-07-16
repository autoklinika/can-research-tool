from __future__ import annotations

import pytest

from app.filter_tree import (
    append_child,
    clone_tree,
    default_condition,
    default_group,
    duplicate_node,
    move_node,
    node_at,
    remove_node,
    summarize_node,
    walk_nodes,
)


def test_nested_tree_editing_keeps_paths_stable() -> None:
    root = default_group("and")
    condition_path = append_child(root, (), default_condition())
    group_path = append_child(root, (), default_group("or"))
    nested_path = append_child(root, group_path, default_condition())

    assert condition_path == (0,)
    assert group_path == (1,)
    assert nested_path == (1, 0)
    assert node_at(root, nested_path)["field"] == "can_id"
    assert [path for path, _node in walk_nodes(root)] == [(), (0,), (1,), (1, 0)]


def test_duplicate_move_and_remove_node() -> None:
    root = default_group("and")
    append_child(root, (), {"type": "condition", "field": "dlc", "operator": "eq", "values": [8]})
    append_child(root, (), {"type": "condition", "field": "can_id", "operator": "eq", "values": [1]})

    duplicate_path = duplicate_node(root, (0,))
    assert duplicate_path == (1,)
    assert len(root["children"]) == 3

    moved_path = move_node(root, duplicate_path, 1)
    assert moved_path == (2,)
    removed = remove_node(root, moved_path)
    assert removed["field"] == "dlc"
    assert len(root["children"]) == 2


def test_not_group_rejects_second_child_and_duplication() -> None:
    root = default_group("not")
    with pytest.raises(ValueError, match="NOT"):
        append_child(root, (), default_condition())
    with pytest.raises(ValueError, match="NOT"):
        duplicate_node(root, (0,))


def test_clone_tree_is_deep_copy() -> None:
    root = default_group("and")
    append_child(root, (), default_condition())
    cloned = clone_tree(root)
    cloned["children"][0]["values"][0] = "0x123"
    assert root["children"][0]["values"][0] == "0x18FEAE30"


def test_summary_is_human_readable() -> None:
    group = default_group("or")
    append_child(group, (), default_condition())
    assert summarize_node(group) == "OR (1)"
    assert summarize_node(group["children"][0]) == "can_id eq 0x18FEAE30"
