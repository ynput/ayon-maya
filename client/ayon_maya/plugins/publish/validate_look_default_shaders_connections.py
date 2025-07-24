import pyblish.api
from ayon_core.pipeline.publish import (
    PublishValidationError,
    RepairContextAction,
)
from ayon_maya.api import plugin
from maya import cmds


class ValidateLookDefaultShadersConnections(plugin.MayaContextPlugin):
    """Validate default shaders in the scene have their default connections.

    Any of the following should be connected to initialShadingGroup:
    - openPBR_shader1 (maya 2026+),
    - standardSurface1 (maya 2024-2025),
    - or lambert1 (maya 2023 and before)

    When disconnected then another material than e.g. the lambert1 will be
    identified as the default shader which can have unpredictable results.

    To fix, the default connections need to be made again. See the logs for
    more details on which connections are missing.
    """

    order = pyblish.api.ValidatorOrder - 0.4999
    families = ['look']
    label = 'Look Default Shader Connections'
    actions = [RepairContextAction]

    # The default connections to check
    DEFAULTS = {
        "initialShadingGroup.surfaceShader": [
            "openPBR_shader1.outColor",
            "standardSurface1.outColor",
            "lambert1.outColor",
        ],
        "initialParticleSE.surfaceShader": [
            "openPBR_shader1.outColor",
            "standardSurface1.outColor",
            "lambert1.outColor",
        ],
        "initialParticleSE.volumeShader": ["particleCloud1.outColor"],
    }

    def process(self, context):

        if self.get_invalid():
            raise PublishValidationError(
                "Default shaders in your scene do not have their "
                "default shader connections. Please repair them to continue."
            )

    @classmethod
    def get_invalid(cls):

        # Process as usual
        invalid = list()
        for plug, valid_inputs in cls.DEFAULTS.items():
            inputs = cmds.listConnections(plug,
                                          source=True,
                                          destination=False,
                                          plugs=True) or None
            if not inputs or inputs[0] not in valid_inputs:
                cls.log.error(
                    "{0} is not connected to {1}. This can result in "
                    "unexpected behavior. Please reconnect to continue."
                    "".format(plug, " or ".join(valid_inputs))
                )
                invalid.append(plug)

        return invalid

    @classmethod
    def repair(cls, context):
        invalid = cls.get_invalid()
        for plug in invalid:
            valid_inputs = cls.DEFAULTS[plug]
            for valid_input in valid_inputs:
                if cmds.objExists(valid_input):
                    cls.log.info(
                        "Connecting {} -> {}".format(valid_input, plug)
                    )
                    cmds.connectAttr(valid_input, plug, force=True)
                    break
