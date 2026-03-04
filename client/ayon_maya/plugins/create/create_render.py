# -*- coding: utf-8 -*-
"""Create ``Render`` instance in Maya."""
import typing
from typing import Optional, Any

from ayon_core.lib import (
    BoolDef,
    EnumDef,
    NumberDef,
)
from ayon_core.pipeline.create import get_product_name, ProductTypeItem
from ayon_maya.api import (
    lib_rendersettings,
    plugin
)

if typing.TYPE_CHECKING:
    from ayon_core.pipeline import CreatedInstance


class CreateRender(plugin.RenderlayerCreator):
    """Create and manages renderlayer product per renderLayer in workfile.

    This generates a single node in the scene which tells the Creator to if
    it exists collect Maya rendersetup renderlayers as individual instances.
    As such, triggering create doesn't actually create the instance node per
    layer but only the node which tells the Creator it may now collect
    the renderlayers.

    """

    identifier = "io.openpype.creators.maya.renderlayer"
    product_base_type = "renderlayer"  # this won't be integrated
    product_type = product_base_type
    label = "Render"
    icon = "eye"

    singleton_node_name = "renderingMain"

    render_target = "farm"
    render_settings = {}

    def apply_settings(self, project_settings):
        super().apply_settings(project_settings)
        self.render_settings = project_settings["maya"]["render_settings"]

    def get_product_type_items(self) -> list[ProductTypeItem]:
        if self.product_type_items:
            return self.product_type_items
        # Make sure there is one item with product type 'render'
        # - this is to avoid having product type being 'renderlayer'
        return [
            ProductTypeItem(product_type="render")
        ]

    def get_product_name(
        self,
        project_name: str,
        folder_entity: dict[str, Any],
        task_entity: Optional[dict[str, Any]],
        variant: str,
        host_name: Optional[str] = None,
        instance: Optional["CreatedInstance"] = None,
        project_entity: Optional[dict[str, Any]] = None,
        product_type: Optional[str] = None,
    ) -> str:
        if host_name is None:
            host_name = self.create_context.host_name

        return get_product_name(
            project_name=project_name,
            folder_entity=folder_entity,
            task_entity=task_entity,
            host_name=host_name,
            product_base_type="render",
            product_type=product_type or "render",
            variant=variant,
            project_settings=self.project_settings,
        )

    def create(self, product_name, instance_data, pre_create_data):
        # Only allow a single render instance to exist
        if (
                not self._get_singleton_node()
                and self.render_settings.get("apply_render_settings")
        ):
            lib_rendersettings.RenderSettings().set_default_renderer_settings()

        super().create(product_name, instance_data, pre_create_data)

    def get_instance_attr_defs(self):
        """Create instance settings."""

        render_target_items: dict[str, str] = {
            "local": "Local machine rendering",
            "local_no_render": "Use existing frames (local)",
            "farm": "Farm Rendering",
        }

        return [
            EnumDef("render_target",
                    items=render_target_items,
                    label="Render target",
                    default=self.render_target),
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
