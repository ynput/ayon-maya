# -*- coding: utf-8 -*-
"""Create ``Render`` instance in Maya."""

from ayon_maya.api import (
    lib_rendersettings,
    plugin
)
from ayon_core.pipeline import CreatorError
from ayon_core.lib import (
    BoolDef,
    NumberDef,
)


class CreateRenderlayer(plugin.RenderlayerCreator):
    """Create and manages renderlayer product per renderLayer in workfile.

    This generates a single node in the scene which tells the Creator to if
    it exists collect Maya rendersetup renderlayers as individual instances.
    As such, triggering create doesn't actually create the instance node per
    layer but only the node which tells the Creator it may now collect
    the renderlayers.

    """

    identifier = "io.openpype.creators.maya.renderlayer"
    product_type = "renderlayer"
    label = "Render"
    icon = "eye"

    layer_instance_prefix = "render"
    singleton_node_name = "renderingMain"

    render_settings = {}

    def apply_settings(self, project_settings):
        super().apply_settings(project_settings)
        self.render_settings = project_settings["maya"]["render_settings"]

    def create(self, product_name, instance_data, pre_create_data):
        # Only allow a single render instance to exist
        if self._get_singleton_node():
            raise CreatorError(
                "A Render instance already exists - only one can be "
                "configured.\n\n"
                "To render multiple render layers, create extra Render Setup "
                "Layers via Maya's Render Setup UI.\n"
                "Then refresh the publisher to detect the new layers for "
                "rendering.\n\n"
                "With a render instance present all Render Setup layers in "
                "your workfile are renderable instances.")

        # Apply default project render settings on create
        if self.render_settings.get("apply_render_settings"):
            lib_rendersettings.RenderSettings().set_default_renderer_settings()

        super(CreateRenderlayer, self).create(product_name,
                                              instance_data,
                                              pre_create_data)

    def get_instance_attr_defs(self):
        """Create instance settings."""

        return [
            BoolDef("review",
                    label="Review",
                    tooltip="Mark as reviewable",
                    default=True),
            BoolDef("extendFrames",
                    label="Extend Frames",
                    tooltip="Extends the frames on top of the previous "
                            "publish.\nIf the previous was 1001-1050 and you "
                            "would now submit 1020-1070 only the new frames "
                            "1051-1070 would be rendered and published "
                            "together with the previously rendered frames.\n"
                            "If 'overrideExistingFrame' is enabled it *will* "
                            "render any existing frames.",
                    default=False),
            BoolDef("overrideExistingFrame",
                    label="Override Existing Frame",
                    tooltip="Override existing rendered frames "
                            "(if they exist).",
                    default=True),

            # TODO: Should these move to submit_maya_deadline plugin?
            # Tile rendering
            BoolDef("tileRendering",
                    label="Enable tiled rendering",
                    default=False),
            NumberDef("tilesX",
                      label="Tiles X",
                      default=2,
                      minimum=1,
                      decimals=0),
            NumberDef("tilesY",
                      label="Tiles Y",
                      default=2,
                      minimum=1,
                      decimals=0),

            # Additional settings
            BoolDef("convertToScanline",
                    label="Convert to Scanline",
                    tooltip="Convert the output images to scanline images",
                    default=False),
            BoolDef("useReferencedAovs",
                    label="Use Referenced AOVs",
                    tooltip="Consider the AOVs from referenced scenes as well",
                    default=False),

            BoolDef("renderSetupIncludeLights",
                    label="Render Setup Include Lights",
                    default=self.render_settings.get("enable_all_lights",
                                                     False))
        ]
