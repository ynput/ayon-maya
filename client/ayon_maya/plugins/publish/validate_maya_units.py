import ayon_maya.api.lib as mayalib
import maya.cmds as cmds
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishXmlValidationError,
    RepairContextAction,
    ValidateSceneOrder,
)
from ayon_maya.api import plugin
from ayon_maya.api.lib import get_scene_units_settings


class ValidateMayaUnits(plugin.MayaContextPlugin,
                        OptionalPyblishPluginMixin):
    """Check if the Maya units are set correct"""

    order = ValidateSceneOrder
    label = "Maya Units"
    actions = [RepairContextAction]

    validate_linear_units = True

    validate_angular_units = True

    validate_fps = True

    nice_message_format = (
        "- <b>{setting}</b> must be <b>{required_value}</b>.  "
        "Your scene is set to <b>{current_value}</b>"
    )
    log_message_format = (
        "Maya scene {setting} must be '{required_value}'. "
        "Current value is '{current_value}'."
    )
    optional = False

    def process(self, context):
        if not self.is_active(context.data):
            return
        # Collected units
        linearunits = context.data.get('linearUnits')
        angularunits = context.data.get('angularUnits')

        fps = context.data.get('fps')

        folder_attributes = context.data["folderEntity"]["attrib"]
        folder_fps = mayalib.convert_to_maya_fps(folder_attributes["fps"])

        self.log.info('Units (linear): {0}'.format(linearunits))
        self.log.info('Units (angular): {0}'.format(angularunits))
        self.log.info('Units (time): {0} FPS'.format(fps))

        invalid = []

        project_settings: dict = context.data["project_settings"]
        linear_units, angular_units = get_scene_units_settings(
            project_settings
        )

        # Check if units are correct
        if (
            self.validate_linear_units
            and linearunits
            and linearunits != linear_units
        ):
            invalid.append({
                "setting": "Linear units",
                "required_value": linear_units,
                "current_value": linearunits
            })

        if (
            self.validate_angular_units
            and angularunits
            and angularunits != angular_units
        ):
            invalid.append({
                "setting": "Angular units",
                "required_value": angular_units,
                "current_value": angularunits
            })

        if self.validate_fps and fps and fps != folder_fps:
            invalid.append({
                "setting": "FPS",
                "required_value": folder_fps,
                "current_value": fps
            })

        if invalid:

            issues = []
            for data in invalid:
                self.log.error(self.log_message_format.format(**data))
                issues.append(self.nice_message_format.format(**data))
            issues = "\n".join(issues)

            raise PublishXmlValidationError(
                plugin=self,
                message="Invalid maya scene units",
                formatting_data={"issues": issues}
            )

    @classmethod
    def repair(cls, context):
        """Fix the current FPS setting of the scene, set to PAL(25.0 fps)"""

        linear_units, angular_units = get_scene_units_settings()
        if cls.validate_angular_units:
            cls.log.info("Setting angular unit to '{}'".format(angular_units))
            cmds.currentUnit(angle=angular_units)

        if cls.validate_linear_units:
            cls.log.info("Setting linear unit to '{}'".format(linear_units))
            cmds.currentUnit(linear=linear_units)

        cls.log.info("Setting time unit to match project")
        folder_entity = context.data["folderEntity"]
        mayalib.set_scene_fps(folder_entity["attrib"]["fps"])
