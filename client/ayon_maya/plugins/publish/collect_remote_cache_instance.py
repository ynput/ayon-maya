import pyblish.api
from ayon_maya.api import plugin


class CollectRemoteCacheInstances(plugin.MayaInstancePlugin):
    """Collect Cache instances for publish, only works for headless mode

    """

    order = pyblish.api.CollectorOrder + 0.223
    label = "Collect Cache Farm Instances"
    targets = ["remote"]

    def process(self, instance):
        self.log.debug("Processing Cache Farm Instances.")
        if not instance.data.get("farm"):
            instance.data["publish"] = False
        instance.data["farm"] = False
