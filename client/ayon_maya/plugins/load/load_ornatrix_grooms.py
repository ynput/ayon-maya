import os
import json
from typing import Any, Dict, List

from ayon_core.settings import get_project_settings
from ayon_maya.api import lib, plugin
from ayon_maya.api.pipeline import containerise
from ayon_maya.api.plugin import get_load_color_for_product_type
from maya import cmds


def get_node_name(path: str) -> str:
    """Return maya node name without namespace or parents

    Examples:
        >>> get_node_name("|grp|node")
        "node"
        >>> get_node_name("|foobar:grp|foobar:child")
        "child"
        >>> get_node_name("|foobar:grp|lala:bar|foobar:test:hello_world")
        "hello_world"
    """
    return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]


class OxOrnatrixGrooms(plugin.Loader):
    """Load Ornatrix Grooms"""

    product_types = {"oxrig"}
    representations = {"oxg.zip"}

    label = "Load Ornatrix Grooms"
    order = -9
    icon = "code-fork"

    def load(self, context, name=None, namespace=None, data=None):
        cmds.loadPlugin("Ornatrix", quiet=True)

        # Build namespace
        folder_name = context["folder"]["name"]
        if namespace is None:
            namespace = self.create_namespace(folder_name)

        path = self.filepath_from_context(context)
        path = path.replace("\\", "/")

        # prevent loading the presets with the selected meshes
        cmds.select(deselect=True)
        hair_shape = cmds.OxLoadGroom(path=path)

        # Add the root to the group
        parents = list(lib.iter_parents(cmds.ls(hair_shape, long=True)[0]))
        root = parents[-1]
        group_name = "{}:{}".format(namespace, name)
        group_node = cmds.group(root,
                                name=group_name)

        project_name = context["project"]["name"]

        # The load may generate a shape node which is not returned by the
        # `OxLoadGroom` command so we find it. It's usually the parent.
        # And we rename the loaded mesh transform.
        hair_transform = lib.get_node_parent(hair_shape)
        mesh_transform = lib.get_node_parent(hair_transform)
        if mesh_transform:
            meshes = cmds.listRelatives(mesh_transform,
                                        type="mesh",
                                        fullPath=True)
            if meshes:
                self.rename_mesh(meshes, context, namespace)

        product_type = context["product"]["productType"]
        settings = get_project_settings(project_name)
        color = get_load_color_for_product_type(product_type, settings)
        if color is not None:
            red, green, blue = color
            cmds.setAttr(group_node + ".useOutlinerColor", 1)
            cmds.setAttr(group_node + ".outlinerColor", red, green, blue)

        nodes = cmds.ls(group_node, long=True, dag=True)
        self[:] = nodes

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__
        )

    def rename_mesh(self, nodes, context, namespace):
        """Rename mesh based on node name in rigsettings file."""

        # Get .cachesettings file
        path = self.filepath_from_context(context)
        if path.endswith(".oxg.zip"):
            base = path[:-len(".oxg.zip")]  # strip off multi-dot ext
        else:
            base = os.path.splitext(path)[0]
        rigsettings_path = base + ".rigsettings"
        with open(rigsettings_path, "r") as f:
            rigsettings: List[Dict[str, Any]] = json.load(f)

        # Assume only ever one node, get its nice name
        name = get_node_name(rigsettings[0]["node"])

        for mesh in cmds.ls(nodes, type="mesh"):
            transform = cmds.listRelatives(mesh, parent=True, fullPath=True)[0]
            cmds.rename(transform, f"{namespace}:{name}")

    def remove(self, container):
        self.log.info("Removing '%s' from Maya.." % container["name"])

        nodes = lib.get_container_members(container)
        cmds.delete(nodes)

        namespace = container["namespace"]
        cmds.namespace(removeNamespace=namespace, deleteNamespaceContent=True)

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
