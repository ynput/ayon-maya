"""Create USD Rig for Maya - Rigging workflow for USD assets."""
from ayon_maya.api import plugin
from ayon_core.lib import BoolDef, TextDef

from maya import cmds


class CreateMayaUsdRig(plugin.MayaCreator):
    """Create rig for USD Asset with Maya Reference Prim integration.

    This creator enables the rigging workflow for USD assets:
    1. Load USD asset using LoadMayaUsd
    2. Set Edit Target Layer in Maya USD Layer Editor
    3. Create rig and publish using this creator
    4. Rig is exported as .mb and automatically imported via Maya Reference Prim
    5. A new "rigging" layer is created and contributes to the USD Asset
    """

    identifier = "io.ayon.creators.maya.mayausdrig"
    label = "Maya USD: Rig"
    product_base_type = "rig"
    product_type = product_base_type
    icon = "wheelchair"
    description = "Create Rig for USD Asset with Maya Reference Prim"

    allow_animation = False

    def get_publish_families(self):
        """Return publish families for extractors."""
        return ["rig", "mayaUsdRig"]

    def get_instance_attr_defs(self):
        """Define instance attributes specific to USD rig."""
        return [
            BoolDef(
                "includeGuides",
                label="Include Guide Curves",
                tooltip="Include guide curves and reference objects in export",
                default=True
            ),
            BoolDef(
                "preserveReferences",
                label="Preserve References",
                tooltip="Keep references in exported rig file",
                default=False
            ),
            TextDef(
                "rigSuffix",
                label="Rig Suffix",
                tooltip="Suffix for rig nodes (e.g., '_rig', '_jnt')",
                default="_rig",
                placeholder="_rig"
            ),
        ]

    def get_pre_create_attr_defs(self):
        """Define pre-create attributes with USD validations."""
        defs = super().get_pre_create_attr_defs()

        # Remove template hierarchy creation as rigs use duplicated USD geometry
        defs = [
            d for d in defs
            if d.key != "createAssetTemplateHierarchy"
        ]

        defs.append(
            BoolDef(
                "validateTargetLayer",
                label="Validate Target Layer",
                tooltip="Validate USD edit target layer exists",
                default=True
            )
        )

        return defs

    def create(self, product_name, instance_data, pre_create_data):
        """Create rig instance with USD target layer validation."""

        # Validate target layer if requested
        if pre_create_data.get("validateTargetLayer", True):
            self._validate_target_layer()

        # Call parent to create base instance
        super().create(product_name, instance_data, pre_create_data)

        instance_node = instance_data.get("instance_node")
        if not instance_node:
            # Fallback: try to get from instance object set in scene
            instance_node = next(
                (n for n in cmds.ls(type="objectSet")
                 if cmds.getAttr(f"{n}.instance_node", asString=True) == ""),
                None
            )

        if instance_node:
            self.log.info("Creating Rig instance sets...")
            # Create standard rig sets (similar to CreateRig)
            controls = cmds.sets(name=f"{product_name}_controls_SET", empty=True)
            skeleton = cmds.sets(name=f"{product_name}_skeleton_SET", empty=True)
            geometry = cmds.sets(name=f"{product_name}_geo_SET", empty=True)

            # Add sets to instance
            cmds.sets([controls, skeleton, geometry], forceElement=instance_node)
            self.log.info("Rig instance sets created successfully")

    def _validate_target_layer(self):
        """Validate that a USD edit target layer is available.

        Raises:
            RuntimeError: If no suitable USD setup is found.
        """
        try:
            cmds.loadPlugin("mayaUsdPlugin", quiet=True)
        except RuntimeError as e:
            raise RuntimeError(
                "Maya USD plugin not available. "
                "Please ensure 'mayaUsdPlugin' is installed."
            ) from e

        # Check if there's an active mayaUsdProxyShape in the scene
        proxies = cmds.ls(type="mayaUsdProxyShape", long=True)
        if not proxies:
            raise RuntimeError(
                "No mayaUsdProxyShape found in scene. "
                "Please load a USD Asset first using 'Load Maya USD'"
            )

        # Check if edit target is set in any proxy
        try:
            import mayaUsd

            for proxy in proxies:
                stage = mayaUsd.ufe.getStage(proxy)
                if stage and stage.GetEditTarget():
                    self.log.info(f"Found edit target layer in {proxy}")
                    return

            self.log.warning(
                "No edit target layer found in USD stage. "
                "Please use 'Maya USD Layer Editor' to set target layer. "
                "Publication will proceed but Maya Reference Prim creation may fail."
            )
        except ImportError as e:
            raise RuntimeError("Unable to import mayaUsd module") from e
