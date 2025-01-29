import os

from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    RepairAction,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin
from maya import cmds


class ValidateRenderImageRule(plugin.MayaInstancePlugin,
                              OptionalPyblishPluginMixin):
    """Validates Maya Workpace "images" file rule matches project settings.

    This validates against the configured default render image folder:
        Studio Settings > Project > Maya >
        Render Settings > Default render image folder.

    """

    order = ValidateContentsOrder
    label = "Images File Rule (Workspace)"
    families = ["renderlayer"]
    actions = [RepairAction]
    optional = False

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        required_images_rule = os.path.normpath(
            self.get_default_render_image_folder(instance)
        )
        current_images_rule = os.path.normpath(
            cmds.workspace(fileRuleEntry="images")
        )

        if current_images_rule != required_images_rule:
            raise PublishValidationError(
                (
                    "Invalid workspace `images` file rule value: '{}'. "
                    "Must be set to: '{}'"
                ).format(current_images_rule, required_images_rule))

    @classmethod
    def repair(cls, instance):

        required_images_rule = cls.get_default_render_image_folder(instance)
        current_images_rule = cmds.workspace(fileRuleEntry="images")

        if current_images_rule != required_images_rule:
            cmds.workspace(fileRule=("images", required_images_rule))
            cmds.workspace(saveWorkspace=True)

    @classmethod
    def get_default_render_image_folder(cls, instance):
        # Allow custom staging dir to override the expected output directory
        # of the renders
        if instance.data.get("stagingDir_is_custom", False):
            staging_dir = instance.data.get("stagingDir")
            if staging_dir:
                cls.log.debug(
                    "Staging dir found: \"{}\". Ignoring setting from "
                    "`project_settings/maya/render_settings/"
                    "default_render_image_folder`.".format(staging_dir)
                )
                return staging_dir

        return (
            instance.context.data
            ["project_settings"]
            ["maya"]
            ["render_settings"]
            ["default_render_image_folder"]
        )
