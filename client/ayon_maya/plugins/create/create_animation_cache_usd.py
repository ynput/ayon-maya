"""Create Animation Cache USD instance.

This creator enables publishing of animated USD assets that were edited
as Maya data. The animation cache is exported as USD and can be used as
a contribution layer in the shot composition.

Workflow:
1. Load USD asset in shot with "Edit as Maya Data"
2. Animate the geometry
3. Create animationCacheUsd instance
4. Publish to generate:
   - animation_cache.usda: Sparse animation data
   - animation_contribution.usda: Override layer for shot USD composition
"""

from ayon_maya.api import plugin, lib
from ayon_core.lib import (
    BoolDef,
    EnumDef,
    NumberDef,
    TextDef
)
from maya import cmds


class CreateAnimationCacheUsd(plugin.MayaCreator):
    """Create Animation Cache USD from Maya scene objects"""

    identifier = "io.ayon.creators.maya.animationcacheusd"
    label = "Animation Cache USD"
    product_base_type = "usd"
    product_type = "animationCacheUsd"
    icon = "circle-play"
    description = "Create Animation Cache USD Export"

    def get_publish_families(self):
        return ["animationCacheUsd", "usd"]

    def get_attr_defs_for_instance(self, instance):
        """Get attribute definitions for this instance."""

        # Get animation frame range defaults
        defs = lib.collect_animation_defs(
            create_context=self.create_context)

        # Animation sampling strategy
        defs.append(
            EnumDef("animationSampling",
                    label="Animation Sampling",
                    items={
                        "sparse": "Sparse (keyframes only)",
                        "per_frame": "Per Frame",
                        "custom": "Custom Step"
                    },
                    default="sparse",
                    tooltip=(
                        "sparse: Only animated keys (minimal file size)\n"
                        "per_frame: All frames sampled (complete data)\n"
                        "custom: Custom step size for sampling"
                    ))
        )

        # Custom step size (visible when custom selected)
        custom_step_def = NumberDef(
            "customStepSize",
            label="Custom Step Size",
            default=1.0,
            decimals=3,
            tooltip=(
                "Step size for animation sampling.\n"
                "1.0 = every frame, 0.5 = two samples per frame"
            )
        )
        defs.append(custom_step_def)

        # Department/layer selection
        defs.append(
            EnumDef("department",
                    label="Department",
                    items={
                        "auto": "Auto-detect from task",
                        "animation": "Animation",
                        "layout": "Layout",
                        "cfx": "CFX",
                        "fx": "FX"
                    },
                    default="auto",
                    tooltip=(
                        "Department layer for the contribution.\n"
                        "auto: Detect from current task context"
                    ))
        )

        # Asset prim path input (fallback if auto-detection fails)
        defs.append(
            TextDef("originalAssetPrimPath",
                    label="Original Asset Prim Path",
                    default="",
                    placeholder="/assets/character/cone_character",
                    tooltip=(
                        "Full USD prim path of the original asset in the "
                        "shot stage.\n\n"
                        "AUTO-DETECTED: This is normally resolved "
                        "automatically from loaded USD containers (the prims "
                        "with Ayon metadata). You do NOT need to fill this "
                        "manually unless auto-detection fails.\n\n"
                        "If auto-detection fails, enter the full prim path "
                        "as it appears in the USD stage outliner.\n"
                        "Example: /assets/character/cone_character"
                    ))
        )

        # USD format
        defs.append(
            EnumDef("defaultUSDFormat",
                    label="File Format",
                    items={
                        "usdc": "Binary",
                        "usda": "ASCII"
                    },
                    default="usda",
                    tooltip="Output USD file format")
        )

        # Reset Xform Stack (prevent double-transforms from layout)
        defs.append(
            BoolDef("resetXformStack",
                    label="Reset Xform Stack",
                    default=True,
                    tooltip=(
                        "Add !resetXformStack! to the exported cache prims.\n"
                        "This prevents double-transforms when the cache is "
                        "composed as a sublayer under an Xform that still "
                        "carries the layout transform.\n\n"
                        "When enabled (and worldspace export is used), the "
                        "cache points are already in worldspace and ancestor "
                        "transforms will be ignored during composition."
                    ))
        )

        # Strip namespaces
        defs.append(
            BoolDef("stripNamespaces",
                    label="Strip Namespaces",
                    default=True,
                    tooltip="Remove namespaces during export")
        )

        return defs

    def create(self, product_name, instance_data, pre_create_data):
        """Create the instance with selected members."""

        # Use currently selected nodes as members
        members = cmds.ls(selection=True, long=True, type="dagNode")

        if not members:
            self.log.warning(
                "No nodes selected for animation cache export. "
                "Please select the animated geometry."
            )

        # Call parent create to register the instance
        super().create(product_name, instance_data, pre_create_data)
