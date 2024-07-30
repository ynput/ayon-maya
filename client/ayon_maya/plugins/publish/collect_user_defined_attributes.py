from maya import cmds
from ayon_maya.api import plugin
import pyblish.api


class CollectUserDefinedAttributes(plugin.MayaInstancePlugin):
    """Collect user defined attributes for nodes in instance."""

    order = pyblish.api.CollectorOrder + 0.45
    families = ["pointcache", "animation", "usd"]
    label = "Collect User Defined Attributes"

    def process(self, instance):

        # Collect user defined attributes.
        if not instance.data.get("creator_attributes", {}).get(
            "includeUserDefinedAttributes"
        ):
            return

        if "out_hierarchy" in instance.data:
            # animation family
            nodes = instance.data["out_hierarchy"]
        else:
            nodes = instance[:]
        if not nodes:
            return

        shapes = cmds.listRelatives(nodes, shapes=True, fullPath=True) or []
        nodes = set(nodes).union(shapes)

        attrs = cmds.listAttr(list(nodes), userDefined=True) or []
        user_defined_attributes = list(sorted(set(attrs)))
        instance.data["userDefinedAttributes"] = user_defined_attributes

        self.log.debug(
            "Collected user defined attributes: {}".format(
                ", ".join(user_defined_attributes)
            )
        )
