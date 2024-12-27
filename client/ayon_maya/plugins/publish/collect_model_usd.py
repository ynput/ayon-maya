import pyblish.api
from ayon_maya.api import plugin
from ayon_core.pipeline import AYONPyblishPluginMixin


class CollectModelProductTypeUSDExport(plugin.MayaInstancePlugin,
                                       AYONPyblishPluginMixin):
    """Mark 'model' product type for USD export"""

    order = pyblish.api.CollectorOrder - 0.5
    label = "Mark 'model' product type for USD export"
    families = ["model"]
    enabled = True

    def process(self, instance):
        # Do nothing
        pass

    @classmethod
    def get_attr_defs_for_instance(
        cls, create_context: "CreateContext", instance: "CreatedInstance"
    ):
        """
        When this plug-in is enabled this will make it so that the instance
        is registered to be published as USD using Maya USD exporter by marking
        it with the families.

        This *seems* to work, however it may be undefined whether this logic
        runs BEFORE the relevant Maya USD and USD plug-ins that check what
        attribute definitions to show for these families. As such, it *may*
        occur that the families are added 'too late' for them to be picked up.
        But so far it seems so good - and likely they are collected in plug-in
        "order" (and with this being ordered very early we should be fine?)

        """
        # Filtering of instance, if needed, can be customized
        if not cls.instance_matches_plugin_families(instance):
            return []

        # Instance.data does not have `setdefault` so we need to check if the
        # key exists
        if "families" not in instance.data:
            instance.data["families"] = []

        families = instance.data["families"]
        families.append("usd")
        families.append("mayaUsd")
        return []
