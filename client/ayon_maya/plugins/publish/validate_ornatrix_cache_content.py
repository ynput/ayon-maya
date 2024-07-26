import inspect
import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)

from ayon_maya.api import plugin
from maya import cmds


class ValidateOrnatrixCacheContent(plugin.MayaInstancePlugin,
                                   OptionalPyblishPluginMixin):
    """Adheres to the content of 'oxcache' product type

    See `get_description` for more details.

    """

    order = ValidateContentsOrder
    families = ["oxcache", "oxrig"]
    label = "Validate Ornatrix Cache Content"
    actions = [ayon_maya.api.action.SelectInvalidAction]

    optional = False

    @classmethod
    def get_invalid(cls, instance):

        nodes = list(instance[:])
        ox_hair_shapes = cmds.ls(nodes, type="HairShape")
        invalid = []
        if len(ox_hair_shapes) == 0:
            cls.log.warning("No Ornatrix Hair shapes found to cache from.")
            invalid.append(nodes)

        return invalid

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)

        if invalid:
            raise PublishValidationError(
                title="Ornatrix cache content is invalid",
                message="Ornatrix cache content is invalid. "
                        "See log for more details.",
                description=self.get_description()
            )

    @classmethod
    def get_description(self):
        return inspect.cleandoc("""
            ### Ornatrix cache content is invalid

            Your oxrig or oxcache instance does not adhere to the rules of an
            oxcache product type:

            - Must have a Ornatrix `HairShape` nodes to cache.

            Using the *Select Invalid* action will select all nodes that do
            not adhere to these rules.
        """)
