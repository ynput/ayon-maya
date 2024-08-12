import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin


class ValidateAnimationProductTypePublish(plugin.MayaInstancePlugin):
    """Validate Animation Product Type to ensure either fbx animation
    collector or collect animation output geometry(alembic) enabled for
    publishing
    """

    order = ValidateContentsOrder
    families = ["animation"]
    label = "Animation Product Type Publish"
    actions = [ayon_maya.api.action.SelectInvalidAction]

    @classmethod
    def get_invalid(cls, instance):
        invalid = []
        if {"animation.fbx", "animation.abc"} not in instance.data["families"]:
            cls.log.debug(
                "Either 'Collect Fbx Animation' or "
                "'Collect Animation Output Geometry(Alembic)' should be enabled")
            invalid.append(instance.name)

        return invalid

    def process(self, instance):
        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                "Invalid Animation Product Type. See log.")
