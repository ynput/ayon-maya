from ayon_core.pipeline.publish import (
    PublishValidationError,
    ValidateContentsOrder,
    OptionalPyblishPluginMixin
)
from ayon_maya.api import plugin


class ValidateSingleAssembly(plugin.MayaInstancePlugin,
                             OptionalPyblishPluginMixin):
    """Ensure the content of the instance is grouped in a single hierarchy

    The instance must have a single root node containing all the content.
    This root node *must* be a top group in the outliner.

    Example outliner:
        root_GRP
            -- geometry_GRP
               -- mesh_GEO
            -- controls_GRP
               -- control_CTL

    """

    order = ValidateContentsOrder
    families = ['rig']
    label = 'Single Assembly'

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        from maya import cmds

        assemblies = cmds.ls(instance, assemblies=True)

        # ensure unique (somehow `maya.cmds.ls` doesn't manage that)
        assemblies = set(assemblies)

        if len(assemblies) == 0:
            raise PublishValidationError(
                "One assembly required for: %s (currently empty?)" % instance
            )
        elif len(assemblies) > 1:
            raise PublishValidationError(
                'Multiple assemblies found: %s' % assemblies
            )
