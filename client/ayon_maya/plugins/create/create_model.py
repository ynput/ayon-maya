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
    product_base_type = "model"
    icon = "cube"
    default_variants = ["Main", "Proxy", "_MD", "_HD", "_LD"]


    write_face_sets = True
    include_shaders = False

    def get_instance_attr_defs(self):

        return [
            # TODO: Differentiate this more clearly from the exact Alembic
            #  export feature to 'write face sets'
            #  This particular toggle here implements an additional process
            #  step for exports where ANY shader assignment is turned into an
            #  explicit 'per face' assignment even if it was just a regular
            #  full object material assignment in Maya.
            #  See: https://github.com/ynput/ayon-maya/pull/37
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
            # TODO: Remove these `attr` and `attrPrefix` attributes to avoid
            #  confusion. This currently does NOT influence the model product
            #  `mayaScene` nor `Alembic` output. It only influences the Maya
            #  USD exported output. Which is confusing, because the attr def
            #  is ALSO exposed in the Alembic export plugin as attr defs.
            #  Preferably we unify them or clean it up some way so they are
            #  not duplicated.
            TextDef("attr",
                    label="Custom Attributes",
                    tooltip="Relevant to Maya USD Export only",
                    default="",
                    placeholder="attr1, attr2"),
            TextDef("attrPrefix",
                    label="Custom Attributes Prefix",
                    tooltip="Relevant to Maya USD Export only",
                    placeholder="prefix1, prefix2"),
        ]
