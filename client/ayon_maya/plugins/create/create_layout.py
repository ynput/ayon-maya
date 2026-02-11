import inspect

from ayon_maya.api import plugin
from ayon_core.lib import BoolDef


class CreateLayout(plugin.MayaCreator):
    """A grouped package of loaded content"""

    identifier = "io.openpype.creators.maya.layout"
    label = "Layout"
    product_base_type = "layout"
    product_type = product_base_type
    icon = "cubes"

    description = "Create a Layout - a grouped package of loaded content"

    def get_instance_attr_defs(self):

        return [
            BoolDef("allowObjectTransforms",
                    label="Include Children Transforms",
                    tooltip="Enable this when include all the transform data"
                            "of objects"
                    )
        ]

    def get_detail_description(self):
        return inspect.cleandoc("""### Layout
        
        The Layout creator will collect all included loaded assets and their
        positioning and export them as a single `.json` package so they can
        be loaded as individual products again in Maya, or other DCCs 
        supporting the `layout` product.
        
        A Maya Scene is also written alongside the JSON package to facilitate
        quick loading and previewing of the full layout in Maya, but if you
        solely need the Maya content perhaps the Set Dress creator is the 
        better fit.
        
        Note that any vertex deformations (like vertex edits, blendshapes or 
        deformers) will not be stored as edits. Loading a Layout will purely
        consider the collect transform data and the referenced assets.
        """)
