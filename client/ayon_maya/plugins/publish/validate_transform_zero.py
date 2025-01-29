import inspect

import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin
from maya import cmds


class ValidateTransformZero(plugin.MayaInstancePlugin,
                            OptionalPyblishPluginMixin):
    """Transforms can't have any values

    To solve this issue, try freezing the transforms. So long
    as the transforms, rotation and scale values are zero,
    you're all good.

    """

    order = ValidateContentsOrder
    families = ["model"]
    label = "Transform Zero (Freeze)"
    actions = [ayon_maya.api.action.SelectInvalidAction]

    _identity = [1.0, 0.0, 0.0, 0.0,
                 0.0, 1.0, 0.0, 0.0,
                 0.0, 0.0, 1.0, 0.0,
                 0.0, 0.0, 0.0, 1.0]
    _tolerance = 1e-30
    optional = True

    @classmethod
    def get_invalid(cls, instance):
        """Returns the invalid transforms in the instance.

        This is the same as checking:
        - translate == [0, 0, 0] and rotate == [0, 0, 0] and
          scale == [1, 1, 1] and shear == [0, 0, 0]

        .. note::
            This will also catch camera transforms if those
            are in the instances.

        Returns:
            list: Transforms that are not identity matrix

        """

        transforms = cmds.ls(instance, type="transform")

        invalid = []
        for transform in transforms:
            if ('_LOC' in transform) or ('_loc' in transform):
                continue
            mat = cmds.xform(transform, q=1, matrix=True, objectSpace=True)
            if not all(abs(x - y) < cls._tolerance
                       for x, y in zip(cls._identity, mat)):
                invalid.append(transform)

        return invalid

    def process(self, instance):
        """Process all the nodes in the instance "objectSet"""
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)
        if invalid:
            names = "\n".join(
                " - {}".format(node) for node in invalid
            )

            raise PublishValidationError(
                title="Transform Zero",
                description=self.get_description(),
                message="The model publish allows no transformations. You must"
                        " 'freeze transformations'. to continue.\n\n"
                        "Nodes found with transform values:\n"
                        "{0}".format(names))

    @staticmethod
    def get_description():
        return inspect.cleandoc("""### Transform can't have any values

        The model publish allows no transformations.

        You must **freeze transformations** to continue.

        """)
