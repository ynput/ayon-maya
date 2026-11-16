from __future__ import annotations

import pyblish.api

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
        scene_linear_units = context.data.get("linearUnits")
        scene_angular_units = context.data.get("angularUnits")
        scene_fps = context.data.get("fps")
        self.log.info(f"Units (linear): {scene_linear_units}")
        self.log.info(f"Units (angular): {scene_angular_units}")
        self.log.info(f"Units (time): {scene_fps} FPS")

        context_fps = mayalib.convert_to_maya_fps(
            self._get_context_fps(context)
        )

        project_settings: dict = context.data["project_settings"]
        linear_units, angular_units = get_scene_units_settings(
            project_settings
        )

        invalid = []
        # Check if units are correct
        if (
            self.validate_linear_units
            and scene_linear_units
            and scene_linear_units != linear_units
        ):
            invalid.append({
                "setting": "Linear units",
                "required_value": linear_units,
                "current_value": scene_linear_units
            })

        if (
            self.validate_angular_units
            and scene_angular_units
            and scene_angular_units != angular_units
        ):
            invalid.append({
                "setting": "Angular units",
                "required_value": angular_units,
                "current_value": scene_angular_units
            })

        if self.validate_fps and scene_fps and scene_fps != context_fps:
            invalid.append({
                "setting": "FPS",
                "required_value": context_fps,
                "current_value": scene_fps
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
            cls.log.info(f"Setting angular unit to '{angular_units}'")
            cmds.currentUnit(angle=angular_units)

        if cls.validate_linear_units:
            cls.log.info(f"Setting linear unit to '{linear_units}'")
            cmds.currentUnit(linear=linear_units)

        context_fps = cls._get_context_fps(context)
        cls.log.info(f"Setting time unit to match context: {context_fps}")
        mayalib.set_scene_fps(context_fps)

    @staticmethod
    def _get_context_fps(context: pyblish.api.Context) -> float:
        return context.data["taskEntity"]["attrib"]["fps"]
