from maya import cmds

from ayon_core.pipeline import InventoryAction
from ayon_maya.api.lib import get_reference_node


class ImportReference(InventoryAction):
    """Imports selected reference to inside of the file."""

    label = "Import Reference"
    icon = "download"
    color = "#d8d8d8"

    supported_loaders = {"ReferenceLoader", "MayaUSDReferenceLoader"}

    def process(self, containers):
        for container in containers:
            if container["loader"] not in self.supported_loaders:
                print("Not a reference, skipping")
                continue

            node = container["objectName"]
            members = cmds.sets(node, query=True, nodesOnly=True)
            ref_node = get_reference_node(members)

            ref_file = cmds.referenceQuery(ref_node, f=True)
            cmds.file(ref_file, importReference=True)

        return True  # return anything to trigger model refresh

    @classmethod
    def is_compatible(cls, container):
        return container.get("loader") in cls.supported_loaders
