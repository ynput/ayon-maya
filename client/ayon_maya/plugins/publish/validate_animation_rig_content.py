import inspect
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin


class ValidateAnimatedRigContent(plugin.MayaInstancePlugin,
                                 OptionalPyblishPluginMixin):
    """Validates the `skeletonAnim_SET` must have one or more objects
    """
    order = ValidateContentsOrder + 0.05
    label = "Animated Rig Content"
    families = ["animation.fbx"]
    optional = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        skeleton_anim_nodes = instance.data("animated_skeleton", [])
        if not skeleton_anim_nodes:
            raise PublishValidationError(
                "The skeletonAnim_SET includes no objects.",
                description=self.get_description())

    @staticmethod
    def get_description():
        return inspect.cleandoc("""
            ### Invalid FBX export

            FBX export is enabled for your animation instance however the
            instance does not meet the required configurations for a valid
            export.

            It must contain at one or more objects in the `skeletonAnim_SET`.

        """)
