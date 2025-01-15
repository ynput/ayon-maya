from collections import Counter

import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin
from maya import cmds


class ValidateUniqueNames(plugin.MayaInstancePlugin,
                          OptionalPyblishPluginMixin):
    """transform names should be unique

    ie: using cmds.ls(someNodeName) should always return shortname

    """

    order = ValidateContentsOrder
    families = ["model"]
    label = "Unique transform name"
    actions = [ayon_maya.api.action.SelectInvalidAction]
    optional = True

    @staticmethod
    def get_invalid(instance):
        """Returns the invalid transforms in the instance.

        Returns:
            list: Non-unique name transforms.

        """
        # Check whether Maya's 'short name' includes a longer path than just
        # the node name to check whether it's unique in the full scene.
        non_unique_transforms_in_instance = [
            tr for tr in cmds.ls(instance, type="transform")
            if '|' in tr
        ]

        # Only invalidate if the clash is within the current instance
        count = Counter()
        for transform in non_unique_transforms_in_instance:
            short_name = transform.rsplit("|", 1)[-1]
            count[short_name] += 1

        invalid = []
        for transform in non_unique_transforms_in_instance:
            short_name = transform.rsplit("|", 1)[-1]
            if count[short_name] >= 2:
                invalid.append(transform)

        return invalid

    def process(self, instance):
        """Process all the nodes in the instance "objectSet"""
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                "Nodes found with non-unique names:\n{0}".format(invalid))
