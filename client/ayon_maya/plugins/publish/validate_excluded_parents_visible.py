import inspect

from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError
)
import ayon_maya.api.action
from ayon_maya.api import plugin, lib
import pyblish.api

from maya import cmds


class ValidateExcludedParentsVisible(plugin.MayaInstancePlugin,
                                     OptionalPyblishPluginMixin):
    """Validate whether all parents are visible in frame range when 'include
    parent hierarchy' is disabled for the instance.

    This validation helps to detect the issue where an animator may have hidden
    or keyed visibilities on parent nodes for an export where these parents
    are not included in the export. Because if so, those invisibilities would
    not be included in the export either, giving a different visual result than
    what the artist likely intended in their workfile

    """

    order = pyblish.api.ValidatorOrder
    families = ["pointcache", "animation"]
    label = "Excluded parents visible"
    actions = [ayon_maya.api.action.SelectInvalidAction]

    @classmethod
    def get_invalid(cls, instance):

        # Only validate if we exclude parent hierarchy
        if instance.data.get("includeParentHierarchy", True):
            return []

        if "out_hierarchy" in instance.data:
            # Animation instances
            members = instance.data["out_hierarchy"]
        else:
            members = instance.data["setMembers"]

        members = cmds.ls(members, type="dagNode", long=True)  # DAG nodes only
        if not members:
            cls.log.debug("No members found in instance.")
            return []

        roots = lib.get_highest_in_hierarchy(members)

        # If there are no parents to the root we are already including the
        # full hierarchy, so we can skip checking visibilities on parents
        parents = cmds.listRelatives(roots, parent=True, fullPath=True)
        if not parents:
            return []

        # Include ancestors to check for visibilities on them
        ancestors = list(parents)
        for parent in parents:
            ancestors.extend(lib.iter_parents(parent))

        # Check if the parent is hidden anywhere within the frame range
        invalid = []
        frame_start = int(instance.data["frameStartHandle"])
        frame_end = int(instance.data["frameEndHandle"])

        cls.log.debug(
            "Validating invisibilities for excluded ancestors in frame "
            f"range {frame_start}-{frame_end}: {ancestors}.")
        for ancestor in ancestors:
            attr = f"{ancestor}.visibility"

            # We need to check whether the ancestor is ever invisible
            # during the frame range if it has inputs
            has_inputs = bool(cmds.listConnections(
                attr, source=True, destination=False))
            if has_inputs:
                for frame in range(frame_start, frame_end+1):
                    if cmds.getAttr(attr, time=frame):
                        continue

                    # We found an invisible frame
                    cls.log.warning(
                        "Excluded parent is invisible on frame "
                        f"{frame}: {ancestor}")
                    invalid.append(ancestor)
                    break

            # If no inputs, check the current visibility
            elif not cmds.getAttr(attr):
                cls.log.warning(f"Excluded parent is invisible: {ancestor}")
                invalid.append(ancestor)

        return invalid

    def process(self, instance):
        """Process all the nodes in the instance 'objectSet'"""
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:
            invalid_list = "\n".join(f"- {node}" for node in invalid)

            raise PublishValidationError(
                "Invisible parents found that are excluded from the export:\n"
                "{0}".format(invalid_list),
                title="Excluded parents are invisible",
                description=self.get_description()
            )

    @staticmethod
    def get_description():
        return inspect.cleandoc("""### Excluded parents are invisible

        The instance is set to exclude the parent hierarchy, however the
        excluded parents are invisible within the exported frame range.
        This may be on all frames, of if animated on only certain frames.
        
        Because the export excludes those parents the exported geometry will
        **not** have these (animated) invisibilities and will appear visible
        in the output regardless of how your scene looked on export.
        
        To resolve this, either move the invisibility down into the hierarchy
        that you are including in the export. Or, export with include parent
        hierarchy enabled.
        """)
