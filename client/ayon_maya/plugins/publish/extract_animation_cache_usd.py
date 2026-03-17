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

        # 3. Add representation
        if "representations" not in instance.data:
            instance.data["representations"] = []

        # Main representation: Animation cache USD
        instance.data["representations"].append({
            "name": "usd",
            "ext": "usda",
            "files": cache_filename,
            "stagingDir": staging_dir
        })

        self.log.info(
            f"Extracted animation cache: {cache_filename}\n"
            f"Contribution layer: {contribution_filename}\n"
            f"(Contribution layer can be manually added to shot USD)"
        )

    def _export_animation_cache(self, instance, staging_dir) -> str:
        """Export animated members as USD animation cache.

        Args:
            instance: Publish instance
            staging_dir: Staging directory for output

        Returns:
            str: Path to exported USD file
        """

        # Load Maya USD plugin
        cmds.loadPlugin("mayaUsdPlugin", quiet=True)

        # Prepare output file
        filename = f"{instance.name}_cache.usda"
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

        # Prepare export options
        options = {
            "file": filepath,
            "frameRange": (
                instance.data.get("frameStart", 1),
                instance.data.get("frameEnd", 1)
            ),
            "frameStride": frame_step,
            "stripNamespaces": creator_attrs.get("stripNamespaces", True),
            "mergeTransformAndShape": True,
            "exportDisplayColor": False,
            "exportVisibility": True,
            "staticSingleSample": False,
            "defaultUSDFormat": creator_attrs.get("defaultUSDFormat", "usda"),
        }

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

        # Export USD with animation
        with maintained_selection():
            cmds.select(members, noExpand=True)
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
        """Create USD contribution layer that overrides asset /geo.

        This layer uses over opinions to replace the original asset's
        geometry with the animation cache, allowing the shot USD to
        reference both the asset and this override layer.

        Args:
            instance: Publish instance
            staging_dir: Staging directory
            cache_filename: Name of exported cache file

        Returns:
            str: Path to contribution layer file
        """

        asset_prim_path = instance.data.get("originalAssetPrimPath", "")
        if not asset_prim_path:
            self.log.warning(
                f"No asset prim path for {instance.name}, "
                "contribution layer may not be placed correctly"
            )
            asset_prim_path = "/layout/character"  # Default fallback

        # Get asset name for contribution layer naming
        asset_name = instance.name
        department = instance.data.get("departmentLayer", "animation")

        # Prepare contribution layer filename
        filename = f"{department}_{asset_name}_animation.usda"
        filepath = os.path.join(staging_dir, filename).replace("\\", "/")

        # Create Sdf layer
        layer = Sdf.Layer.CreateNew(filepath)

        # Build the full hierarchy as "over" opinions
        # Split the prim path into components: /assets/character/cone -> ['assets', 'character', 'cone']
        prim_parts = [p for p in asset_prim_path.strip("/").split("/") if p]

        if not prim_parts:
            self.log.warning(f"Invalid asset prim path: {asset_prim_path}")
            return filepath

        # Create hierarchy of over prims
        current_path = ""
        current_prim = None

        for part in prim_parts:
            current_path += "/" + part
            prim_spec = Sdf.PrimSpec(
                current_prim or layer,
                part,
                Sdf.SpecifierOver
            )
            current_prim = prim_spec

        # Now add /geo as a child with the animation cache reference
        geo_prim = Sdf.PrimSpec(
            current_prim,
            "geo",
            Sdf.SpecifierOver
        )

        # Add reference to animation cache
        cache_ref = Sdf.Reference(cache_filename)
        geo_prim.referenceList.Append(cache_ref)

        # Add comment to root prim
        if current_prim:
            current_prim.comment = (
                f"Animation contribution layer for {asset_name}\n"
                f"Overrides {asset_prim_path}/geo with animation cache"
            )

        # Save layer
        layer.Save()

        self.log.debug(f"Created contribution layer: {filepath}")
        self.log.debug(f"  Asset prim path: {asset_prim_path}")
        self.log.debug(f"  Cache reference: {cache_filename}")

        return filepath
