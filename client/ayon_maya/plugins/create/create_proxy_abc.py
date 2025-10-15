from ayon_maya.api import (
    lib,
    plugin
)
from ayon_core.lib import (
    BoolDef,
    TextDef
)


class CreateProxyAlembic(plugin.MayaCreator):
    """Proxy Alembic for animated data"""

    identifier = "io.openpype.creators.maya.proxyabc"
    label = "Proxy Alembic"
    # product_type to be defined in the project settings
    # use product_base_type instead
    # see https://github.com/ynput/ayon-core/issues/1297
    product_base_type = product_type = "proxyAbc"
    icon = "gears"
    write_color_sets = False
    write_face_sets = False

    def get_instance_attr_defs(self):

        defs = lib.collect_animation_defs()

        defs.extend([
            BoolDef("farm",
                    label="Submit to Farm",
                    default=False),
            BoolDef("writeColorSets",
                    label="Write vertex colors",
                    tooltip="Write vertex colors with the geometry",
                    default=self.write_color_sets),
            BoolDef("writeFaceSets",
                    label="Write face sets",
                    tooltip="Write face sets with the geometry",
                    default=self.write_face_sets),
            BoolDef("worldSpace",
                    label="World-Space Export",
                    default=True),
            TextDef("nameSuffix",
                    label="Name Suffix for Bounding Box",
                    default="_BBox",
                    placeholder="_BBox"),
            TextDef("attr",
                    label="Custom Attributes",
                    default="",
                    placeholder="attr1, attr2"),
            TextDef("attrPrefix",
                    label="Custom Attributes Prefix",
                    placeholder="prefix1, prefix2")
        ])

        return defs
