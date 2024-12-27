from ayon_maya.api import plugin
from ayon_core.lib import (
    BoolDef,
    TextDef
)


class CreateModel(plugin.MayaCreator):
    """Polygonal static geometry"""

    identifier = "io.openpype.creators.maya.model"
    label = "Model"
    product_type = "model"
    icon = "cube"
    default_variants = ["Main", "Proxy", "_MD", "_HD", "_LD"]

    write_face_sets = True
    include_shaders = False

    def get_instance_attr_defs(self):

        return [
            BoolDef("writeFaceSets",
                    label="Write face sets",
                    tooltip="Write face sets with the geometry",
                    default=self.write_face_sets),
            BoolDef("includeParentHierarchy",
                    label="Include Parent Hierarchy",
                    tooltip="Whether to include parent hierarchy of nodes in "
                            "the publish instance",
                    default=False),
            BoolDef("include_shaders",
                    label="Include Shaders",
                    tooltip="Include shaders in the geometry export.",
                    default=self.include_shaders),
        ]
