"""Extract rig as Maya Scene + USD Maya Reference Prim."""
import os

from maya import cmds

from ayon_maya.api import plugin
from ayon_maya.api.lib import maintained_selection
from ayon_maya.api.usdlib import containerise_prim
from ayon_core.pipeline import (
    PublishValidationError,
    get_representation_context
)


class ExtractMayaUsdRig(plugin.MayaExtractorPlugin):
    """Extract rig as Maya Scene and create USD Maya Reference Prim.

    This extractor:
    1. Exports the rig as .mb (Maya Binary)
    2. Creates a new "rigging" USD layer if needed
    3. Creates a Maya Reference Prim in the USD edit target
    4. Containerizes the prim with Ayon metadata
    5. Exports the rigging layer as .usd
    """

    label = "Extract Maya USD Rig"
    families = ["mayaUsdRig"]
    scene_type = "mb"

    def process(self, instance):
        """Extract rig for USD asset.

        Args:
            instance: Pyblish instance
        """
        staging_dir = self.staging_dir(instance)

        # 1. EXPORT RIG AS MAYA BINARY
        self.log.info("Exporting rig as Maya binary...")
        mb_file = self._export_rig_mb(instance, staging_dir)

        # 2. MANAGE USD LAYER AND CREATE MAYA REFERENCE PRIM
        self.log.info("Creating Maya Reference Prim in USD...")
        prim = self._create_maya_reference_prim(instance, staging_dir, mb_file)

        if not prim:
            raise PublishValidationError(
                f"Failed to create Maya Reference Prim for {instance.name}"
            )

        # 3. CONTAINERIZE PRIM WITH AYON METADATA
        self.log.info("Containerizing USD prim...")
        self._containerize_prim(instance, prim)

        # 4. EXPORT USD LAYER
        self.log.info("Exporting USD rigging layer...")
        usd_file = self._export_usd_layer(instance, staging_dir)

        # 5. ADD REPRESENTATIONS
        if "representations" not in instance.data:
            instance.data["representations"] = []

        # .mb representation
        mb_filename = os.path.basename(mb_file)
        instance.data["representations"].append({
            "name": "mb",
            "ext": "mb",
            "files": mb_filename,
            "stagingDir": staging_dir
        })

        # .usd representation
        if usd_file:
            usd_filename = os.path.basename(usd_file)
            instance.data["representations"].append({
                "name": "usd",
                "ext": "usd",
                "files": usd_filename,
                "stagingDir": staging_dir
            })

        self.log.info(
            f"Extracted rig '{instance.name}': "
            f"MB={mb_filename}, USD prim={prim.GetPath()}"
        )

    def _export_rig_mb(self, instance, staging_dir):
        """Export rig as Maya binary file.

        Args:
            instance: Pyblish instance
            staging_dir: Directory to export to

        Returns:
            str: Path to exported .mb file
        """
        filename = f"{instance.name}.mb"
        filepath = os.path.join(staging_dir, filename).replace("\\", "/")

        members = instance.data.get("setMembers", [])
        if not members:
            self.log.warning(f"Instance {instance.name} has no members to export")

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

    def _create_maya_reference_prim(self, instance, staging_dir, mb_file):
        """Create Maya Reference Prim in USD layer.

        Args:
            instance: Pyblish instance
            staging_dir: Staging directory
            mb_file: Path to exported .mb file

        Returns:
            pxr.Usd.Prim: Created prim or None if failed
        """
        try:
            cmds.loadPlugin("mayaUsdPlugin", quiet=True)
            import mayaUsd
            import mayaUsdAddMayaReference
        except Exception as e:
            raise PublishValidationError(
                f"Failed to load Maya USD plugins: {str(e)}"
            ) from e

        # Get USD stage and proxy shape
        proxy_path = instance.data.get("usdStageProxyPath")
        if not proxy_path:
            raise PublishValidationError(
                f"Instance {instance.name}: No USD proxy shape found"
            )

        try:
            stage = mayaUsd.ufe.getStage(proxy_path)
            if not stage:
                raise PublishValidationError(
                    f"Unable to get USD stage from {proxy_path}"
                )
        except Exception as e:
            raise PublishValidationError(
                f"Error accessing USD stage: {str(e)}"
            ) from e

        # Ensure rigging layer exists in stage
        rigging_layer = self._ensure_rigging_layer(stage, instance)

        # Get target prim path (hierarchized under asset name)
        asset_name = instance.data.get("folderPath", "asset").rsplit("/", 1)[-1]
        prim_path = f"/{asset_name}/Rig"

        # Create UFE path for the prim
        ufe_path = f"{proxy_path},{prim_path}"

        # Create Maya Reference Prim
        try:
            self.log.debug(
                f"Creating Maya Reference Prim with:\n"
                f"  UFE path: {ufe_path}\n"
                f"  MB file: {mb_file}\n"
                f"  Namespace: {instance.name}"
            )
            prim = mayaUsdAddMayaReference.createMayaReferencePrim(
                ufe_path,
                mb_file,
                instance.name,
            )

            # Check if prim creation succeeded
            if not prim:
                raise PublishValidationError(
                    f"createMayaReferencePrim() returned None for prim path {prim_path}. "
                    f"Check UFE path format and file path: {mb_file}"
                )

            self.log.debug(f"Created Maya Reference Prim at: {prim.GetPath()}")
            return prim
        except PublishValidationError:
            raise
        except Exception as e:
            self.log.error(f"Error creating Maya Reference Prim: {str(e)}")
            raise PublishValidationError(
                f"Failed to create Maya Reference Prim at {prim_path}: {str(e)}"
            ) from e

    def _ensure_rigging_layer(self, stage, instance):
        """Ensure 'rigging' layer exists in stage.

        Args:
            stage: USD stage
            instance: Pyblish instance

        Returns:
            pxr.Sdf.Layer: The rigging layer
        """
        from pxr import Sdf

        # Check if rigging layer already exists
        layer_stack = stage.GetLayerStack(includeSessionLayers=False)
        for layer in layer_stack:
            display_name = layer.GetDisplayName()
            if display_name and ("rigging" in display_name or "rig" in display_name):
                self.log.debug(f"Using existing layer: {display_name}")
                return layer

        # Get root layer path to create rigging layer nearby
        root_layer = stage.GetRootLayer()
        root_path = root_layer.realPath
        asset_dir = os.path.dirname(root_path)

        # Create/open rigging.usda layer
        rigging_layer_path = os.path.join(asset_dir, "rigging.usda")
        rigging_layer_path = rigging_layer_path.replace("\\", "/")

        try:
            rigging_layer = Sdf.Layer.FindOrOpen(rigging_layer_path)
            if not rigging_layer:
                rigging_layer = Sdf.Layer.CreateNew(rigging_layer_path)
                self.log.debug(f"Created new rigging layer: {rigging_layer_path}")
        except Exception as e:
            self.log.warning(
                f"Could not create rigging layer at {rigging_layer_path}: {str(e)}"
            )
            # Fallback to anonymous layer
            rigging_layer = Sdf.Layer.CreateAnonymous("rigging")
            self.log.debug("Using anonymous rigging layer")

        # Add to stage if not already present
        root_sublayer_paths = root_layer.subLayerPaths
        if rigging_layer_path not in root_sublayer_paths:
            root_sublayer_paths.append(rigging_layer_path)
            self.log.debug(f"Added rigging layer to stage: {rigging_layer_path}")

        return rigging_layer

    def _containerize_prim(self, instance, prim):
        """Containerize USD prim with Ayon metadata.

        Args:
            instance: Pyblish instance
            prim: USD prim to containerize
        """
        try:
            context = get_representation_context(instance.context)
            # Use placeholder representation since prim doesn't have ID yet
            if "representation" not in context:
                context["representation"] = {
                    "id": "",
                    "name": "usd"
                }

            containerise_prim(
                prim,
                name=instance.name,
                namespace=instance.name,
                context=context,
                loader="MayaUsdProxyAddMayaReferenceLoader"
            )
            self.log.debug(f"Containerized prim: {prim.GetPath()}")
        except Exception as e:
            self.log.warning(f"Failed to containerize prim: {str(e)}")
            # Don't fail the whole publish, continue

    def _export_usd_layer(self, instance, staging_dir):
        """Export USD rigging layer.

        Args:
            instance: Pyblish instance
            staging_dir: Directory to export to

        Returns:
            str: Path to exported layer or None
        """
        try:
            from pxr import Usd

            # Get the target layer from instance data
            proxy_path = instance.data.get("usdStageProxyPath")
            if not proxy_path:
                self.log.warning("Cannot export USD layer: no proxy shape")
                return None

            try:
                import mayaUsd
                stage = mayaUsd.ufe.getStage(proxy_path)
            except Exception as e:
                self.log.warning(f"Cannot get stage for USD export: {str(e)}")
                return None

            # Find rigging layer
            layer_stack = stage.GetLayerStack(includeSessionLayers=False)
            rigging_layer = None
            for layer in layer_stack:
                display_name = layer.GetDisplayName()
                if display_name and ("rigging" in display_name or "rig" in display_name):
                    rigging_layer = layer
                    break

            if not rigging_layer:
                self.log.warning("No rigging layer found to export")
                return None

            # Export layer
            filename = "rigging.usda"
            filepath = os.path.join(staging_dir, filename).replace("\\", "/")

            rigging_layer.Export(filepath)
            self.log.debug(f"Exported USD layer to: {filepath}")
            return filepath

        except Exception as e:
            self.log.warning(f"Failed to export USD layer: {str(e)}")
            return None
