from ayon_maya.api import plugin
from ayon_core.lib import BoolDef


class CreateSetDress(plugin.MayaCreator):
    """A grouped package of loaded content"""

    identifier = "io.openpype.creators.maya.setdress"
    label = "Set Dress"
    # product_type to be defined in the project settings
    # use product_base_type instead
    # see https://github.com/ynput/ayon-core/issues/1297
    product_base_type = product_type = "setdress"
    icon = "cubes"
    exactSetMembersOnly = True
    shader = True
    default_variants = ["Main", "Anim"]

    def get_instance_attr_defs(self):
        return [
            BoolDef("exactSetMembersOnly",
                    label="Exact Set Members Only",
                    default=self.exactSetMembersOnly),
            BoolDef("shader",
                    label="Include shader",
                    default=self.shader)
        ]
