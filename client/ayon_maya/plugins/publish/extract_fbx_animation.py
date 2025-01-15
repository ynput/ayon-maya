# -*- coding: utf-8 -*-
import os

import pyblish.api
from ayon_maya.api import fbx
from ayon_maya.api.lib import get_namespace, namespaced, strip_namespace
from ayon_maya.api import plugin
from maya import cmds  # noqa


class ExtractFBXAnimation(plugin.MayaExtractorPlugin):
    """Extract Rig in FBX format from Maya.

    This extracts the rig in fbx with the constraints
    and referenced asset content included.
    This also optionally extract animated rig in fbx with
    geometries included.

    """
    order = pyblish.api.ExtractorOrder
    label = "Extract Animation (FBX)"
    families = ["animation.fbx"]

    def process(self, instance):
        # Define output path
        staging_dir = self.staging_dir(instance)
        filename = "{0}.fbx".format(instance.name)
        path = os.path.join(staging_dir, filename)
        path = path.replace("\\", "/")

        fbx_exporter = fbx.FBXExtractor(log=self.log)
        out_members = instance.data.get("animated_skeleton", [])
        # Export
        # TODO: need to set up the options for users to set up
        # the flags they intended to export
        instance.data["skeletonDefinitions"] = True
        instance.data["referencedAssetsContent"] = True
        fbx_exporter.set_options_from_instance(instance)

        namespace = get_namespace(out_members[0])
        relative_out_members = [
            strip_namespace(node, namespace) for node in out_members
        ]
        with namespaced(
            ":" + namespace,
            new=False,
            relative_names=True
        ) as namespace:
            fbx_exporter.export(relative_out_members, path)

        representations = instance.data.setdefault("representations", [])
        representations.append({
            'name': 'fbx',
            'ext': 'fbx',
            'files': filename,
            "stagingDir": staging_dir
        })

        self.log.debug(
            "Extracted FBX animation to: {0}".format(path))
