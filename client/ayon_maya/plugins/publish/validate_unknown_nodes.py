from maya import cmds

import os
import inspect
import pyblish.api
from ayon_maya.api.action import SelectInvalidAction
from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    RepairContextAction,
    PublishValidationError,
    OptionalPyblishPluginMixin
)


def force_delete(node: str) -> None:
    """Forcefully deletes a node in the Maya scene.

    Args:
        node (str): invalid node to delete
    """
    if cmds.objExists(node):
        cmds.lockNode(node, lock=False)
        cmds.delete(node)


class ValidateSceneUnknownNodes(pyblish.api.ContextPlugin,
                                OptionalPyblishPluginMixin):
    """Checks to see if there are any unknown nodes in the scene.

    This often happens if nodes from plug-ins are used but are not available
    on this machine.

    Note: Some studios use unknown nodes to store data on (as attributes)
        because it's a lightweight node.

    This differs from validate no unknown nodes since it checks the
    full scene - not just the nodes in the instance.

    """

    order = ValidateContentsOrder
    hosts = ['maya']
    families = ["model", "rig", "mayaScene", "look", "renderlayer", "yetiRig"]
    optional = True
    label = "Unknown Nodes"
    actions = [SelectInvalidAction, RepairContextAction]

    def _is_workfile_extension_align_with_extension_mapping(self, context) -> bool:
        """Check if the workfile extension is aligned with the extension mapping.

        This is to prevent false positives when the workfile extension is not
        aligned with the extension mapping.

        Args:
            context (pyblish.api.Context): The publish context.
        """
        maya_settings = context.data["project_settings"]["maya"]
        ext_mapping = {
            item["name"]: item["value"]
            for item in maya_settings["ext_mapping"]
        }
        current_file = context.data["currentFile"]
        extension = os.path.splitext(current_file)[-1].strip(".")
        correct_extension = ext_mapping.get(context.data["productBaseType"])
        return extension == correct_extension

    @staticmethod
    def get_invalid(context) -> list:
        return cmds.ls(type="unknown")

    def process(self, context):
        """Process all the nodes in the instance"""
        if not self.is_active(context.data):
            return

        if self._is_workfile_extension_align_with_extension_mapping(context):
            self.log.warning(
                "Workfile extension is not aligned with the extension mapping."
                " Skipping unknown nodes validation to prevent false"
                " positives."
            )
            return

        invalid = self.get_invalid(context)
        if invalid:
            raise PublishValidationError(
                "Unknown nodes found: {0}".format(invalid),
                description=self.get_description()
            )

    @classmethod
    def repair(cls, context):
        for node in cls.get_invalid(context):
            try:
                force_delete(node)
            except RuntimeError as exc:
                cls.log.error(exc)

    def get_description(self) -> str:
        return inspect.cleandoc("""
            ## Unknown Nodes Found
            Unknown nodes were found in the scene. This often happens if nodes from
            plug-ins are used but are not available on this machine.
            Note: Some studios use unknown nodes to store data on (as attributes)
            because it's a lightweight node.
            ### How to Fix
            You can either:
            - Install the missing plug-in that the unknown nodes belong to.
            - Delete the unknown nodes from the scene. You can use the "Repair"
            action to automatically delete the unknown nodes.
        """)
