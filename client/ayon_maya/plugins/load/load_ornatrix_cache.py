import json
import os
from ayon_maya.api import lib
from ayon_maya.api.pipeline import containerise
from ayon_maya.api import plugin
from maya import cmds


class OxCacheLoader(plugin.Loader):
    """Load Ornatrix Cache with one or more Ornatrix nodes"""

    product_types = {"oxcache", "oxrig"}
    representations = {"abc"}

    label = "Load Ornatrix Cache with Hair Guide"
    order = -9
    icon = "code-fork"
    color = "orange"

    def load(self, context, name=None, namespace=None, data=None):
        """Loads a .cachesettings file defining how to load .abc into
        HairGuideFromMesh nodes

        The .cachesettings file defines what the node names should be and also
        what "cbId" attribute they should receive to match the original source
        and allow published looks to also work for Ornatrix rigs and its caches.

        """
        # Ensure Ornatrix is loaded
        cmds.loadPlugin("Ornatrix", quiet=True)

        # Build namespace
        folder_name = context["folder"]["name"]
        if namespace is None:
            namespace = self.create_namespace(folder_name)

        path = self.filepath_from_context(context)
        settings = self.read_settings(path)
        nodes = []
        for setting in settings["nodes"]:
            nodes.extend(self.create_node(namespace, path, setting))

        # Select the node and show dialog so the user can directly
        # start working with the newly created nodes.
        cmds.select(nodes)
        cmds.OxShowHairStackDialog()

        self[:] = nodes

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__
        )

    def remove(self, container):
        self.log.info("Removing '%s' from Maya.." % container["name"])

        nodes = lib.get_container_members(container)
        cmds.delete(nodes)

        namespace = container["namespace"]
        cmds.namespace(removeNamespace=namespace, deleteNamespaceContent=True)

    def update(self, container, context):
        path = self.filepath_from_context(context)
        nodes = lib.get_container_members(container)
        for node in cmds.ls(nodes, type="HairFromGuidesNode"):
            cmds.setAttr(f"{node}.cacheFilePath", path, type="string")

        # Update the representation
        cmds.setAttr(
            container["objectName"] + ".representation",
            context["representation"]["id"],
            type="string"
        )

    def switch(self, container, context):
        self.update(container, context)

    # helper functions
    def create_namespace(self, folder_name):
        """Create a unique namespace
        Args:
            folder_name (str): Folder name

        Returns:
            str: The unique namespace for the folder.
        """

        asset_name = "{}_".format(folder_name)
        prefix = "_" if asset_name[0].isdigit() else ""
        namespace = lib.unique_namespace(
            asset_name,
            prefix=prefix,
            suffix="_"
        )

        return namespace

    def create_node(self, namespace, filepath, node_settings):
        """Use the cachesettings to create a shape node which
        connects to HairFromGuidesNode with abc file cache.

        Args:
            namespace (str): namespace
            filepath (str): filepath
            node_settings (dict): node settings

        Returns:
            list: loaded nodes
        """
        orig_guide_name = node_settings["name"]
        guide_name = "{}:{}".format(namespace, orig_guide_name)
        hair_guide_node = cmds.createNode("HairFromGuidesNode",
                                          name=guide_name, skipSelect=True)
        lib.set_id(hair_guide_node, node_settings.get("cbId", ""))
        cmds.setAttr(f"{hair_guide_node}.cacheFilePath",
                     filepath, type="string")

        return [hair_guide_node]

    def read_settings(self, path):
        """Read the ornatrix-related parameters from the cachesettings.
        Args:
            path (str): filepath of cachesettings

        Returns:
            dict: setting attributes
        """
        path_no_ext, _ = os.path.splitext(path)
        settings_path = f"{path_no_ext}.cachesettings"
        with open(settings_path, "r") as fp:
            setting_attributes = json.load(fp)

        return setting_attributes
