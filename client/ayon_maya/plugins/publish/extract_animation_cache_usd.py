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
from pxr import Sdf, Usd


def parse_version(version_str):
    """Parse string like '0.21.0' to (0, 21, 0)"""
    return tuple(int(v) for v in version_str.split("."))


def _flatten_usd_hierarchy(filepath):
    """Clean up USD file after export, keeping only animated content.

    Maya USD exports often create unnecessary structure:
    - Multiple root prims (usdShot, __mayaUsd__, etc)
    - Deep hierarchies (rigParent > rig > cone_character)
    - Geometry that should have been filtered

    This function:
    1. Finds the deepest animated prim
    2. Promotes it to root level
    3. Removes all other root prims
    4. Result: clean file with just the animation

    Args:
        filepath: Path to USD file (.usd or .usda)

    Returns:
        bool: True if modified, False if no changes needed
    """

    try:
        layer = Sdf.Layer.FindOrOpen(filepath)
        if not layer:
            return False

        root_prims = list(layer.rootPrims)
        if not root_prims:
            return False

        # If we have multiple root prims, find the one with animation
        # Usually it's __mayaUsd__ or similar - we want to extract from it
        target_root = None

        # Look for a prim that's NOT usdShot (which is the shot structure)
        for root in root_prims:
            if root.name not in ["usdShot", "Shot"]:
                target_root = root
                break

        # If didn't find alternative, use first one
        if not target_root:
            target_root = root_prims[0]

        # Now find the deepest prim in this root's hierarchy
        def find_deepest_prim(prim_spec, max_depth=10):
            """Walk down hierarchy to find deepest single-child chain."""
            current = prim_spec
            depth = 0

            while depth < max_depth:
                children = [c for c in current.nameChildren]
                if len(children) != 1:
                    # Multiple or no children - stop here
                    return current, depth

                current = children[0]
                depth += 1

            return current, depth

        deepest_prim, depth = find_deepest_prim(target_root)

        # If we found a deep hierarchy or have multiple roots, flatten it
        if depth > 0 or len(root_prims) > 1:
            # Get the deepest prim's name
            final_name = deepest_prim.name

            # Create new root prim with the deepest prim's content
            # Copy the spec to root level
            new_root = Sdf.PrimSpec(layer, final_name, deepest_prim.specifier)

            # Copy all attributes
            for attr_name, attr in deepest_prim.attributes.items():
                new_root.attributes[attr_name] = attr

            # Copy all children
            for child in deepest_prim.nameChildren:
                new_root.nameChildren.append(child)

            # Replace all root prims with just this one
            layer.rootPrims[:] = [new_root]

            # Save
            layer.Save()
            return True

    except Exception as e:
        # If anything fails, leave the file as-is
        return False

    return False


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

        # CRITICAL: Only export leaf transforms (not parent groups)
        # This prevents exporting the full hierarchy (rigParent/rig/asset)
        # and focuses only on the actual animated asset transform(s)
        leaf_transforms = []
        for xf in transforms:
            # Check if this transform has any children that are also in the export list
            children = cmds.listRelatives(xf, children=True, allDescendents=False) or []
            has_exported_children = any(child in transforms for child in children)

            if not has_exported_children:
                # This is a leaf (no children in the export list)
                leaf_transforms.append(xf)

        # Use leaf transforms only
        transforms_to_export = leaf_transforms if leaf_transforms else transforms

        self.log.debug(f"Original members: {members}")
        self.log.debug(f"All transforms: {transforms}")
        self.log.debug(f"Leaf transforms (for export): {transforms_to_export}")
        self.log.info(
            f"Exporting {len(transforms_to_export)} animated transform(s)\n"
            f"(filtered to leaf nodes only, avoiding parent hierarchies)"
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
            cmds.select(transforms_to_export, replace=True, noExpand=True)
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

        # Post-process: flatten unnecessary hierarchy
        # Maya USD creates rigParent > rig > cone_character structure
        # We want just cone_character at the root
        self.log.info("Flattening USD hierarchy (removing parent prims)...")
        try:
            was_flattened = _flatten_usd_hierarchy(filepath)
            if was_flattened:
                self.log.info("✓ USD hierarchy flattened successfully")
            else:
                self.log.debug("No hierarchy flattening needed")
        except Exception as e:
            self.log.warning(f"Could not flatten hierarchy: {e}")
            # Continue anyway - the file is still valid

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

        # Determine the asset prim path where the animation should override
        asset_prim_path = instance.data.get("originalAssetPrimPath", "")

        if not asset_prim_path:
            # Try to deduce from instance name or use common paths
            asset_name = instance.name

            # Common patterns: /assets/character, /layout/character, etc
            possible_paths = [
                f"/assets/{asset_name}",
                f"/layout/{asset_name}",
                f"/assets/character/{asset_name}",
            ]

            self.log.warning(
                f"No originalAssetPrimPath for {instance.name}\n"
                f"Will try these paths: {possible_paths}\n"
                f"Consider setting originalAssetPrimPath in the creator to be explicit"
            )
            # Use the first one for now (user can override with originalAssetPrimPath)
            asset_prim_path = f"/assets/{asset_name}"

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
