# -*- coding: utf-8 -*-
import pyblish.api
from ayon_maya.api import plugin


class CollectLayoutOptions(plugin.MayaInstancePlugin):
    """Collect Camera for FBX export."""

    order = pyblish.api.CollectorOrder + 0.2
    label = "Collect Layout Options"
    families = ["layout"]

    def process(self, instance):
        if instance.data.get("layout_options") == "fbx":
            instance.data["families"] += ["layout.fbx"]
        elif instance.data.get("layout_options") == "abc":
            instance.data["families"] += ["layout.abc"]
        else:
            self.log.error("No layout options found.")
