# -*- coding: utf-8 -*-
import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_maya.api import plugin
from maya import cmds  # noqa


class CollectFbxAnimation(plugin.MayaInstancePlugin,
                          OptionalPyblishPluginMixin):
    """Collect Animated Rig Data for FBX Extractor."""

    order = pyblish.api.CollectorOrder + 0.2
    label = "Collect Fbx Animation"
    families = ["animation"]
    optional = True
    input_connections = True
    up_axis = "y"

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        skeleton_sets = [
            i for i in instance
            if i.endswith("skeletonAnim_SET")
        ]
        if not skeleton_sets:
            return

        instance.data["families"].append("animation.fbx")
        instance.data["animated_skeleton"] = []
        for skeleton_set in skeleton_sets:
            skeleton_content = cmds.sets(skeleton_set, query=True)
            self.log.debug(
                "Collected animated skeleton data: {}".format(
                    skeleton_content
                ))
            if skeleton_content:
                instance.data["animated_skeleton"] = skeleton_content

        instance.data["upAxis"] = self.up_axis
        if self.input_connections:
            instance.data["inputConnections"] = self.input_connections
