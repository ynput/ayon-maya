from __future__ import annotations

from typing import Any

from maya import cmds

from ayon_core.pipeline import InventoryAction


def set_version_locked(container: dict[str, Any], locked: bool):
    key = "version_locked"
    if container.get("usd_container_type"):
        # Container inside a Maya USD stage
        from ayon_maya.api import usdlib
        usdlib.update_container_data(container, {key: locked})
        return

    node = container["objectName"]
    if cmds.attributeQuery(key, node=node, exists=True):
        cmds.deleteAttr(f"{node}.{key}")
    if locked:
        cmds.addAttr(node, longName=key, attributeType="bool")
        cmds.setAttr(
            f"{node}.{key}", True, keyable=False, channelBox=True
        )


class LockVersions(InventoryAction):
    label = "Lock versions"
    icon = "lock"
    color = "#ffffff"
    order = -1

    @staticmethod
    def is_compatible(container: dict[str, Any]) -> bool:
        return container.get("version_locked") is not True

    def process(self, containers: list[dict[str, Any]]) -> bool:
        for container in containers:
            if container.get("version_locked") is True:
                continue
            set_version_locked(container, True)
        return True


class UnlockVersions(InventoryAction):
    label = "Unlock versions"
    icon = "lock-open"
    color = "#ffffff"
    order = -1

    @staticmethod
    def is_compatible(container: dict[str, Any]) -> bool:
        return container.get("version_locked") is True

    def process(self, containers: list[dict[str, Any]]) -> bool:
        for container in containers:
            if container.get("version_locked") is not True:
                continue
            set_version_locked(container, False)
        return True
