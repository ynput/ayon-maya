"""Validators for Animation Cache USD publishing.

Ensures that instances meet requirements before extraction.
"""

import maya.cmds as cmds
import pyblish.api
from ayon_core.pipeline import PublishValidationError
from ayon_maya.api import plugin


class ValidateAnimatedMembersExist(plugin.MayaInstancePlugin):
    """Validate that animated members exist in the instance."""

    order = pyblish.api.ValidatorOrder
    families = ["animationCacheUsd"]
    label = "Validate Animated Members Exist"

    def process(self, instance):
        """Check that setMembers is not empty."""

        members = instance.data.get("setMembers", [])

        if not members:
            raise PublishValidationError(
                f"Instance '{instance.name}' has no animated members selected. "
                "Please select the geometry to animate."
            )

        # Verify members still exist in scene
        invalid_members = []
        for member in members:
            if not cmds.objExists(member):
                invalid_members.append(member)

        if invalid_members:
            raise PublishValidationError(
                f"Instance '{instance.name}' has invalid members "
                f"(no longer exist): {invalid_members}"
            )


class ValidateAssetPrimPathResolved(plugin.MayaInstancePlugin):
    """Validate that original asset prim path was resolved."""

    order = pyblish.api.ValidatorOrder + 0.1
    families = ["animationCacheUsd"]
    label = "Validate Asset Prim Path"
    optional = False

    def process(self, instance):
        """Check that asset prim path is available."""

        prim_path = instance.data.get("originalAssetPrimPath", "")

        if not prim_path:
            self.log.warning(
                f"Instance '{instance.name}' could not auto-detect asset "
                "prim path. The contribution layer may not be placed at the "
                "correct location in the shot composition. Please set the "
                "'Original Asset Prim Path' in the instance attributes if "
                "auto-detection fails."
            )


class ValidateFrameRange(plugin.MayaInstancePlugin):
    """Validate animation frame range."""

    order = pyblish.api.ValidatorOrder + 0.2
    families = ["animationCacheUsd"]
    label = "Validate Frame Range"

    def process(self, instance):
        """Check that frame range is valid."""

        frame_start = instance.data.get("frameStart")
        frame_end = instance.data.get("frameEnd")

        if frame_start is None or frame_end is None:
            self.log.warning(
                f"Instance '{instance.name}' has incomplete frame range: "
                f"start={frame_start}, end={frame_end}. "
                "Using current playback range."
            )
            return

        if frame_start >= frame_end:
            raise PublishValidationError(
                f"Instance '{instance.name}' has invalid frame range: "
                f"start ({frame_start}) >= end ({frame_end})"
            )

        # Validate sampling settings
        sampling_mode = instance.data.get("samplingMode", "sparse")
        if sampling_mode == "custom":
            custom_step = instance.data.get("customStepSize", 1.0)
            if custom_step <= 0:
                raise PublishValidationError(
                    f"Instance '{instance.name}' has invalid custom step size: "
                    f"{custom_step}. Must be greater than 0."
                )
