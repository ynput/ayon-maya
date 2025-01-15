import inspect
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
        defs = [
            attr_def for attr_def in lib.collect_animation_defs(
                create_context=self.create_context)
            if attr_def.key not in remove
        ]
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
                BoolDef("useWorldCoordinates",
                        label="Use World Coordinates",
                        default=False),
                BoolDef("exportStrandData",
                        label="Export Strand Data",
                        default=True),
                BoolDef("exportSurfacePositions",
                        label="Export Surface Positions",
                        default=False),
                # TODO: Should we support this?
                # BoolDef("oneObjectPerFile",
                #         label="One Object Per File",
                #         default=False),
                BoolDef("exportStrandIds",
                        label="Export Strand Ids",
                        default=True),
                BoolDef("exportStrandGroups",
                        label="Export Strand Groups",
                        default=True),
                BoolDef("exportWidths",
                        label="Export Widths",
                        default=True),
                BoolDef("exportTextureCoordinates",
                        label="Export Texture Coordinates",
                        default=True),
                BoolDef("exportNormals",
                        label="Export Normals",
                        default=False),
                BoolDef("exportVelocities",
                        label="Export Velocities",
                        default=False),
                NumberDef("velocityIntervalCenter",
                          label="Velocity Interval Center",
                          default=0.0),
                NumberDef("velocityIntervalLength",
                          label="Velocity Interval Length",
                          default=0.5),
                BoolDef("unrealEngineExport",
                        label="Unreal Engine Export",
                        default=False),
                BoolDef("exportEachStrandAsSeparateObject",
                        label="Export Each Strand As Separate Object",
                        default=False)
            ]
        )

        return defs

    def get_detail_description(self):
        return inspect.cleandoc("""
            ### Ornatrix Cache
            
            The Ornatrix cache creator allows you to cache Ornatrix
            hair shapes to an Ornatrix Alembic.
            
            For more details, see the [AYON Maya Ornatrix Artist documentation](https://ayon.ynput.io/docs/addon_maya_ornatrix_artist/).
        """  # noqa
        )
