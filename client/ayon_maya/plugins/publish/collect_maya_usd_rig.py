"""Collect Maya USD Rig instance data for publishing."""
from maya import cmds

import pyblish.api
from ayon_core.pipeline import PublishValidationError
from ayon_maya.api import plugin


class CollectMayaUsdRig(plugin.MayaInstancePlugin):
    """Collect USD Rig instance data.

    Validates that:
    - mayaUsdProxyShape exists in scene
    - USD edit target layer is set
    - Rig members are defined

    Stores for extractor:
    - usdProxyShape: path to proxy
    - usdEditTargetLayer: identifier of target layer
    - setMembers: rig nodes to export
    """

    label = "Collect Maya USD Rig"
    order = pyblish.api.CollectorOrder + 0.1
    hosts = ["maya"]
    families = ["mayaUsdRig"]

    def process(self, instance):
        """Collect USD rig data.

        Args:
            instance: Pyblish instance

        Raises:
            PublishValidationError: If USD setup is invalid
        """
        try:
            cmds.loadPlugin("mayaUsdPlugin", quiet=True)
        except RuntimeError as e:
            raise PublishValidationError(
                f"Instance '{instance.name}': "
                "Maya USD plugin not available"
            ) from e

        # 1. Validate mayaUsdProxyShape exists
        proxies = cmds.ls(type="mayaUsdProxyShape", long=True)
        if not proxies:
            raise PublishValidationError(
                f"Instance '{instance.name}': "
                "No mayaUsdProxyShape found in scene. "
                "Load a USD Asset first using 'Load Maya USD'"
            )

        # Store the first proxy shape
        proxy_shape = proxies[0]
        instance.data["usdProxyShape"] = proxy_shape
        instance.data["usdStageProxyPath"] = proxy_shape

        # 2. Get stage and validate edit target layer
        try:
            import mayaUsd

            stage = mayaUsd.ufe.getStage(proxy_shape)
            if not stage:
                raise PublishValidationError(
                    f"Instance '{instance.name}': "
                    f"Unable to get USD stage from {proxy_shape}"
                )

            edit_target = stage.GetEditTarget()
            if not edit_target:
                raise PublishValidationError(
                    f"Instance '{instance.name}': "
                    "No USD edit target layer set. "
                    "Use 'Maya USD Layer Editor' to set target layer"
                )

            # Store edit target layer for extractor
            edit_layer = edit_target.GetLayer()
            instance.data["usdEditTargetLayer"] = edit_layer
            self.log.debug(
                f"Edit target layer: {edit_layer.GetDisplayName()}"
            )

        except ImportError as e:
            raise PublishValidationError(
                f"Instance '{instance.name}': "
                "Unable to import mayaUsd module"
            ) from e
        except Exception as e:
            raise PublishValidationError(
                f"Instance '{instance.name}': "
                f"Error accessing USD stage: {str(e)}"
            ) from e

        # 3. Collect rig members
        objset = instance.data.get("instance_node")
        members = []
        if objset:
            members = cmds.sets(objset, query=True) or []
            if members:
                members = cmds.ls(members, long=True) or []

        instance.data["setMembers"] = members
        instance.data["rigMembers"] = members

        self.log.info(
            f"Collected USD rig '{instance.name}' with {len(members)} members"
        )
