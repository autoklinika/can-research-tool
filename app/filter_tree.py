from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Sequence

Node = dict[str, Any]
Path = tuple[int, ...]


def default_condition() -> Node:
    return {
        "type": "condition",
        "field": "can_id",
        "operator": "eq",
        "values": ["0x18FEAE30"],
    }


def default_group(operator: str = "and") -> Node:
    children: list[Node] = []
    if operator == "not":
        children.append(default_condition())
    return {"type": "group", "operator": operator, "children": children}


def clone_tree(node: Node) -> Node:
    return deepcopy(node)


def node_at(root: Node, path: Sequence[int]) -> Node:
    node = root
    for index in path:
        children = node.get("children")
        if node.get("type") != "group" or not isinstance(children, list):
            raise ValueError("Ścieżka prowadzi przez węzeł, który nie jest grupą.")
        if index < 0 or index >= len(children):
            raise IndexError("Ścieżka węzła jest poza zakresem.")
        child = children[index]
        if not isinstance(child, dict):
            raise ValueError("Węzeł drzewa musi być obiektem.")
        node = child
    return node


def parent_at(root: Node, path: Sequence[int]) -> tuple[Node, int]:
    if not path:
        raise ValueError("Korzeń nie ma rodzica.")
    return node_at(root, path[:-1]), int(path[-1])


def append_child(root: Node, parent_path: Sequence[int], child: Node) -> Path:
    parent = node_at(root, parent_path)
    if parent.get("type") != "group":
        raise ValueError("Elementy można dodawać tylko do grupy.")
    children = parent.setdefault("children", [])
    if not isinstance(children, list):
        raise ValueError("Pole children musi być listą.")
    if parent.get("operator") == "not" and children:
        raise ValueError("Grupa NOT może zawierać dokładnie jeden element.")
    children.append(deepcopy(child))
    return tuple(parent_path) + (len(children) - 1,)


def remove_node(root: Node, path: Sequence[int]) -> Node:
    parent, index = parent_at(root, path)
    children = parent.get("children")
    if not isinstance(children, list):
        raise ValueError("Pole children musi być listą.")
    return children.pop(index)


def duplicate_node(root: Node, path: Sequence[int]) -> Path:
    parent, index = parent_at(root, path)
    children = parent.get("children")
    if not isinstance(children, list):
        raise ValueError("Pole children musi być listą.")
    if parent.get("operator") == "not":
        raise ValueError("Nie można duplikować elementu wewnątrz grupy NOT.")
    children.insert(index + 1, deepcopy(children[index]))
    return tuple(path[:-1]) + (index + 1,)


def move_node(root: Node, path: Sequence[int], offset: int) -> Path:
    parent, index = parent_at(root, path)
    children = parent.get("children")
    if not isinstance(children, list):
        raise ValueError("Pole children musi być listą.")
    target = index + offset
    if target < 0 or target >= len(children):
        return tuple(path)
    children[index], children[target] = children[target], children[index]
    return tuple(path[:-1]) + (target,)


def walk_nodes(root: Node, path: Path = ()) -> Iterable[tuple[Path, Node]]:
    yield path, root
    children = root.get("children")
    if root.get("type") == "group" and isinstance(children, list):
        for index, child in enumerate(children):
            if isinstance(child, dict):
                yield from walk_nodes(child, path + (index,))


def summarize_node(node: Node) -> str:
    if node.get("type") == "group":
        operator = str(node.get("operator", "?")).upper()
        children = node.get("children")
        count = len(children) if isinstance(children, list) else 0
        return f"{operator} ({count})"
    field = str(node.get("field", "?"))
    operator = str(node.get("operator", "?"))
    values = node.get("values")
    rendered = ", ".join(str(value) for value in values) if isinstance(values, list) else "?"
    return f"{field} {operator} {rendered}"
