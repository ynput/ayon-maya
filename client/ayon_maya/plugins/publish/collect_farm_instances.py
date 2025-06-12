import pyblish.api
from ayon_maya.api import plugin


class CollectFarmInstances(plugin.MayaInstancePlugin):
    """Collect Farm Instances for remote publish
    """

    order = pyblish.api.CollectorOrder + 0.223
    label = "Collect Farm Instances"
    families = ["animation", "pointcache"]
    targets = ["local"]

    def process(self, instance):
        if instance.data.get("farm"):
            instance.data["families"].append("remote_publish_on_farm")


class CollectRemoteCacheInstances(plugin.MayaInstancePlugin):
    """Collect Cache instances for publish, only works for headless mode

    """

    order = pyblish.api.CollectorOrder + 0.223
    label = "Collect Remote Cache Instances"
    families = ["animation", "pointcache"]
    targets = ["remote"]

    def process(self, instance):
        self.log.debug("Processing Cache Farm Instances.")
        instance.data["farm"] = False
