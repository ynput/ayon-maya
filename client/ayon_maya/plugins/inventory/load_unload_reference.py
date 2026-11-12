from __future__ import annotations

from typing import Any, Optional

from maya import cmds

from ayon_core.pipeline import InventoryAction
from ayon_maya.api.lib import get_reference_node


def get_container_reference_node(container: dict[str, Any]) -> Optional[str]:
    """Return the reference node of the container, if any.

    This is used in `is_compatible` so must be fast. Instead of querying all
    set members (which can be thousands of nodes for e.g. older containers or
    non-reference containers), only the reference nodes connected to the
    objectSet are queried.
    """
    node = container.get("objectName")
    if (
        not node
        or not cmds.objExists(node)
        or cmds.nodeType(node) != "objectSet"
    ):
        return None
    # Using listConnections because it is much faster than
    # using `cmds.sets` to query all members and filters directly
    references = cmds.listConnections(
        f"{node}.dnSetMembers",
        source=True,
        destination=False,
        type="reference",
    )
    if not references:
        return None
    return get_reference_node(references)


def is_reference_loaded(container: dict[str, Any]) -> Optional[bool]:
    """Return whether the container's reference is loaded.

    Returns None if the container has no reference node.
    """
    reference_node = get_container_reference_node(container)
    if not reference_node:
        return None
    return cmds.referenceQuery(reference_node, isLoaded=True)


class LoadReference(InventoryAction):
    """Load the unloaded reference of the selected containers."""

    label = "Load Reference"
    icon = "play"
    color = "#d8d8d8"

    @staticmethod
    def is_compatible(container: dict[str, Any]) -> bool:
        return is_reference_loaded(container) is False

    def process(self, containers: list[dict[str, Any]]) -> bool:
        for container in containers:
            reference_node = get_container_reference_node(container)
            if not reference_node:
                continue
            if cmds.referenceQuery(reference_node, isLoaded=True):
                continue
            cmds.file(loadReference=reference_node)
        return True


class UnloadReference(InventoryAction):
    """Unload the loaded reference of the selected containers."""

    label = "Unload Reference"
    icon = "pause"
    color = "#d8d8d8"

    @staticmethod
    def is_compatible(container: dict[str, Any]) -> bool:
        return is_reference_loaded(container) is True

    def process(self, containers: list[dict[str, Any]]) -> bool:
        for container in containers:
            reference_node = get_container_reference_node(container)
            if not reference_node:
                continue
            if not cmds.referenceQuery(reference_node, isLoaded=True):
                continue
            cmds.file(unloadReference=reference_node)
        return True
