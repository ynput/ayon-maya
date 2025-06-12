from ayon_maya.api import plugin
from ayon_core.lib import BoolDef


class CreateXgen(plugin.MayaCreator):
    """Xgen"""

    identifier = "io.openpype.creators.maya.xgen"
    label = "Xgen"
    product_type = "xgen"
    icon = "pagelines"

    def get_instance_attr_defs(self):
        return [
            BoolDef("farm",
                    label="Submit to Farm",
                    default=False),
        ]
