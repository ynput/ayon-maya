import pyblish.api

from ayon_core.lib import TextDef
from ayon_core.pipeline.publish import AYONPyblishPluginMixin
from ayon_maya.api import plugin


class CollectMayaUsdFilterProperties(plugin.MayaInstancePlugin,
                                     AYONPyblishPluginMixin):

    order = pyblish.api.CollectorOrder
    label = "Maya USD Export Chaser: Filter Properties"
    families = ["mayaUsd"]

    default_filter = ""

    @classmethod
    def get_attribute_defs(cls):
        return [
            TextDef(
                "filter_properties",
                label="USD Filter Properties",
                tooltip=(
                    "Filter USD properties using a pattern:\n"
                    "- Only include xforms: xformOp*\n"
                    "- All but xforms: * ^xformOp*\n"
                    "- All but mesh point data: * ^extent ^points "
                    "^faceVertex* ^primvars*\n\n"
                    "The pattern matching is very similar to SideFX Houdini's "
                    "Pattern Matching in Parameters."
                ),
                placeholder="* ^xformOp* ^points",
                default=cls.default_filter
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
