# -*- coding: utf-8 -*-
import pyblish.api
from ayon_maya.api import plugin
from ayon_core.pipeline.publish import OptionalPyblishPluginMixin
from ayon_core.lib import (
    UISeparatorDef,
    UILabelDef,
    EnumDef,
    BoolDef
)
from maya import cmds  # noqa



class CollectFbxCamera(plugin.MayaInstancePlugin,
                       OptionalPyblishPluginMixin):
    """Collect Camera for FBX export."""

    order = pyblish.api.CollectorOrder + 0.2
    label = "Collect Camera for FBX export"
    families = ["camera"]
    optional = False
    input_connections = True
    up_axis = "y"

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        if not instance.data.get("families"):
            instance.data["families"] = []

        if "fbx" not in instance.data["families"]:
            instance.data["families"].append("fbx")

        instance.data["cameras"] = True

        attribute_values = self.get_attr_values_from_data(
            instance.data
        )

        instance.data["upAxis"] = attribute_values.get(
            "upAxis", self.up_axis)
        instance.data["inputConnections"] = attribute_values.get(
            "inputConnections", self.input_connections)

    @classmethod
    def get_attribute_defs(cls):
        defs = [
            UISeparatorDef("sep_fbx_options"),
            UILabelDef("Fbx Options"),
        ]
        defs.extend(
            super().get_attribute_defs() + [
            EnumDef("upAxis",
                    items=["y", "z"],
                    label="Up Axis",
                    default=cls.up_axis,
                    tooltip="Convert the scene's orientation in your FBX file"),
            BoolDef("inputConnections",
                    label="Input Connections",
                    default=cls.input_connections,
                    tooltip=(
                        "Whether input connections to "
                        "selected objects are to be exported."
                        ),
                    ),
            UISeparatorDef("sep_fbx_options_end")
        ])

        return defs
