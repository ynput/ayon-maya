from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin
from maya import cmds


def get_non_root_nodes(nodes):
    """Return all nodes that are not root nodes (they have parents)

    Arguments:
        nodes (list[str]): Maya nodes.

    Returns:
        list[str]: Non-root maya node (long names)
    """
    nodes = cmds.ls(nodes, long=True)  # ensure long names
    return [
        node for node in nodes if node.count("|") > 2
    ]


class ValidateSkeletonTopGroupHierarchy(plugin.MayaInstancePlugin,
                                        OptionalPyblishPluginMixin):
    """Validates top group hierarchy in the SETs
    Make sure the object inside the SETs are always top
    group of the hierarchy
    """
    order = ValidateContentsOrder + 0.05
    label = "Skeleton Rig Top Group Hierarchy"
    families = ["rig.fbx"]
    optional = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        skeleton_mesh_nodes = instance.data("skeleton_mesh", [])
        if not skeleton_mesh_nodes:
            return

        invalid = get_non_root_nodes(skeleton_mesh_nodes)
        if invalid:
            raise PublishValidationError(
                "The skeletonMesh_SET includes the object which "
                "is not at the top hierarchy: {}".format(invalid))


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

        skeleton_anim_nodes = instance.data("animated_skeleton", [])
        if not skeleton_anim_nodes:
            return

        invalid = get_non_root_nodes(skeleton_anim_nodes)
        if invalid:
            raise PublishValidationError(
                "The skeletonAnim_SET includes the object which "
                "is not at the top hierarchy: {}".format(invalid))
