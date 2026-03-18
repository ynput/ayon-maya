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
3. Post-process to remap hierarchy to match original asset prim path
4. Result: Clean point cache with correct hierarchy for sublayer composition

Usage:
- Select: /assets/character/cone_character/geo/cone_character_GEO (or similar)
- Publish with animationCacheUsd family
- Get: point_cache.usd with animated mesh at the correct prim path
"""

import os

from ayon_core.pipeline import PublishValidationError
from ayon_maya.api import plugin
from ayon_maya.api.lib import maintained_selection
from maya import cmds
from pxr import Sdf, Usd, UsdGeom


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
        2. Remap hierarchy to match original asset prim path
        3. Add !resetXformStack! to prevent double-transforms
        4. Generate representation
        """

        staging_dir = self.staging_dir(instance)

        # 1. Export animation cache USD (point cache)
        self.log.info("Exporting animation cache USD (point cache)...")
        cache_file = self._export_animation_cache(instance, staging_dir)

        # 2. Remap hierarchy to match original asset prim path
        self._remap_to_asset_hierarchy(cache_file, instance)

        # 3. Add !resetXformStack! to prevent double-transforms
        #    When the cache is exported with worldspace=True, the point
        #    positions already include the layout transform. Adding
        #    resetXformStack ensures ancestor transforms (from layout
        #    positioning) are ignored during composition.
        creator_attrs = instance.data.get("creator_attributes", {})
        if creator_attrs.get("resetXformStack", True):
            self._add_reset_xform_stack(cache_file, instance)

        cache_filename = os.path.basename(cache_file)

        # 4. Add representation
        if "representations" not in instance.data:
            instance.data["representations"] = []

        instance.data["representations"].append({
            "name": "usd",
            "ext": "usd",
            "files": cache_filename,
            "stagingDir": staging_dir
        })

        self.log.info(f"Extracted point cache: {cache_filename}")

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
        self.log.debug(
            f"Frame range: {instance.data.get('frameStart', 1)}"
            f"-{instance.data.get('frameEnd', 1)}"
        )
        self.log.debug(f"Sampling: {sampling_mode} (step: {frame_step})")

        # Prepare export options for POINT CACHE
        options = {
            "file": filepath,
            "selection": True,
            "frameRange": (
                instance.data.get("frameStart", 1),
                instance.data.get("frameEnd", 1)
            ),
            "frameStride": frame_step,
            "exportSkels": "none",
            "exportSkin": "none",
            "exportBlendShapes": True,
            "stripNamespaces": creator_attrs.get("stripNamespaces", True),
            "mergeTransformAndShape": False,
            "exportDisplayColor": False,
            "exportVisibility": False,
            "exportColorSets": False,
            "exportUVs": True,
            "exportInstances": False,
            "defaultUSDFormat": "usdc",
            "staticSingleSample": False,
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
                self.log.debug(
                    f"Maya USD {maya_usd_version} < 0.21.0, no worldspace"
                )
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

    # ------------------------------------------------------------------
    # resetXformStack — prevent double-transforms from layout
    # ------------------------------------------------------------------

    def _add_reset_xform_stack(self, filepath, instance):
        """Add !resetXformStack! to geometry prims in the cache.

        When the cache is exported with ``worldspace=True``, the point
        positions already include the layout transform baked in.  If the
        cache is then composed as a sublayer in a shot stage where an
        ancestor Xform still carries the layout transform, the geometry
        would be double-transformed.

        ``!resetXformStack!`` is a USD directive in ``xformOpOrder`` that
        tells the renderer to ignore all ancestor transforms above this
        prim, effectively anchoring it in worldspace.

        This method opens the exported cache and sets
        ``resetXformStack`` on:
        - The asset root prim (if it is Xformable)
        - All direct geometry children (Mesh, etc.)
        """
        original_path = instance.data.get("originalAssetPrimPath", "")

        stage = Usd.Stage.Open(filepath)
        if not stage:
            self.log.warning(
                f"Could not open USD stage for resetXformStack: {filepath}"
            )
            return

        modified = False

        # Determine which prim to apply resetXformStack to
        if original_path:
            target_prim = stage.GetPrimAtPath(original_path)
        else:
            # Fallback: use the defaultPrim or first root prim
            target_prim = stage.GetDefaultPrim()
            if not target_prim or not target_prim.IsValid():
                root_prims = [
                    p for p in stage.GetPseudoRoot().GetChildren()
                ]
                target_prim = root_prims[0] if root_prims else None

        if not target_prim or not target_prim.IsValid():
            self.log.warning(
                "No valid prim found for resetXformStack application"
            )
            return

        # Apply to the asset root prim itself
        xformable = UsdGeom.Xformable(target_prim)
        if xformable:
            xformable.SetResetXformStack(True)
            modified = True
            self.log.debug(
                f"Added resetXformStack to: {target_prim.GetPath()}"
            )

        # Also apply to geometry children that are Xformable
        for child in target_prim.GetAllChildren():
            child_xformable = UsdGeom.Xformable(child)
            if child_xformable and child.GetTypeName() in (
                "Mesh", "Xform", "Scope"
            ):
                child_xformable.SetResetXformStack(True)
                modified = True
                self.log.debug(
                    f"Added resetXformStack to child: {child.GetPath()}"
                )

        if modified:
            stage.GetRootLayer().Save()
            self.log.info(
                "Applied !resetXformStack! to prevent double-transforms"
            )

    # ------------------------------------------------------------------
    # Hierarchy remapping
    # ------------------------------------------------------------------

    def _remap_to_asset_hierarchy(self, filepath, instance):
        """Remap exported USD hierarchy to match original asset prim path.

        When exporting geometry from 'Edit as Maya Data', the Maya USD
        exporter preserves the internal Maya scene hierarchy, producing
        paths like::

            /__mayaUsd__/rigParent/rig/<asset>/geo/mesh

        For the LayCache sublayer to compose correctly over the original
        asset in the shot stage, the hierarchy must match the original
        prim path, e.g.::

            /usdShot/assets/character/<asset>/geo/mesh

        This method:
        1. Finds the asset prim in the exported hierarchy by name
        2. Creates a new layer with the correct target hierarchy
        3. Copies the geometry subtree to the correct location
        4. Cleans up non-geometry prims (rig controls, materials)
        """
        original_path = instance.data.get("originalAssetPrimPath", "")
        if not original_path:
            self.log.warning(
                "No originalAssetPrimPath available. "
                "Cannot remap LayCache hierarchy. The exported USD will "
                "keep the Maya scene hierarchy which may not compose "
                "correctly as a sublayer."
            )
            return

        target_path = Sdf.Path(original_path)
        asset_name = target_path.name

        layer = Sdf.Layer.FindOrOpen(filepath)
        if not layer:
            self.log.error(f"Could not open exported USD: {filepath}")
            return

        # Find the asset prim in the exported hierarchy
        source_path = self._find_prim_by_name(layer, asset_name)

        # Fallback: try namespace-suffixed match (when stripNamespaces=False)
        if not source_path:
            source_path = self._find_prim_by_name_suffix(layer, asset_name)

        if not source_path:
            self.log.warning(
                f"Could not find prim '{asset_name}' in exported USD. "
                "Hierarchy remapping skipped."
            )
            return

        if source_path == target_path:
            self.log.debug("Hierarchy already correct, no remapping needed")
            return

        self.log.info(f"Remapping hierarchy: {source_path} -> {target_path}")

        # Build new layer with correct hierarchy
        new_layer = Sdf.Layer.CreateAnonymous()
        self._copy_layer_metadata(layer, new_layer)

        # Create parent Xform prims for the target path
        prefixes = target_path.GetPrefixes()
        for prefix in prefixes[:-1]:
            if not new_layer.GetPrimAtPath(prefix):
                prim_spec = Sdf.CreatePrimInLayer(new_layer, prefix)
                prim_spec.specifier = Sdf.SpecifierDef
                prim_spec.typeName = "Xform"

        # Copy the asset subtree from source to target
        if not Sdf.CopySpec(layer, source_path, new_layer, target_path):
            self.log.error(
                f"Failed to copy prim specs: {source_path} -> {target_path}"
            )
            return

        # Set defaultPrim to the topmost prim
        new_layer.defaultPrim = prefixes[0].name

        # Clean up non-geometry prims (rig controls, materials, etc.)
        self._cleanup_non_geometry(new_layer, target_path)

        # Save the remapped layer
        new_layer.Export(filepath)
        self.log.info(
            f"Hierarchy remapped successfully: {source_path} -> {target_path}"
        )

    def _copy_layer_metadata(self, source_layer, target_layer):
        """Copy layer-level metadata (timeCode, upAxis, etc.)."""
        source_root = source_layer.pseudoRoot
        target_root = target_layer.pseudoRoot

        skip_keys = {
            "primChildren", "defaultPrim",
            "subLayers", "subLayerOffsets",
        }
        for key in source_root.ListInfoKeys():
            if key not in skip_keys:
                try:
                    target_root.SetInfo(key, source_root.GetInfo(key))
                except Exception:
                    pass

    def _find_prim_by_name(self, layer, name):
        """Find first prim with exact name match via depth-first search."""

        def _search(parent_path):
            spec = layer.GetPrimAtPath(parent_path)
            if not spec:
                return None
            for child_spec in spec.nameChildren:
                child_path = parent_path.AppendChild(child_spec.name)
                if child_spec.name == name:
                    return child_path
                result = _search(child_path)
                if result:
                    return result
            return None

        for root_spec in layer.rootPrims:
            root_path = Sdf.Path.absoluteRootPath.AppendChild(root_spec.name)
            if root_spec.name == name:
                return root_path
            result = _search(root_path)
            if result:
                return result
        return None

    def _find_prim_by_name_suffix(self, layer, name):
        """Find prim whose name ends with ':name' (namespace handling).

        When stripNamespaces is False, prim names may include namespaces
        like 'myNs:cone_character'. This matches those cases.
        """
        suffix = f":{name}"

        def _search(parent_path):
            spec = layer.GetPrimAtPath(parent_path)
            if not spec:
                return None
            for child_spec in spec.nameChildren:
                child_path = parent_path.AppendChild(child_spec.name)
                if child_spec.name.endswith(suffix):
                    return child_path
                result = _search(child_path)
                if result:
                    return result
            return None

        for root_spec in layer.rootPrims:
            root_path = Sdf.Path.absoluteRootPath.AppendChild(root_spec.name)
            if root_spec.name.endswith(suffix):
                return root_path
            result = _search(root_path)
            if result:
                return result
        return None

    # ------------------------------------------------------------------
    # Non-geometry cleanup
    # ------------------------------------------------------------------

    def _cleanup_non_geometry(self, layer, root_path):
        """Remove non-geometry prims from the pointcache.

        For a pointcache sublayer we only need Mesh geometry and its
        parent hierarchy (Xform, Scope). This removes:
        - BasisCurves (rig control shapes)
        - Material / Shader / NodeGraph prims
        - MayaReference prims
        - Empty Xform/Scope containers with no geometry descendants
        """
        non_geo_types = {
            "BasisCurves", "Material", "Shader",
            "NodeGraph", "MayaReference",
        }

        # Pass 1: collect non-geometry typed prims
        prims_to_remove = []

        def _collect_non_geo(path):
            spec = layer.GetPrimAtPath(path)
            if not spec:
                return
            if spec.typeName in non_geo_types:
                prims_to_remove.append(path)
                return  # skip children - they'll be removed with parent
            for child_spec in list(spec.nameChildren):
                _collect_non_geo(path.AppendChild(child_spec.name))

        _collect_non_geo(root_path)

        if prims_to_remove:
            edit = Sdf.BatchNamespaceEdit()
            for path in reversed(prims_to_remove):
                edit.Add(path, Sdf.Path.emptyPath)
            layer.Apply(edit)
            self.log.debug(
                f"Removed {len(prims_to_remove)} non-geometry prims"
            )

        # Pass 2: remove empty Xform/Scope containers
        self._remove_empty_containers(layer, root_path)

    def _remove_empty_containers(self, layer, root_path):
        """Remove Xform/Scope prims that have no geometry descendants."""
        geo_types = {
            "Mesh", "GeomSubset", "Points",
            "NurbsPatch", "PointInstancer",
        }

        def _has_geometry(path):
            spec = layer.GetPrimAtPath(path)
            if not spec:
                return False
            if spec.typeName in geo_types:
                return True
            for child_spec in spec.nameChildren:
                if _has_geometry(path.AppendChild(child_spec.name)):
                    return True
            return False

        def _collect_empty(path):
            spec = layer.GetPrimAtPath(path)
            if not spec:
                return []
            empties = []
            for child_spec in list(spec.nameChildren):
                child_path = path.AppendChild(child_spec.name)
                child_obj = layer.GetPrimAtPath(child_path)
                if (child_obj
                        and child_obj.typeName in ("Xform", "Scope")
                        and not _has_geometry(child_path)):
                    empties.append(child_path)
                else:
                    empties.extend(_collect_empty(child_path))
            return empties

        empties = _collect_empty(root_path)
        if empties:
            edit = Sdf.BatchNamespaceEdit()
            for path in reversed(empties):
                edit.Add(path, Sdf.Path.emptyPath)
            layer.Apply(edit)
            self.log.debug(
                f"Removed {len(empties)} empty containers"
            )
