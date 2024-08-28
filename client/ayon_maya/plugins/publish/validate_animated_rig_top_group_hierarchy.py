# -*- coding: utf-8 -*-
"""Plugin for validating naming conventions."""
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin
from maya import cmds


class ValidateAnimatedRigTopGroupHierarchy(plugin.MayaInstancePlugin,
                                           OptionalPyblishPluginMixin):
    """Validates top group hierarchy in the SETs
    Make sure the object inside the SETs are always top
    group of the hierarchy
    """
    order = ValidateContentsOrder + 0.05
    label = "Animated Rig Top Group Hierarchy"
    families = ["animation.fbx"]
    optional = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        invalid = []
        skeleton_mesh_data = instance.data("animated_skeleton", [])
        if skeleton_mesh_data:
            invalid =  cmds.ls(skeleton_mesh_data, assemblies=True, long=True)

            if invalid:
                raise PublishValidationError(
                    "The skeletonAnim_SET includes the object which "
                    "is not at the top hierarchy: {}".format(invalid))
