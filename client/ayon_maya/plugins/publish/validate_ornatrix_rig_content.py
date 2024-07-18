import inspect
import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)

from ayon_maya.api import plugin
from maya import cmds

ORNATRIX_NODES = {
    "HairFromGuidesNode", "GuidesFromMeshNode",
    "MeshFromStrandsNode", "SurfaceCombNode"
}


class ValidateOrnatrixRigContent(plugin.MayaInstancePlugin,
                                 OptionalPyblishPluginMixin):
    """Adheres to the content of 'oxrig' product type

    See `get_description` for more details.

    """

    order = ValidateContentsOrder
    families = ["oxrig"]
    label = "Validate Ornatrix Content"
    actions = [ayon_maya.api.action.SelectInvalidAction]

    optional = False

    @classmethod
    def get_invalid(cls, instance):
        invalid = []
        nodes = instance.data["setMembers"]
        for node in nodes:
            # Members must have shapes
            node_shapes = cmds.listRelatives(node, shapes=True, fullPath=True)
            if not node_shapes:
                invalid.append(node)

            # Shapes must have a connection to ornatrix nodes
            ox_nodes = cmds.ls(cmds.listConnections(
                node_shapes, destination=True) or [], type=ORNATRIX_NODES)
            if not ox_nodes:
                invalid.append(node)

        return invalid

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)

        if invalid:
            raise PublishValidationError(
                title="Ornatrix content is invalid",
                message="Ornatrix content is invalid. "
                        "See log for more details.",
                description=self.get_description()
            )

    @classmethod
    def get_description(self):
        return inspect.cleandoc("""
            ### Ornatrix content is invalid

            Your oxrig instance does not adhere to the rules of an
            oxrig product type:

            - Must have the Ornatrix nodes connected to the shape
            of the mesh
            - May only have members that have shapes.
            
            Using the *Select Invalid* action will select all nodes that do
            not adhere to these rules.
        """)
