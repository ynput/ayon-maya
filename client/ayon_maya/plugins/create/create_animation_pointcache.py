from maya import cmds

from ayon_maya.api import lib, plugin

from ayon_core.lib import BoolDef


def _get_animation_attr_defs(
        create_context,
        include_user_defined_attributes,
        include_parent_hierarchy=False):
    """Get Animation generic definitions."""
    defs = lib.collect_animation_defs(create_context=create_context)
    defs.extend(
        [
            BoolDef("farm", label="Submit to Farm"),
            BoolDef("refresh", label="Refresh viewport during export"),
            BoolDef(
                "includeParentHierarchy",
                label="Include Parent Hierarchy",
                tooltip=(
                    "Whether to include parent hierarchy of nodes in the "
                    "publish instance."
                ),
                default=include_parent_hierarchy
            ),
            BoolDef(
                "includeUserDefinedAttributes",
                label="Include User Defined Attributes",
                tooltip=(
                    "Whether to include all custom maya attributes found "
                    "on nodes as attributes in the Alembic data."
                ),
                default=include_user_defined_attributes
            ),
        ]
    )

    return defs


def convert_legacy_alembic_creator_attributes(node_data, class_name):
    """This is a legacy transfer of creator attributes to publish attributes
    for ExtractAlembic/ExtractAnimation plugin.
    """
    publish_attributes = node_data["publish_attributes"]

    if class_name in publish_attributes:
        return node_data

    attributes = [
        "attr",
        "attrPrefix",
        "visibleOnly",
        "writeColorSets",
        "writeFaceSets",
        "writeNormals",
        "renderableOnly",
        "visibleOnly",
        "worldSpace",
        "renderableOnly"
    ]
    plugin_attributes = {}
    for attr in attributes:
        if attr not in node_data["creator_attributes"]:
            continue
        value = node_data["creator_attributes"].pop(attr)

        plugin_attributes[attr] = value

    publish_attributes[class_name] = plugin_attributes

    return node_data


class CreateAnimation(plugin.MayaHiddenCreator):
    """Animation output for character rigs

    We hide the animation creator from the UI since the creation of it is
    automated upon loading a rig. There's an inventory action to recreate it
    for loaded rigs if by chance someone deleted the animation instance.
    """

    identifier = "io.openpype.creators.maya.animation"
    name = "animationDefault"
    label = "Animation"
    product_type = "animation"
    icon = "male"

    include_parent_hierarchy = False
    include_user_defined_attributes = False

    def read_instance_node(self, node):
        node_data = super(CreateAnimation, self).read_instance_node(node)
        node_data = convert_legacy_alembic_creator_attributes(
            node_data, "ExtractAnimation"
        )
        return node_data

    def get_instance_attr_defs(self):
        return _get_animation_attr_defs(self.create_context,
                                        self.include_user_defined_attributes,
                                        self.include_parent_hierarchy)


class CreatePointCache(plugin.MayaCreator):
    """Alembic pointcache for animated data"""

    identifier = "io.openpype.creators.maya.pointcache"
    label = "Pointcache"
    product_type = "pointcache"
    icon = "gears"
    include_user_defined_attributes = False

    def read_instance_node(self, node):
        node_data = super(CreatePointCache, self).read_instance_node(node)
        node_data = convert_legacy_alembic_creator_attributes(
            node_data, "ExtractAlembic"
        )
        return node_data

    def get_instance_attr_defs(self):
        return _get_animation_attr_defs(self.create_context,
                                        self.include_user_defined_attributes)

    def create(self, product_name, instance_data, pre_create_data):
        instance = super(CreatePointCache, self).create(
            product_name, instance_data, pre_create_data
        )
        instance_node = instance.get("instance_node")

        # For Arnold standin proxy
        proxy_set = cmds.sets(name=instance_node + "_proxy_SET", empty=True)
        cmds.sets(proxy_set, forceElement=instance_node)
