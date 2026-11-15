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
                    ),
            BoolDef("sampleAtPlayhead",
                    label="Sample at Playhead",
                    tooltip=(
                        "By default layout transforms are sampled at the "
                        "start frame of the folder so publishing is "
                        "deterministic. Enable this to sample at the current "
                        "timeline frame instead (legacy behaviour)."
                    ),
                    default=False),
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

        ### Sampling frame

        The JSON package stores a single static transform per loaded asset.
        By default those transforms are sampled at the start frame of the
        published folder, making publishes deterministic regardless of where
        the timeline playhead is. The Maya Scene written alongside it is not
        affected and keeps its animation keyframes.

        The sampled frame is recorded as `sample_frame` in each JSON element.
        The field is omitted when the layout is sampled at the playhead
        instead (see the "Sample at Playhead" attribute).
        """)
