import inspect

import ayon_maya.api.action
from ayon_maya.api import lib
from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    PublishValidationError
)
from ayon_maya.api import plugin


class ValidateLookSets(plugin.MayaInstancePlugin):
    """Validate if any sets relationships are not being collected.

    Usually this collection fails if either the geometry or the shader are
    lacking a valid `cbId` attribute.

    If the relationship needs to be maintained you may need to
    create a *different** relationship or ensure the node has the `cbId`.

    **The relationship might be too broad (assigned to top node of hierarchy).
    This can be countered by creating the relationship on the shape or its
    transform. In essence, ensure the node the shader is assigned to has a
    `cbId`.*

    ### For example:

    Displacement objectSets (like V-Ray):

    It is best practice to add the transform of the shape to the
    displacement objectSet. Any parent groups will not work as groups
    do not receive a `cbId`. As such the assignments need to be
    made to the shapes or their transform.

    """

    order = ValidateContentsOrder
    families = ['look']
    label = 'Look Sets'
    actions = [ayon_maya.api.action.SelectInvalidAction]

    def process(self, instance):
        """Process all the nodes in the instance"""

        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                f"'{instance.name}' has relationships that could not be "
                f"collected, likely due to lack of a `cbId` on the relevant "
                f"nodes or sets.",
                description=self.get_description())

    @classmethod
    def get_invalid(cls, instance):
        """Get all invalid nodes"""

        relationships = instance.data["lookData"]["relationships"]
        invalid = []

        renderlayer = instance.data.get("renderlayer", "defaultRenderLayer")
        with lib.renderlayer(renderlayer):
            for node in instance:
                # get the connected objectSets of the node
                sets = lib.get_related_sets(node)
                if not sets:
                    continue

                # check if any objectSets are not present in the relationships
                missing_sets = [s for s in sets if s not in relationships]
                # We ignore sets with `_SET` for legacy reasons but unclear why
                # TODO: should we remove this exclusion?
                missing_sets = [s for s in missing_sets if '_SET' not in s]
                if missing_sets:
                    for missing_set in missing_sets:
                        cls.log.debug(missing_set)

                    # A set of this node is not coming along.
                    cls.log.error("Missing sets for node '{}':\n - {}".format(
                        node, "\n - ".join(missing_sets)
                    ))
                    invalid.append(node)
                    continue

                # Ensure the node is in the sets that are collected
                for shader_set, data in relationships.items():
                    if shader_set not in sets:
                        # no need to check for a set if the node
                        # isn't in it anyway
                        continue

                    member_nodes = [member['name'] for member in
                                    data['members']]
                    if node not in member_nodes:
                        # The node is not found in the collected set
                        # relationships
                        cls.log.error("Missing '{}' in collected set node "
                                      "'{}'".format(node, shader_set))
                        invalid.append(node)
                        continue

        return invalid

    @classmethod
    def get_description(cls):
        return """## Missing look sets\n""" + inspect.getdoc(cls)
