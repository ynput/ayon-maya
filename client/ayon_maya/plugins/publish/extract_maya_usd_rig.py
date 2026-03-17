"""Extract rig as Maya Scene + USD Maya Reference Prim.

Workflow based on Prism Pipeline's USD rigging approach:
1. Export rig geometry/controls as .mb (Maya Binary)
2. Create a MayaReference prim in the USD edit target layer
   pointing to the .mb file
3. Export the edit target layer as .usda

The MayaReference prim type is a Maya USD specific schema that
allows Maya to load a .ma/.mb file as native Maya data when
the user selects "Edit As Maya Data" on the prim. In other DCCs
(e.g. Houdini) the prim is simply ignored.

The .mb rig file is published as its own AYON representation and
also transferred to ``publishDir`` (same pattern as OBJ .mtl files).
The MayaReference prim stores the **absolute published path** so
the .mb resolves correctly both during the session (after integration)
and when the layer is loaded from a different context.
"""
import os

from maya import cmds

from ayon_maya.api import plugin
from ayon_maya.api.lib import maintained_selection
from ayon_core.pipeline import PublishValidationError


class ExtractMayaUsdRig(plugin.MayaExtractorPlugin):
    """Extract rig as Maya Scene and create USD Maya Reference Prim.

    This extractor:
    1. Exports the rig as .mb (Maya Binary)
    2. Ensures a rigging layer exists as edit target
    3. Creates a MayaReference prim with the **absolute published path**
       to the .mb so "Edit as Maya Data" works after integration
    4. Exports the rigging layer as .usda
    5. Transfers the .mb to publishDir so it lives at the referenced path
    """

    label = "Extract Maya USD Rig"
    families = ["mayaUsdRig"]
    scene_type = "mb"

    def process(self, instance):
        staging_dir = self.staging_dir(instance)

        # 1. Export rig as Maya binary
        self.log.info("Exporting rig as Maya binary...")
        mb_file = self._export_rig_mb(instance, staging_dir)
        mb_filename = os.path.basename(mb_file)

        # 2. Compute the absolute published path for the .mb.
        #    This is where the .mb will live after integration (via
        #    transfer).  Using the absolute path ensures "Edit as Maya
        #    Data" resolves correctly regardless of where the rigging
        #    layer is anchored (work dir during session, publish dir
        #    after reload).
        publish_dir = instance.data.get("publishDir", "")
        if publish_dir:
            mb_ref_path = os.path.join(
                publish_dir, mb_filename
            ).replace("\\", "/")
        else:
            # Fallback: just the filename (relative to layer location)
            self.log.warning(
                "publishDir not available, using relative .mb path"
            )
            mb_ref_path = mb_filename

        # 3. Create Maya Reference Prim in USD
        self.log.info("Creating Maya Reference Prim in USD...")
        prim_path = self._create_maya_reference_prim(
            instance, staging_dir, mb_ref_path
        )

        if not prim_path:
            raise PublishValidationError(
                "Failed to create Maya Reference Prim for "
                f"{instance.name}"
            )

        # 4. Export USD layer
        self.log.info("Exporting USD rigging layer...")
        usd_file = self._export_usd_layer(instance, staging_dir)

        # 5. Transfer .mb to publishDir so it lives at the path
        #    referenced by the MayaReference prim (same pattern as
        #    OBJ .mtl files in extract_obj.py).
        if publish_dir:
            mb_destination = os.path.join(
                publish_dir, mb_filename
            ).replace("\\", "/")
            transfers = instance.data.setdefault("transfers", [])
            transfers.append((mb_file, mb_destination))
            self.log.debug(
                f"Transfer .mb to publishDir: {mb_file} -> {mb_destination}"
            )

        # 6. Add representations
        if "representations" not in instance.data:
            instance.data["representations"] = []

        instance.data["representations"].append({
            "name": "mb",
            "ext": "mb",
            "files": mb_filename,
            "stagingDir": staging_dir
        })

        if usd_file:
            usd_filename = os.path.basename(usd_file)
            instance.data["representations"].append({
                "name": "usd",
                "ext": "usda",
                "files": usd_filename,
                "stagingDir": staging_dir
            })

        self.log.info(
            f"Extracted rig '{instance.name}': "
            f"MB={mb_filename}, USD prim={prim_path}, "
            f"MB published at={mb_ref_path}"
        )

    def _export_rig_mb(self, instance, staging_dir):
        """Export rig as Maya binary file.

        Returns:
            str: Path to exported .mb file
        """
        filename = f"{instance.name}.mb"
        filepath = os.path.join(staging_dir, filename).replace("\\", "/")

        members = instance.data.get("setMembers", [])
        if not members:
            self.log.warning(
                f"Instance {instance.name} has no members to export"
            )

        with maintained_selection():
            cmds.select(members, noExpand=True)
            cmds.file(
                filepath,
                force=True,
                type="mayaBinary",
                exportSelected=True,
                preserveReferences=False,
                channels=True,
                constraints=True,
                expressions=True,
                constructionHistory=True
            )

        self.log.debug(f"Exported rig to: {filepath}")
        return filepath

    def _create_maya_reference_prim(self, instance, staging_dir, mb_ref_path):
        """Create a MayaReference prim in the USD edit target layer.

        First tries ``mayaUsdAddMayaReference.createMayaReferencePrim``
        which requires a UFE path to an **existing parent prim**.
        If that fails, falls back to creating the prim directly via
        ``stage.DefinePrim`` with the correct MayaReference schema
        and attributes.

        Args:
            instance: Pyblish instance.
            staging_dir (str): Staging directory path.
            mb_ref_path (str): Value for the ``mayaReference`` attribute.
                Typically the **absolute published path** to the ``.mb``
                file so the reference resolves correctly regardless of
                where the rigging layer is loaded from.

        Returns:
            str: USD prim path of the created MayaReference, or None.
        """
        try:
            cmds.loadPlugin("mayaUsdPlugin", quiet=True)
            import mayaUsd
        except Exception as exc:
            raise PublishValidationError(
                f"Failed to load Maya USD plugins: {exc}"
            ) from exc

        proxy_path = instance.data.get("usdStageProxyPath")
        if not proxy_path:
            raise PublishValidationError(
                f"Instance {instance.name}: No USD proxy shape found"
            )

        stage = mayaUsd.ufe.getStage(proxy_path)
        if not stage:
            raise PublishValidationError(
                f"Unable to get USD stage from {proxy_path}"
            )

        # Ensure the rigging layer is the edit target
        rigging_layer = self._ensure_rigging_layer(stage, instance)
        stage.SetEditTarget(rigging_layer)

        # Find a suitable parent prim to create the MayaReference under.
        # The parent should be the asset root prim (e.g. /cube_character).
        parent_prim = self._find_parent_prim(stage)
        parent_path = str(parent_prim.GetPath()) if parent_prim else ""

        # Build unique rig prim name
        rig_prim_name = "rig"
        rig_prim_path = f"{parent_path}/{rig_prim_name}"

        namespace = instance.name

        # --- Approach 1: Use the Maya USD API ---
        prim = self._try_create_via_api(
            proxy_path, parent_path, mb_ref_path, namespace, rig_prim_name
        )
        if prim and prim.IsValid():
            self.log.info(
                f"Created MayaReference prim via API at "
                f"{prim.GetPath()}"
            )
            return str(prim.GetPath())

        # --- Approach 2: Direct USD prim creation ---
        self.log.info(
            "API approach did not succeed, creating MayaReference "
            "prim directly via USD API..."
        )
        prim = self._create_maya_reference_prim_direct(
            stage, rig_prim_path, mb_ref_path, namespace
        )
        if prim and prim.IsValid():
            self.log.info(
                f"Created MayaReference prim directly at "
                f"{prim.GetPath()}"
            )
            return str(prim.GetPath())

        return None

    def _find_parent_prim(self, stage):
        """Find the best parent prim for the MayaReference.

        Looks for the default prim first, then the first root Xform
        prim, then falls back to the pseudo-root.

        Returns:
            pxr.Usd.Prim: Parent prim to create the reference under
        """
        # Try the default prim
        default_prim = stage.GetDefaultPrim()
        if default_prim and default_prim.IsValid():
            self.log.debug(
                f"Using default prim as parent: {default_prim.GetPath()}"
            )
            return default_prim

        # Try first root-level Xform/Scope prim
        for prim in stage.GetPseudoRoot().GetChildren():
            if prim.IsValid() and prim.GetTypeName() in (
                "Xform", "Scope", ""
            ):
                self.log.debug(
                    f"Using root prim as parent: {prim.GetPath()}"
                )
                return prim

        # Fallback: use pseudo-root (creates prim at root level)
        self.log.debug("No suitable parent found, using stage root")
        return stage.GetPseudoRoot()

    def _try_create_via_api(
        self, proxy_path, parent_path, mb_ref_path, namespace, prim_name
    ):
        """Try creating MayaReference via mayaUsdAddMayaReference API.

        The API expects a UFE path to an *existing parent prim*.
        It creates a child MayaReference prim under that parent.

        Returns:
            pxr.Usd.Prim or None
        """
        try:
            import mayaUsdAddMayaReference

            # UFE path to the PARENT prim (must already exist)
            parent_ufe_path = f"{proxy_path},{parent_path}"

            self.log.debug(
                f"Calling createMayaReferencePrim:\n"
                f"  parent UFE: {parent_ufe_path}\n"
                f"  MB ref path: {mb_ref_path}\n"
                f"  namespace: {namespace}\n"
                f"  prim name: {prim_name}"
            )

            prim = mayaUsdAddMayaReference.createMayaReferencePrim(
                parent_ufe_path,
                mb_ref_path,
                namespace,
                prim_name,  # mayaReferencePrimName
            )

            if prim and (hasattr(prim, 'IsValid') and prim.IsValid()
                         or isinstance(prim, str)):
                return prim

            self.log.warning(
                "createMayaReferencePrim returned invalid prim"
            )
            return None

        except Exception as exc:
            self.log.warning(
                f"createMayaReferencePrim failed: {exc}"
            )
            return None

    def _create_maya_reference_prim_direct(
        self, stage, prim_path, mb_ref_path, namespace
    ):
        """Create a MayaReference prim directly using USD API.

        Creates a prim with type "MayaReference" and sets the three
        required attributes:
        - mayaReference (Asset): path to the .mb file (relative filename)
        - mayaNamespace (String): namespace for the reference
        - mayaAutoEdit (Bool): whether to auto-edit on load

        This mirrors what ``createMayaReferencePrim`` does internally.

        Returns:
            pxr.Usd.Prim or None
        """
        from pxr import Sdf

        try:
            prim = stage.DefinePrim(prim_path, "MayaReference")
            if not prim or not prim.IsValid():
                self.log.error(
                    f"stage.DefinePrim failed for {prim_path}"
                )
                return None

            # Set the three MayaReference attributes
            maya_ref_attr = prim.CreateAttribute(
                "mayaReference", Sdf.ValueTypeNames.Asset
            )
            maya_ref_attr.Set(mb_ref_path)

            maya_ns_attr = prim.CreateAttribute(
                "mayaNamespace", Sdf.ValueTypeNames.String
            )
            maya_ns_attr.Set(namespace)

            maya_auto_edit_attr = prim.CreateAttribute(
                "mayaAutoEdit", Sdf.ValueTypeNames.Bool
            )
            maya_auto_edit_attr.Set(False)

            self.log.debug(
                f"Defined MayaReference prim at {prim_path} -> "
                f"{mb_ref_path}"
            )
            return prim

        except Exception as exc:
            self.log.error(
                f"Failed to create MayaReference prim at "
                f"{prim_path}: {exc}"
            )
            return None

    def _ensure_rigging_layer(self, stage, instance):
        """Ensure a rigging layer exists in the stage.

        If the current edit target already contains 'rigging' or 'rig'
        in its name, use that. Otherwise look through the layer stack.
        If none found, create a new sublayer.

        Returns:
            pxr.Sdf.Layer: The rigging layer
        """
        from pxr import Sdf

        # Check current edit target first
        current_target = stage.GetEditTarget().GetLayer()
        display_name = current_target.GetDisplayName()
        if display_name and (
            "rigging" in display_name.lower()
            or "rig" in display_name.lower()
        ):
            self.log.debug(
                f"Current edit target is already rigging layer: "
                f"{display_name}"
            )
            return current_target

        # Search existing layer stack
        layer_stack = stage.GetLayerStack(includeSessionLayers=False)
        for layer in layer_stack:
            name = layer.GetDisplayName()
            if name and (
                "rigging" in name.lower() or "rig" in name.lower()
            ):
                self.log.debug(f"Found existing rigging layer: {name}")
                return layer

        # Create new rigging layer as sublayer of root
        root_layer = stage.GetRootLayer()
        root_path = root_layer.realPath
        asset_dir = os.path.dirname(root_path) if root_path else ""

        if asset_dir:
            rigging_path = os.path.join(
                asset_dir, "rigging.usda"
            ).replace("\\", "/")
            try:
                rigging_layer = Sdf.Layer.FindOrOpen(rigging_path)
                if not rigging_layer:
                    rigging_layer = Sdf.Layer.CreateNew(rigging_path)
                    self.log.info(
                        f"Created new rigging layer: {rigging_path}"
                    )
            except Exception:
                rigging_layer = Sdf.Layer.CreateAnonymous("rigging")
                self.log.debug("Using anonymous rigging layer")
        else:
            rigging_layer = Sdf.Layer.CreateAnonymous("rigging")
            self.log.debug("Using anonymous rigging layer (no root path)")

        # Add to root layer sublayers if needed
        sublayer_paths = root_layer.subLayerPaths
        layer_id = rigging_layer.identifier
        if layer_id not in sublayer_paths:
            sublayer_paths.append(layer_id)
            self.log.debug(
                f"Added rigging layer to root sublayers: {layer_id}"
            )

        return rigging_layer

    def _export_usd_layer(self, instance, staging_dir):
        """Export the rigging layer to staging directory.

        Returns:
            str: Path to exported layer or None
        """
        try:
            import mayaUsd

            proxy_path = instance.data.get("usdStageProxyPath")
            if not proxy_path:
                self.log.warning(
                    "Cannot export USD layer: no proxy shape"
                )
                return None

            stage = mayaUsd.ufe.getStage(proxy_path)
            if not stage:
                self.log.warning(
                    "Cannot export USD layer: stage not found"
                )
                return None

            # The edit target should be the rigging layer
            edit_layer = stage.GetEditTarget().GetLayer()

            filename = "rigging.usda"
            filepath = os.path.join(
                staging_dir, filename
            ).replace("\\", "/")

            edit_layer.Export(filepath)
            self.log.debug(f"Exported USD layer to: {filepath}")
            return filepath

        except Exception as exc:
            self.log.warning(f"Failed to export USD layer: {exc}")
            return None
