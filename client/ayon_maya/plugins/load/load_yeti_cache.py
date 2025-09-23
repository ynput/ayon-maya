import json
import os
import re
from collections import defaultdict

import clique
from ayon_core.settings import get_project_settings
from ayon_maya.api import lib
from ayon_maya.api.pipeline import containerise
from ayon_maya.api import plugin
from ayon_maya.api.plugin import get_load_color_for_product_type
from ayon_maya.api.yeti import create_yeti_variable
from maya import cmds

# Do not reset these values on update but only apply on first load
# to preserve any potential local overrides
SKIP_UPDATE_ATTRS = {
    "displayOutput",
    "viewportDensity",
    "viewportWidth",
    "viewportLength",
    "renderDensity",
    "renderWidth",
    "renderLength",
    "increaseRenderBounds"
}

SKIP_ATTR_MESSAGE = (
    "Skipping updating %s.%s to %s because it "
    "is considered a local overridable attribute. "
    "Either set manually or the load the cache "
    "anew."
)


def set_attribute(node, attr, value):
    """Wrapper of set attribute which ignores None values"""
    if value is None:
        return
    lib.set_attribute(node, attr, value)


class YetiCacheLoader(plugin.Loader):
    """Load Yeti Cache with one or more Yeti nodes"""

    product_types = {"yeticache", "yetiRig"}
    representations = {"fur"}

    label = "Load Yeti Cache"
    order = -9
    icon = "code-fork"
    color = "orange"

    def load(self, context, name=None, namespace=None, data=None):
        """Loads a .fursettings file defining how to load .fur sequences

        A single yeticache or yetiRig can have more than a single pgYetiMaya
        nodes and thus load more than a single yeti.fur sequence.

        The .fursettings file defines what the node names should be and also
        what "cbId" attribute they should receive to match the original source
        and allow published looks to also work for Yeti rigs and its caches.

        """

        product_type = context["product"]["productType"]

        # Build namespace
        folder_name = context["folder"]["name"]
        if namespace is None:
            namespace = self.create_namespace(folder_name)

        # Ensure Yeti is loaded
        if not cmds.pluginInfo("pgYetiMaya", query=True, loaded=True):
            cmds.loadPlugin("pgYetiMaya", quiet=True)

        # Create Yeti cache nodes according to settings
        path = self.filepath_from_context(context)
        settings = self.read_settings(path)
        nodes = []
        for node in settings["nodes"]:
            nodes.extend(self.create_node(namespace, node))

        group_name = "{}:{}".format(namespace, name)
        group_node = cmds.group(nodes, name=group_name)
        project_name = context["project"]["name"]

        settings = get_project_settings(project_name)
        color = get_load_color_for_product_type(product_type, settings)
        if color is not None:
            red, green, blue = color
            cmds.setAttr(group_node + ".useOutlinerColor", 1)
            cmds.setAttr(group_node + ".outlinerColor", red, green, blue)

        nodes.append(group_node)

        self[:] = nodes

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__
        )

    def remove(self, container):

        from maya import cmds

        namespace = container["namespace"]
        container_name = container["objectName"]

        self.log.info("Removing '%s' from Maya.." % container["name"])

        container_content = cmds.sets(container_name, query=True)
        nodes = cmds.ls(container_content, long=True)

        nodes.append(container_name)

        try:
            cmds.delete(nodes)
        except ValueError:
            # Already implicitly deleted by Maya upon removing reference
            pass

        cmds.namespace(removeNamespace=namespace, deleteNamespaceContent=True)

    def update(self, container, context):
        repre_entity = context["representation"]
        namespace = container["namespace"]
        container_node = container["objectName"]

        path = self.filepath_from_context(context)
        settings = self.read_settings(path)

        # Collect scene information of asset
        set_members = lib.get_container_members(container)
        container_root = lib.get_container_transforms(container,
                                                      members=set_members,
                                                      root=True)
        scene_nodes = cmds.ls(set_members, type="pgYetiMaya", long=True)

        # Build lookup with cbId as keys
        scene_lookup = defaultdict(list)
        for node in scene_nodes:
            cb_id = lib.get_id(node)
            scene_lookup[cb_id].append(node)

        # Re-assemble metadata with cbId as keys
        meta_data_lookup = {n["cbId"]: n for n in settings["nodes"]}

        # Delete nodes by "cbId" that are not in the updated version
        to_delete_lookup = {cb_id for cb_id in scene_lookup.keys() if
                            cb_id not in meta_data_lookup}
        if to_delete_lookup:

            # Get nodes and remove entry from lookup
            to_remove = []
            for _id in to_delete_lookup:
                # Get all related nodes
                shapes = scene_lookup[_id]
                # Get the parents of all shapes under the ID
                transforms = cmds.listRelatives(shapes,
                                                parent=True,
                                                fullPath=True) or []
                to_remove.extend(shapes + transforms)

                # Remove id from lookup
                scene_lookup.pop(_id, None)

            cmds.delete(to_remove)

        for cb_id, node_settings in meta_data_lookup.items():

            if cb_id not in scene_lookup:
                # Create new nodes
                self.log.info("Creating new nodes ..")

                new_nodes = self.create_node(namespace, node_settings)
                cmds.sets(new_nodes, addElement=container_node)
                cmds.parent(new_nodes, container_root)

            else:
                # Update the matching nodes
                scene_nodes = scene_lookup[cb_id]
                lookup_result = meta_data_lookup[cb_id]["name"]

                # Remove namespace if any (e.g.: "character_01_:head_YNShape")
                node_name = lookup_result.rsplit(":", 1)[-1]

                for scene_node in scene_nodes:

                    # Get transform node, this makes renaming easier
                    transforms = cmds.listRelatives(scene_node,
                                                    parent=True,
                                                    fullPath=True) or []
                    assert len(transforms) == 1, "This is a bug!"

                    # Get scene node's namespace and rename the transform node
                    lead = scene_node.rsplit(":", 1)[0]
                    namespace = ":{}".format(lead.rsplit("|")[-1])

                    new_shape_name = "{}:{}".format(namespace, node_name)
                    new_trans_name = new_shape_name.rsplit("Shape", 1)[0]

                    transform_node = transforms[0]
                    cmds.rename(transform_node,
                                new_trans_name,
                                ignoreShape=False)

                    # Get the newly named shape node
                    yeti_nodes = cmds.listRelatives(new_trans_name,
                                                    children=True)
                    yeti_node = yeti_nodes[0]

                    for attr, value in node_settings["attrs"].items():
                        if attr in SKIP_UPDATE_ATTRS:
                            self.log.info(
                                SKIP_ATTR_MESSAGE, yeti_node, attr, value
                            )
                            continue
                        set_attribute(attr, value, yeti_node)

                    # Set up user defined attributes
                    user_variables = node_settings.get("user_variables", {})
                    for attr, value in user_variables.items():
                        was_value_set = create_yeti_variable(
                            yeti_shape_node=yeti_node,
                            attr_name=attr,
                            value=value,
                            # We do not want to update the
                            # value if it already exists so
                            # that any local overrides that
                            # may have been applied still
                            # persist
                            force_value=False
                        )
                        if not was_value_set:
                            self.log.info(
                                SKIP_ATTR_MESSAGE, yeti_node, attr, value
                            )

        cmds.setAttr("{}.representation".format(container_node),
                     repre_entity["id"],
                     typ="string")

    def switch(self, container, context):
        self.update(container, context)

    # helper functions
    def create_namespace(self, folder_name):
        """Create a unique namespace
        Args:
            asset (dict): asset information

        """

        asset_name = "{}_".format(folder_name)
        prefix = "_" if asset_name[0].isdigit() else ""
        namespace = lib.unique_namespace(
            asset_name,
            prefix=prefix,
            suffix="_"
        )

        return namespace

    def get_cache_node_filepath(self, root, node_name):
        """Get the cache file path for one of the yeti nodes.

        All caches with more than 1 frame need cache file name set with `%04d`
        If the cache has only one frame we return the file name as we assume
        it is a snapshot.

        This expects the files to be named after the "node name" through
        exports with <Name> in Yeti.

        Args:
            root(str): Folder containing cache files to search in.
            node_name(str): Node name to search cache files for

        Returns:
            str: Cache file path value needed for cacheFileName attribute

        """

        name = node_name.replace(":", "_")
        pattern = r"^({name})(\.[0-9]+)?(\.fur)$".format(name=re.escape(name))

        files = [fname for fname in os.listdir(root) if re.match(pattern,
                                                                 fname)]
        if not files:
            self.log.error("Could not find cache files for '{}' "
                           "with pattern {}".format(node_name, pattern))
            return

        if len(files) == 1:
            # Single file
            return os.path.join(root, files[0])

        # Get filename for the sequence with padding
        collections, remainder = clique.assemble(files)
        assert not remainder, "This is a bug"
        assert len(collections) == 1, "This is a bug"
        collection = collections[0]

        # Formats name as {head}%d{tail} like cache.%04d.fur
        fname = collection.format("{head}{padding}{tail}")
        return os.path.join(root, fname)

    def create_node(self, namespace, node_settings):
        """Create nodes with the correct namespace and settings

        Args:
            namespace(str): namespace
            node_settings(dict): Single "nodes" entry from .fursettings file.

        Returns:
             list: Created nodes

        """
        nodes = []

        # Get original names and ids
        orig_transform_name = node_settings["transform"]["name"]
        orig_shape_name = node_settings["name"]

        # Add namespace
        transform_name = "{}:{}".format(namespace, orig_transform_name)
        shape_name = "{}:{}".format(namespace, orig_shape_name)

        # Create pgYetiMaya node
        transform_node = cmds.createNode("transform",
                                         name=transform_name)
        yeti_node = cmds.createNode("pgYetiMaya",
                                    name=shape_name,
                                    parent=transform_node)

        lib.set_id(transform_node, node_settings["transform"]["cbId"])
        lib.set_id(yeti_node, node_settings["cbId"])

        nodes.extend([transform_node, yeti_node])

        # Update attributes with defaults
        attributes = node_settings["attrs"]
        attributes.update({
            "verbosity": 2,
            "fileMode": 1,

            # Fix render stats, like Yeti's own
            # ../scripts/pgYetiNode.mel script
            "visibleInReflections": True,
            "visibleInRefractions": True
        })

        if "viewportDensity" not in attributes:
            attributes["viewportDensity"] = 0.1

        # Apply attributes to pgYetiMaya node
        for attr, value in attributes.items():
            set_attribute(attr, value, yeti_node)

        # Set up user defined attributes
        user_variables = node_settings.get("user_variables", {})
        for attr, value in user_variables.items():
            create_yeti_variable(yeti_shape_node=yeti_node,
                                 attr_name=attr,
                                 value=value)

        # Connect to the time node
        cmds.connectAttr("time1.outTime", "%s.currentTime" % yeti_node)

        return nodes

    def read_settings(self, path):
        """Read .fursettings file and compute some additional attributes"""

        with open(path, "r") as fp:
            fur_settings = json.load(fp)

        if "nodes" not in fur_settings:
            raise RuntimeError("Encountered invalid data, "
                               "expected 'nodes' in fursettings.")

        # Compute the cache file name values we want to set for the nodes
        root = os.path.dirname(path)
        for node in fur_settings["nodes"]:
            cache_filename = self.get_cache_node_filepath(
                root=root, node_name=node["name"])

            attrs = node.get("attrs", {})       # allow 'attrs' to not exist
            attrs["cacheFileName"] = cache_filename
            node["attrs"] = attrs

        return fur_settings
