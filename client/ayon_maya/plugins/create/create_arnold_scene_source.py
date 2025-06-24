from maya import cmds

from ayon_maya.api import (
    lib,
    plugin
)
from ayon_core.lib import (
    NumberDef,
    BoolDef,
    UISeparatorDef,
    UILabelDef
)


class CreateArnoldSceneSource(plugin.MayaCreator):
    """Arnold Scene Source"""

    identifier = "io.openpype.creators.maya.ass"
    label = "Arnold Scene Source"
    product_type = "ass"
    icon = "cube"
    settings_name = "CreateAss"

    # File Type Specific Options
    compressed = False
    boundingBox = True

    # Export
    expandProcedurals = False
    motionBlur = True
    motionBlurKeys = 2
    motionBlurLength = 0.5
    maskOptions = False
    maskCamera = False
    maskLight = False
    maskShape = False
    maskShader = False
    maskOverride = False
    maskDriver = False
    maskFilter = False
    maskColor_manager = False
    maskOperator = False
    maskImager = False

    def get_instance_attr_defs(self):

        defs = lib.collect_animation_defs(create_context=self.create_context)

        defs.extend([
            BoolDef("farm",
                    label="Submit to Farm",
                    default=False),
            BoolDef("motionBlur",
                    label="Motion Blur",
                    default=self.motionBlur),
            NumberDef("motionBlurKeys",
                      label="Motion Blur Keys",
                      decimals=0,
                      default=self.motionBlurKeys),
            NumberDef("motionBlurLength",
                      label="Motion Blur Length",
                      decimals=3,
                      default=self.motionBlurLength),
            BoolDef("expandProcedural",
                    label="Expand Procedurals",
                    default=self.expandProcedurals),
            BoolDef("compressed",
                    label="Use gzip Compression (.ass.gz)",
                    default=self.compressed),

            # Masks
            UISeparatorDef("maskSectionStart"),
            UILabelDef("<b>Export</b>", key="maskHeaderLabel"),
            BoolDef("maskOptions",
                    label="Options",
                    tooltip="Export Options",
                    default=self.maskOptions),
            BoolDef("maskCamera",
                    label="Cameras",
                    tooltip="Export Cameras",
                    default=self.maskCamera),
            BoolDef("maskLight",
                    label="Lights",
                    tooltip="Export Lights",
                    default=self.maskLight),
            BoolDef("maskShape",
                    label="Shapes",
                    tooltip="Export Shapes",
                    default=self.maskShape),
            BoolDef("maskShader",
                    label="Shaders",
                    tooltip="Export Shaders",
                    default=self.maskShader),
            BoolDef("maskOverride",
                    label="Override Nodes",
                    tooltip="Export Override Nodes",
                    default=self.maskOverride),
            BoolDef("maskDriver",
                    label="Drivers",
                    tooltip="Export Drivers",
                    default=self.maskDriver),
            BoolDef("maskFilter",
                    label="Filters",
                    tooltip="Export Filters",
                    default=self.maskFilter),
            BoolDef("maskOperator",
                    label="Operators",
                    tooltip="Export Operators",
                    default=self.maskOperator),
            BoolDef("maskColor_manager",
                    label="Color Managers",
                    tooltip="Export Color Managers",
                    default=self.maskColor_manager),
            BoolDef("maskImager",
                    label="Imagers",
                    tooltip="Export Imagers",
                    default=self.maskImager),
            BoolDef("boundingBox",
                    label="Bounding Box",
                    tooltip="Export Bounding Box",
                    default=self.boundingBox),
        ])

        return defs


class CreateArnoldSceneSourceProxy(CreateArnoldSceneSource):
    """Arnold Scene Source Proxy

    This product type facilitates working with proxy geometry in the viewport.
    """

    identifier = "io.openpype.creators.maya.assproxy"
    label = "Arnold Scene Source Proxy"
    product_type = "assProxy"
    icon = "cube"

    def create(self, product_name, instance_data, pre_create_data):
        instance = super(CreateArnoldSceneSource, self).create(
            product_name, instance_data, pre_create_data
        )

        instance_node = instance.get("instance_node")

        proxy = cmds.sets(name=instance_node + "_proxy_SET", empty=True)
        cmds.sets([proxy], forceElement=instance_node)
