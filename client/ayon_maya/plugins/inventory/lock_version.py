from __future__ import annotations

from typing import Any

from maya import cmds

from ayon_core.pipeline import InventoryAction


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
            node = container["objectName"]
            key = "version_locked"
            if cmds.attributeQuery(key, node=node, exists=True):
                cmds.deleteAttr(f"{node}.{key}")
            cmds.addAttr(node, longName=key, attributeType=bool)
            cmds.setAttr(
                f"{node}.{key}", True, keyable=False, channelBox=True
            )
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
            node = container["objectName"]
            key = "version_locked"
            if cmds.attributeQuery(key, node=node, exists=True):
                cmds.deleteAttr(f"{node}.{key}")
        return True
