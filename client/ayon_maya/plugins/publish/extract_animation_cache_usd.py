"""Extract Animation Cache USD - Point Cache Export.

Exports animated geometry as a USD point cache file.
The geometry is deformed by the rig/animation, and we export the final
deformed mesh with animated point positions (no rig structure).

Outputs:
1. Point Cache USD file: Contains only the deformed geometry with animated points
   - Shape/mesh with time-sampled point positions
   - No rig structure, no control curves
   - Ready to be composed as an override in the shot

The workflow:
1. Select the deformed geometry (typically from inside the rigged asset)
2. Export with proper options (no skeleton, no skin, no rig)
3. Result: Clean point cache with mesh animation

Usage:
- Select: /assets/character/cone_character/geo/cone_character_GEO (or similar)
- Publish with animationCacheUsd family
- Get: point_cache.usd with animated mesh points
"""

import os

from ayon_core.pipeline import PublishValidationError
from ayon_maya.api import plugin
from ayon_maya.api.lib import maintained_selection
from maya import cmds
from pxr import Sdf, Usd


def parse_version(version_str):
    """Parse string like '0.21.0' to (0, 21, 0)"""
    return tuple(int(v) for v in version_str.split("."))


class ExtractAnimationCacheUsd(plugin.MayaExtractorPlugin):
    """Extract animation cache as USD point cache."""

    label = "Extract Animation Cache USD"
    families = ["animationCacheUsd"]
    hosts = ["maya"]
    scene_type = "usd"

    def process(self, instance):
        """Process the animation cache USD extraction.

        Steps:
        1. Export selected geometry with animation (as point cache)
        2. Clean up any unwanted structure
        3. Generate representation
        """

        staging_dir = self.staging_dir(instance)

        # 1. Export animation cache USD (point cache)
        self.log.info("Exporting animation cache USD (point cache)...")
        cache_file = self._export_animation_cache(instance, staging_dir)
        cache_filename = os.path.basename(cache_file)

        # 2. Add representation
        if "representations" not in instance.data:
            instance.data["representations"] = []

        # Main representation: Animation cache USD
        instance.data["representations"].append({
            "name": "usd",
            "ext": "usd",
            "files": cache_filename,
            "stagingDir": staging_dir
        })

        self.log.info(f"✓ Extracted point cache: {cache_filename}")

    def _export_animation_cache(self, instance, staging_dir) -> str:
        """Export animated geometry as USD point cache.

        This exports the deformed geometry (shape/mesh) with animated point
        positions. No rig structure, no control curves - just the final
        animated geometry.

        Args:
            instance: Publish instance
            staging_dir: Staging directory for output

        Returns:
            str: Path to exported USD file
        """

        # Load Maya USD plugin
        cmds.loadPlugin("mayaUsdPlugin", quiet=True)

        # Prepare output file
        filename = f"{instance.name}_cache.usd"
        filepath = os.path.join(staging_dir, filename).replace("\\", "/")

        # Get animation settings
        creator_attrs = instance.data.get("creator_attributes", {})
        sampling_mode = instance.data.get("samplingMode", "sparse")
        custom_step = instance.data.get("customStepSize", 1.0)

        # Determine frame step
        frame_step = 1.0
        if sampling_mode == "custom":
            frame_step = custom_step

        # Get members to export (should be shape/mesh nodes)
        members = instance.data.get("setMembers", [])
        if not members:
            raise PublishValidationError(
                f"No members to export for {instance.name}"
            )

        self.log.info(f"Exporting point cache for: {members}")
        self.log.debug(f"Frame range: {instance.data.get('frameStart', 1)}-{instance.data.get('frameEnd', 1)}")
        self.log.debug(f"Sampling: {sampling_mode} (step: {frame_step})")

        # Prepare export options for POINT CACHE
        # Key: exportSkels and exportSkin should be "none" to skip rig structure
        options = {
            "file": filepath,
            "frameRange": (
                instance.data.get("frameStart", 1),
                instance.data.get("frameEnd", 1)
            ),
            "frameStride": frame_step,
            # CRITICAL: Skip rig/skeleton export - we only want geometry
            "exportSkels": "none",  # Don't export skeleton
            "exportSkin": "none",  # Don't export skin clusters
            "exportBlendShapes": True,  # Export blend shapes if present
            # Other settings
            "stripNamespaces": creator_attrs.get("stripNamespaces", True),
            "mergeTransformAndShape": False,  # Keep transform and shape separate
            "exportDisplayColor": False,
            "exportVisibility": False,
            "exportColorSets": False,
            "exportUVs": True,  # Keep UVs for texture mapping
            "exportInstances": False,
            "defaultUSDFormat": "usdc",  # Compressed binary
            "staticSingleSample": False,  # Keep animation keyframes
            "eulerFilter": True,
        }

        # Try to use worldspace if available (Maya USD 0.21.0+)
        try:
            maya_usd_version = parse_version(
                cmds.pluginInfo("mayaUsdPlugin", query=True, version=True)
            )
            if maya_usd_version >= (0, 21, 0):
                options["worldspace"] = True
            else:
                self.log.debug(f"Maya USD {maya_usd_version} < 0.21.0, no worldspace")
        except Exception as e:
            self.log.debug(f"Could not determine Maya USD version: {e}")

        self.log.debug(f"Export options: {options}")

        # Export USD with animation
        with maintained_selection():
            cmds.select(members, replace=True, noExpand=True)
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

        self.log.debug(f"Exported point cache USD: {filepath}")
        return filepath
