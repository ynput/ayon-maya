from maya import cmds

from ayon_core.pipeline.publish import (
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin
from ayon_maya.api.lib import (
    USD_RIG_ANIMATION_CREATOR_ID,
    get_usd_maya_reference_for_nodes,
)


class ValidateAnimationUsdRig(plugin.MayaInstancePlugin):
    """Validate the animation of a USD rig can contribute to its USD asset.

    The animation of a rig that is loaded from a `MayaReference` prim in a
    USD is published as overlay onto the prim of the asset that holds the
    rig. This requires that:

    - The rig is still related to that prim.
    - The animation is extracted as USD by `Extract USD Animation`.

    It also warns when the output of the rig would not end up on existing
    prims of the USD asset.
    """

    order = ValidateContentsOrder
    families = ["animation"]
    label = "Validate USD Rig Animation"

    def process(self, instance):
        if (
            instance.data.get("creator_identifier")
            != USD_RIG_ANIMATION_CREATOR_ID
        ):
            return

        publish_attributes = instance.data.get("publish_attributes", {})
        if not publish_attributes.get(
            "CollectUSDLayerContributions", {}
        ).get("contribution_enabled"):
            self.log.debug("Instance does not contribute to USD; skipping.")
            return

        reference = get_usd_maya_reference_for_nodes(instance[:])
        if reference is None:
            raise PublishValidationError(
                "The rig is not related to a MayaReference prim of a loaded "
                "USD.",
                title="USD rig is not related to USD",
                description=(
                    "## USD rig is not related to USD\n"
                    "The animation is published as overlay onto the USD "
                    "asset that the rig was loaded from, but the rig is not "
                    "related to a prim in a loaded USD anymore. This can "
                    "happen if the USD does not contain the rig anymore or "
                    "if the rig was not loaded from USD.\n\n"
                    "Either disable the USD contribution of the instance or "
                    "load the rig from the USD with the **Load USD rigs** "
                    "action on the USD container in the scene inventory and "
                    "transfer the animation to that rig."
                )
            )

        if not publish_attributes.get("ExtractMayaUsdAnim", {}).get("active"):
            raise PublishValidationError(
                "The animation is not extracted as USD.",
                title="USD rig animation requires USD extraction",
                description=(
                    "## USD rig animation requires USD extraction\n"
                    "The animation is published as overlay onto the USD "
                    "asset that the rig was loaded from, which requires the "
                    "animation to be extracted as USD.\n\n"
                    "Enable **Extract USD Animation** for the instance, or "
                    "disable its USD contribution."
                )
            )

        self.warn_about_missing_prims(instance, reference)

    def warn_about_missing_prims(self, instance, reference):
        """Warn if the rig output does not match prims of the USD asset."""
        import mayaUsd.ufe

        out_set = next(
            (node for node in instance if node.endswith("out_SET")), None)
        if not out_set:
            return

        stage = mayaUsd.ufe.getStage(reference.proxy)
        for node in cmds.ls(
            cmds.sets(out_set, query=True), type="transform"
        ):
            name = node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            prim_path = f"{reference.asset_prim_path}/{name}"
            if not stage.GetPrimAtPath(prim_path):
                self.log.warning(
                    "The USD asset has no prim '%s' to overlay the "
                    "animation of '%s' on, it will be added as new prim. The "
                    "hierarchy of the rig output should match the USD asset.",
                    prim_path, node
                )
