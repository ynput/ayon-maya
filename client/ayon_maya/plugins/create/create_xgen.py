from ayon_maya.api import plugin
from ayon_core.lib import BoolDef


class CreateXgen(plugin.MayaCreator):
    """Xgen"""

    identifier = "io.openpype.creators.maya.xgen"
    label = "Xgen"
    # product_type to be defined in the project settings
    # use product_base_type instead
    # see https://github.com/ynput/ayon-core/issues/1297
    product_base_type = product_type = "xgen"
    icon = "pagelines"

    def get_instance_attr_defs(self):
        return [
            BoolDef("farm",
                    label="Submit to Farm",
                    default=False),
        ]
