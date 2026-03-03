from ayon_maya.api import plugin
from ayon_core.lib import BoolDef


class CreateXgen(plugin.MayaCreator):
    """Xgen"""

    identifier = "io.openpype.creators.maya.xgen"
    label = "Xgen"
    product_base_type = "xgen"
    product_type = product_base_type
    icon = "pagelines"

    def get_instance_attr_defs(self):
        return [
            BoolDef("farm",
                    label="Submit to Farm",
                    default=False),
        ]
