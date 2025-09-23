from ayon_core.pipeline import InventoryAction
from ayon_maya.api.lib import imprint


class LockVersions(InventoryAction):
    label = "Lock versions"
    icon = "lock"
    color = "#ffffff"
    order = -1

    @staticmethod
    def is_compatible(container):
        return container.get("version_locked") is not True

    def process(self, containers):
        for container in containers:
            if container.get("version_locked") is True:
                continue
            container["version_locked"] = True
            node = container["objectName"]
            imprint(node, {"version_locked": True})
        return True


class UnlockVersions(InventoryAction):
    label = "Unlock versions"
    icon = "lock-open"
    color = "#ffffff"
    order = -1

    @staticmethod
    def is_compatible(container):
        return container.get("version_locked") is True

    def process(self, containers):
        for container in containers:
            if container.get("version_locked") is not True:
                continue
            container["version_locked"] = False
            node = container["objectName"]
            imprint(node, {"version_locked": False})
        return True
