# -*- coding: utf-8 -*-
"""Loader for Redshift proxy."""
import os

import clique
import maya.cmds as cmds
from ayon_core.pipeline import get_representation_path
from ayon_core.settings import get_project_settings
from ayon_maya.api import plugin
from ayon_maya.api.lib import maintained_selection, namespaced, unique_namespace
from ayon_maya.api.pipeline import containerise
from ayon_maya.api.plugin import get_load_color_for_product_type


class RedshiftProxyLoader(plugin.Loader):
    """Load Redshift proxy"""

    product_types = {"*"}
    representations = {"*"}
    extensions = {"rs", "usd", "usda", "usdc", "abc"}

    label = "Import Redshift Proxy"
    order = -10
    icon = "code-fork"
    color = "orange"

    def load(self, context, name=None, namespace=None, options=None):
        """Plugin entry point."""
        product_type = context["product"]["productType"]

        folder_name = context["folder"]["name"]
        namespace = namespace or unique_namespace(
            folder_name + "_",
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="_",
        )

        # Ensure Redshift for Maya is loaded.
        cmds.loadPlugin("redshift4maya", quiet=True)

        path = self.filepath_from_context(context)
        with maintained_selection():
            cmds.namespace(addNamespace=namespace)
            with namespaced(namespace, new=False):
                nodes, group_node = self.create_rs_proxy(name, path)

        proxy = nodes[0]  # RedshiftProxyMesh
        self._set_rs_proxy_file_type(proxy, path)

        self[:] = nodes
        if not nodes:
            return

        # colour the group node
        project_name = context["project"]["name"]
        settings = get_project_settings(project_name)
        color = get_load_color_for_product_type(product_type, settings)
        if color is not None:
            red, green, blue = color
            cmds.setAttr("{0}.useOutlinerColor".format(group_node), 1)
            cmds.setAttr(
                "{0}.outlinerColor".format(group_node), red, green, blue
            )

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__)

    def update(self, container, context):

        node = container['objectName']
        assert cmds.objExists(node), "Missing container"

        members = cmds.sets(node, query=True) or []
        rs_meshes = cmds.ls(members, type="RedshiftProxyMesh")
        assert rs_meshes, "Cannot find RedshiftProxyMesh in container"
        repre_entity = context["representation"]
        filename = get_representation_path(repre_entity)

        for rs_mesh in rs_meshes:
            cmds.setAttr("{}.fileName".format(rs_mesh),
                         filename,
                         type="string")
            self._set_rs_proxy_file_type(rs_mesh, filename)

        # Update metadata
        cmds.setAttr("{}.representation".format(node),
                     repre_entity["id"],
                     type="string")

    def remove(self, container):

        # Delete container and its contents
        if cmds.objExists(container['objectName']):
            members = cmds.sets(container['objectName'], query=True) or []
            cmds.delete([container['objectName']] + members)

        # Remove the namespace, if empty
        namespace = container['namespace']
        if cmds.namespace(exists=namespace):
            members = cmds.namespaceInfo(namespace, listNamespace=True)
            if not members:
                cmds.namespace(removeNamespace=namespace)
            else:
                self.log.warning("Namespace not deleted because it "
                                 "still has members: %s", namespace)

    def switch(self, container, context):
        self.update(container, context)

    def create_rs_proxy(self, name, path):
        """Creates Redshift Proxies showing a proxy object.

        Args:
            name (str): Proxy name.
            path (str): Path to proxy file.

        Returns:
            (str, str): Name of mesh with Redshift proxy and its parent
                transform.

        """
        rs_mesh = cmds.createNode(
            'RedshiftProxyMesh', name="{}_RS".format(name))
        mesh_shape = cmds.createNode("mesh", name="{}_GEOShape".format(name))

        cmds.setAttr("{}.fileName".format(rs_mesh),
                     path,
                     type="string")

        cmds.connectAttr("{}.outMesh".format(rs_mesh),
                         "{}.inMesh".format(mesh_shape))

        # TODO: use the assigned shading group as shaders if existed
        # assign default shader to redshift proxy
        if cmds.ls("initialShadingGroup", type="shadingEngine"):
            cmds.sets(mesh_shape, forceElement="initialShadingGroup")

        group_node = cmds.group(empty=True, name="{}_GRP".format(name))
        mesh_transform = cmds.listRelatives(mesh_shape,
                                            parent=True, fullPath=True)
        cmds.parent(mesh_transform, group_node)
        nodes = [rs_mesh, mesh_shape, group_node]

        # determine if we need to enable animation support
        files_in_folder = os.listdir(os.path.dirname(path))
        collections, remainder = clique.assemble(files_in_folder)

        if collections:
            cmds.setAttr("{}.useFrameExtension".format(rs_mesh), 1)

        return nodes, group_node

    def _set_rs_proxy_file_type(self, proxy: str, path: str):
        """Set Redshift Proxy file type attribute based on input file."""

        extension = os.path.splitext(path)[1].lower()
        file_type = {
            ".rs": 0,
            ".usd": 1,
            ".abc": 2
        }.get(extension, None)

        # If file type is not recognized, log a warning
        if file_type is None:
            self.log.warning("Unknown file type: %s. "
                             "File Type may be set incorrectly", extension)
            return

        # If this redshift release (prior to 2025.4.0+) does not have the
        # `proxyFileType` attribute and the file type is not 0 (rsproxy), then
        # log a warning
        if not cmds.attributeQuery("proxyFileType", node=proxy, exists=True):
            if file_type != 0:
                self.log.warning(
                    "Redshift Proxy file type attribute not found. File Type"
                    " may be set incorrectly. You may need a newer Redshift"
                    " release (2025.4.0+) to support USD and Alembic in"
                    " Redshift Proxies. ")
            return

        cmds.setAttr(proxy + ".proxyFileType", file_type)

    @classmethod
    def get_representation_name_aliases(cls, representation_name):
        # Allow switching between the different supported representations
        # automatically if a newer version does not have the currently used
        # representation
        return ["rs", "usd", "abc"]
