# -*- coding: utf-8 -*-
import pyblish.api
from ayon_maya.api import plugin
from ayon_core.pipeline.publish import OptionalPyblishPluginMixin
from maya import cmds  # noqa


class CollectFbxCamera(plugin.MayaInstancePlugin,
                       OptionalPyblishPluginMixin):
    """Collect Camera for FBX export."""

    order = pyblish.api.CollectorOrder + 0.2
    label = "Collect Camera for FBX export"
    families = ["camera"]
    optional = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        if not instance.data.get("families"):
            instance.data["families"] = []

        if "fbx" not in instance.data["families"]:
            instance.data["families"].append("fbx")

        instance.data["cameras"] = True
