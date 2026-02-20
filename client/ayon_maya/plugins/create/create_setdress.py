import inspect

from ayon_maya.api import plugin
from ayon_core.lib import BoolDef


class CreateSetDress(plugin.MayaCreator):
    """A grouped package of loaded content"""

    identifier = "io.openpype.creators.maya.setdress"
    label = "Set Dress"
    product_base_type = "setdress"
    product_type = product_base_type
    icon = "cubes"
    exactSetMembersOnly = True
    shader = True
    default_variants = ["Main", "Anim"]

    description = "Create a Setdress - a MayaScene for sets or assemblies."

    def get_instance_attr_defs(self):
        return [
            BoolDef("exactSetMembersOnly",
                    label="Exact Set Members Only",
                    default=self.exactSetMembersOnly),
            BoolDef("shader",
                    label="Include shader",
                    default=self.shader)
        ]

    def get_detail_description(self):
        return inspect.cleandoc("""### Setdress
        
        The Setdress creator allows you to export a Maya Scene, usually
        containing multiple assets into a single package called a "setdress". 
        This is useful for organizing and managing complex scenes that require
        multiple assets to be loaded together - of potentially a variety of
        datatypes.
        
        It exports purely as a Maya Scene file (.ma or .mb) which can be
        loaded back into Maya preserving all the original data, making this
        a Maya-specific solution for set assembly and scene organization.
        """)
