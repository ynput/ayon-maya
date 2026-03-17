"""Extract Animation Cache USD.

Exports animated geometry as USD with sparse or per-frame animation data,
and generates a contribution layer that overrides the original asset's
geometry in the shot composition.

Outputs two representations:
1. animationCacheUsd: The animation cache USD file (standalone)
2. animationContribution: Override layer for shot USD composition
"""

import os

from ayon_core.pipeline import PublishValidationError
from ayon_maya.api import plugin
from ayon_maya.api.lib import maintained_selection
from maya import cmds
from pxr import Sdf


def parse_version(version_str):
    """Parse string like '0.21.0' to (0, 21, 0)"""
    return tuple(int(v) for v in version_str.split("."))


class ExtractAnimationCacheUsd(plugin.MayaExtractorPlugin):
    """Extract animation cache as USD with contribution layer."""

    label = "Extract Animation Cache USD"
    families = ["animationCacheUsd"]
    hosts = ["maya"]
    scene_type = "usd"

    def process(self, instance):
        """Process the animation cache USD extraction.

        Steps:
        1. Export animated members as USD with animation data
        2. Create contribution layer that overrides original asset /geo
        3. Generate both representations
        """

        staging_dir = self.staging_dir(instance)

        # 1. Export animation cache USD
        self.log.info("Exporting animation cache USD...")
        cache_file = self._export_animation_cache(instance, staging_dir)
        cache_filename = os.path.basename(cache_file)

        # 2. Create contribution layer (for reference/manual use)
        self.log.info("Creating USD contribution layer...")
        contribution_file = self._create_contribution_layer(
            instance, staging_dir, cache_filename
        )
        contribution_filename = os.path.basename(contribution_file)

        # 3. Add representations
        if "representations" not in instance.data:
            instance.data["representations"] = []

        # Main representation: Animation cache USD (binary format)
        instance.data["representations"].append({
            "name": "usd",
            "ext": "usd",  # Binary USD (usdc format, exported as .usd)
            "files": cache_filename,
            "stagingDir": staging_dir
        })

        # Also add contribution layer as optional representation
        instance.data["representations"].append({
            "name": "contribution",
            "ext": "usda",  # ASCII override layer
            "files": contribution_filename,
            "stagingDir": staging_dir
        })

        self.log.info(
            f"Extracted animation cache: {cache_filename}\n"
            f"Contribution layer: {contribution_filename}\n"
            f"(Contribution layer can be manually added to shot USD)"
        )

    def _export_animation_cache(self, instance, staging_dir) -> str:
        """Export animated members as USD animation cache.

        This exports ONLY the animated transforms (not geometry) so the
        result can be used as an override layer that doesn't duplicate
        the asset hierarchy or break references.

        Args:
            instance: Publish instance
            staging_dir: Staging directory for output

        Returns:
            str: Path to exported USD file
        """

        # Load Maya USD plugin
        cmds.loadPlugin("mayaUsdPlugin", quiet=True)

        # Prepare output file (use .usd not .usda for publishing)
        filename = f"{instance.name}_cache.usd"
        filepath = os.path.join(staging_dir, filename).replace("\\", "/")

        # Get animation settings from creator attributes
        creator_attrs = instance.data.get("creator_attributes", {})
        sampling_mode = instance.data.get("samplingMode", "sparse")
        custom_step = instance.data.get("customStepSize", 1.0)

        # Determine frame step based on sampling mode
        frame_step = 1.0
        if sampling_mode == "custom":
            frame_step = custom_step

        # Get members to export
        members = instance.data.get("setMembers", [])
        if not members:
            raise PublishValidationError(
                f"No members to export for {instance.name}"
            )

        # Get only transform nodes (filters out shapes/geometry)
        # This ensures we export only animation data, not duplicate geometry
        transforms = cmds.ls(members, type="transform", long=True)
        if not transforms:
            self.log.warning(
                f"No transform nodes found in {instance.name}, "
                "will export all members"
            )
            transforms = members

        self.log.debug(f"Members to export: {members}")
        self.log.debug(f"Transforms selected: {transforms}")
        self.log.info(f"Exporting {len(transforms)} transform(s) with animation")

        # Prepare export options
        options = {
            "file": filepath,
            "frameRange": (
                instance.data.get("frameStart", 1),
                instance.data.get("frameEnd", 1)
            ),
            "frameStride": frame_step,
            "stripNamespaces": creator_attrs.get("stripNamespaces", True),
            # NOTE: Don't use exportRoots - it requires a parent-child hierarchy
            # Instead, rely on the selection and filterTypes
            "mergeTransformAndShape": False,  # Keep transforms separate (don't merge with shapes)
            "exportDisplayColor": False,
            "exportVisibility": False,  # Don't export visibility
            "exportComponentTags": False,
            "staticSingleSample": False,  # CRITICAL: Keep animation keyframes!
            "defaultUSDFormat": "usdc",  # Compressed binary USD
            "renderableOnly": False,
            "exportInstances": False,
            "exportColorSets": False,
            "exportUVs": False,
            "exportRefsAsInstanceable": False,
            "eulerFilter": True,
        }

        # Note: filterTypes may cause issues, removed to test basic export
        # The "transforms" list (filtered to type="transform") should prevent
        # shape/mesh/etc nodes from being exported since they won't be selected

        # worldspace parameter requires Maya USD 0.21.0+
        try:
            maya_usd_version = parse_version(
                cmds.pluginInfo("mayaUsdPlugin", query=True, version=True)
            )
            if maya_usd_version >= (0, 21, 0):
                options["worldspace"] = True
        except Exception:
            # If we can't determine version, skip worldspace parameter
            pass

        self.log.debug(f"Export options: {options}")

        # Export USD with animation
        with maintained_selection():
            cmds.select(transforms, replace=True, noExpand=True)
            try:
                cmds.mayaUSDExport(**options)
            except RuntimeError as e:
                raise PublishValidationError(
                    f"Failed to export USD animation cache: {e}"
                )

        if not os.path.exists(filepath):
            raise PublishValidationError(
                f"USD export failed, file not created: {filepath}"
            )

        self.log.debug(f"Exported animation cache: {filepath}")
        return filepath

    def _create_contribution_layer(
        self,
        instance,
        staging_dir,
        cache_filename: str
    ) -> str:
        """Create USD contribution layer as pure override.

        This creates a .usda layer file that can be manually composed into
        the shot USD as an additional layer. It contains ONLY "over" opinions
        that reference the animation cache, so it doesn't duplicate any
        hierarchy or break existing references.

        The layer is meant to be added to the shot composition like:
        ```
        subLayers = [
            @usdMain.usd@,
            @usdShot_layout.usda@,
            @animation_cache_override.usda@  # <- This file
        ]
        ```

        Args:
            instance: Publish instance
            staging_dir: Staging directory
            cache_filename: Name of exported animation cache USD file

        Returns:
            str: Path to contribution layer file
        """

        asset_prim_path = instance.data.get("originalAssetPrimPath", "")
        if not asset_prim_path:
            self.log.warning(
                f"No asset prim path for {instance.name}, "
                "contribution layer will use default fallback"
            )
            asset_prim_path = "/layout/character"

        # Get asset name for contribution layer naming
        asset_name = instance.name
        department = instance.data.get("departmentLayer", "animation")

        # Prepare contribution layer filename (.usda for override layers)
        filename = f"{department}_{asset_name}_animation.usda"
        filepath = os.path.join(staging_dir, filename).replace("\\", "/")

        # Create Sdf layer
        layer = Sdf.Layer.CreateNew(filepath)

        # Build the prim hierarchy as "over" opinions
        # This creates a structure like:
        #   over "/layout/character" { ... }
        prim_parts = [p for p in asset_prim_path.strip("/").split("/") if p]

        if not prim_parts:
            self.log.warning(f"Invalid asset prim path: {asset_prim_path}")
            return filepath

        # Create hierarchy of over prims
        current_prim = None

        for part in prim_parts:
            prim_spec = Sdf.PrimSpec(
                current_prim or layer,
                part,
                Sdf.SpecifierOver
            )
            current_prim = prim_spec

        # Add a comment explaining the layer
        if current_prim:
            current_prim.comment = (
                f"Animation override layer for {asset_name}\n"
                f"Imports animation cache: {cache_filename}\n"
                f"This layer should be added after usdShot_layout in "
                f"the shot composition.\n"
                f"It does NOT duplicate the asset hierarchy, only "
                f"references the animation data."
            )

        # Now add reference to animation cache at the asset root prim
        # This ensures the animation data is loaded alongside the asset
        cache_ref = Sdf.Reference(cache_filename)
        current_prim.referenceList.Append(cache_ref)

        # Save layer
        layer.Save()

        self.log.debug(f"Created contribution layer: {filepath}")
        self.log.debug(f"  Asset prim path: {asset_prim_path}")
        self.log.debug(f"  Cache reference: {cache_filename}")
        self.log.info(
            f"Contribution layer '{filename}' can be manually added to "
            f"the shot USD composition as an additional layer."
        )

        return filepath
