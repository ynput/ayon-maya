import os
import pyblish.api
from ayon_maya.api import plugin


class CollectDataforCache(plugin.MayaInstancePlugin):
    """Collect data for caching to Deadline."""

    # Run after Collect Frames
    order = pyblish.api.CollectorOrder + 0.4991
    families = ["publish.farm"]
    targets = ["local", "remote"]
    label = "Collect Data for Cache"

    def process(self, instance):
        instance.data.update({
            # used in MayaCacheSubmitDeadline in ayon-deadline
            "plugin": "MayaBatch",
            "publish": True,
            "byFrameStep": instance.data.get(
                "creator_attributes", {}).get(
                    "step", 1.0)
        })
