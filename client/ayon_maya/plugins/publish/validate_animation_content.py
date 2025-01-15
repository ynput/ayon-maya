import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin


class ValidateAnimationContent(plugin.MayaInstancePlugin,
                               OptionalPyblishPluginMixin):
    """Adheres to the content of 'animation' product type

    - Must have collected `out_hierarchy` data.
    - All nodes in `out_hierarchy` must be in the instance.

    """

    order = ValidateContentsOrder
    families = ["animation"]
    label = "Animation Content"
    actions = [ayon_maya.api.action.SelectInvalidAction]
    optional = False

    @classmethod
    def get_invalid(cls, instance):
        if "animation.abc" not in instance.data["families"]:
            cls.log.debug("Skipping Validate Animation content.")
            return
        out_set = next((i for i in instance.data["setMembers"] if
                        i.endswith("out_SET")), None)

        assert out_set, ("Instance '%s' has no objectSet named: `OUT_set`. "
                         "If this instance is an unloaded reference, "
                         "please deactivate by toggling the 'Active' attribute"
                         % instance.name)

        assert 'out_hierarchy' in instance.data, "Missing `out_hierarchy` data"

        out_sets = [node for node in instance if node.endswith("out_SET")]
        msg = "Couldn't find exactly one out_SET: {0}".format(out_sets)
        assert len(out_sets) == 1, msg

        # All nodes in the `out_hierarchy` must be among the nodes that are
        # in the instance. The nodes in the instance are found from the top
        # group, as such this tests whether all nodes are under that top group.

        lookup = set(instance[:])
        invalid = [node for node in instance.data['out_hierarchy'] if
                   node not in lookup]

        return invalid

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                "Animation content is invalid. See log.")
