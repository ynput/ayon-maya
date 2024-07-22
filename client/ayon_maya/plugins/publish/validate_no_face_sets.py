import ayon_maya.api.action
import maya.cmds as cmds
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    RepairAction,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin

class ValidateNoFaceSets(plugin.MayaInstancePlugin,
                         OptionalPyblishPluginMixin):
    """Ensure the meshes don't have face sets """

    order = ValidateContentsOrder
    families = ['model']
    label = 'No Face Sets'
    actions = [ayon_maya.api.action.SelectInvalidAction,
               RepairAction]
    optional = False

    @staticmethod
    def get_invalid(instance):
        invalid = []
        members = instance.data["setMembers"]
        members = cmds.ls(members,
                          dag=True,
                          shapes=True,
                          type=("mesh", "nurbsCurve"),
                          noIntermediate=True,
                          long=True)
        if not instance.data.get("writeFaceSets"):
            invalid.append(members)
        return invalid


    def process(self, instance):
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                message="Write face sets is disabled",
                title="Write face sets is disabled",
                description=(
                    "## Write Face Sets Disabled\n"
                    "The mesh(es) require to have face sets to "
                    "generate material with multiple shading entities "
                    "for the Unreal Engine export."
                )
            )
