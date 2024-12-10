import pyblish.api

from ayon_core.lib import TextDef
from ayon_core.pipeline.publish import AYONPyblishPluginMixin
from ayon_maya.api import plugin


class CollectMayaUsdFilterProperties(plugin.InstancePlugin,
                                     AYONPyblishPluginMixin):

    order = pyblish.api.CollectorOrder
    label = "Maya USD Export Chaser: Filter Properties"
    families = ["mayaUsd"]

    @classmethod
    def get_attribute_defs(cls):
        return [
            TextDef(
                "filter_properties",
                label="USD Filter Properties",
                tooltip=(
                    "Filter USD properties to export."
                ),
                placeholder="* ^xformOp* ^points"
            )
        ]

    def process(self, instance):
        attr_values = self.get_attr_values_from_data(instance.data)
        filter_pattern = attr_values.get("filter_properties")
        if not filter_pattern:
            return

        self.log.debug(
            "Enabling USD filter properties chaser "
            f"with pattern {filter_pattern}"
        )
        instance.data.setdefault("chaser", []).append("AYON_filterProperties")
        instance.data.setdefault("chaserArgs", []).append(
            ("AYON_filterProperties", "pattern", filter_pattern)
        )
