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
        if "animation.abc" in instance.data["families"]:
            return invalid
        elif "animation.fbx" in instance.data["families"]:
            return invalid
        else:
            cls.log.error(
                "Users must turn on either 'Collect Fbx Animation'\n"
                "or 'Collect Animation Output Geometry(Alembic)'\n"
                "for publishing\n"
            )
            invalid.append(instance.name)

        return invalid

    def process(self, instance):
        invalid = self.get_invalid(instance)
        if invalid:
            message = (
                "Invalid Animation Product Type\n"
                "Users must turn on either 'Collect Fbx Animation'\n"
                "or 'Collect Animation Output Geometry(Alembic)'\n"
                "for publishing\n"
            )
            raise PublishValidationError(message)
