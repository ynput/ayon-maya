import pyblish.api
from ayon_maya.api import plugin


class CollectPointcacheVisibleOnly(plugin.MayaInstancePlugin):
    """Collect pointcache visible only data for instance."""

    order = pyblish.api.CollectorOrder + 0.4
    families = ["pointcache", "animation", "model", "vrayproxy.alembic"]
    label = "Collect Pointcache Visible Only"

    def process(self, instance):

        if instance.data["productBaseType"] == "animation":
            plugin_name = "ExtractAnimation"
        else:
            plugin_name = "ExtractAlembic"

        publish_attributes = instance.data.get("publish_attributes", {})
        plugin_attr_values = publish_attributes.get(plugin_name, {})

        if "visibleOnly" in plugin_attr_values:
            value = plugin_attr_values["visibleOnly"]
            instance.data["visibleOnly"] = value
            self.log.debug(
                f"Transferring visibleOnly to instance.data: {value}")
