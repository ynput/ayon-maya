from ayon_maya.api import (
    lib,
    plugin
)
from ayon_core.lib import BoolDef, NumberDef, EnumDef


class CreateOxCache(plugin.MayaCreator):
    """Output for procedural plugin nodes of Ornatrix """

    identifier = "io.ayon.creators.maya.oxcache"
    label = "Ornatrix Cache"
    product_type = "oxcache"
    icon = "pagelines"
    description = "Ornatrix Cache"

    def get_instance_attr_defs(self):

        # Add animation data without step and handles
        remove = {"handleStart", "handleEnd"}
        defs = [attr_def for attr_def in lib.collect_animation_defs()
                if attr_def.key not in remove]
        defs.extend(
            [
                EnumDef("format",
                        items={
                            0: "Ogawa",
                            1: "HDF5",
                        },
                        label="Format",
                        default=0),
                BoolDef("renderVersion",
                        label="Use Render Version",
                        tooltip="When on, hair in the scene will be "
                                "switched to render mode and dense hair "
                                "strands will be exported. Otherwise, what "
                                "is seen in the viewport will be exported.",
                        default=True),
                EnumDef("upDirection",
                        items={
                            0: "X",
                            1: "Y",
                            2: "Z"
                        },
                        label="Up Direction",
                        default=1),
                BoolDef("exportVelocities",
                        label="Export Velocities",
                        default=False),
                NumberDef("velocityIntervalCenter",
                          label="Velocity Interval Center",
                          default=0.0),
                NumberDef("velocityIntervalLength",
                        label="Velocity Interval Length",
                        default=0.5)
            ]
        )

        return defs
