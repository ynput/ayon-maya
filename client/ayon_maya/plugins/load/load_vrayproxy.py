# -*- coding: utf-8 -*-
"""Loader for Vray Proxy files.

If there are Alembics published along vray proxy (in the same version),
loader will use them instead of native vray vrmesh format.

"""
import os

import ayon_api
import maya.cmds as cmds
from ayon_core.pipeline import get_representation_path
from ayon_core.settings import get_project_settings
from ayon_maya.api.lib import maintained_selection, namespaced, unique_namespace
from ayon_maya.api.pipeline import containerise
from ayon_maya.api import plugin
from ayon_maya.api.plugin import get_load_color_for_product_type


class VRayProxyLoader(plugin.Loader):
    """Load VRay Proxy with Alembic or VrayMesh."""

    product_types = {"vrayproxy", "model", "pointcache", "animation", "oxcache"}
    representations = {"vrmesh", "abc"}

    label = "Import VRay Proxy"
    order = -10
    icon = "code-fork"
    color = "orange"

    def load(self, context, name=None, namespace=None, options=None):
        # type: (dict, str, str, dict) -> None
        """Loader entry point.

        Args:
            context (dict): Loaded representation context.
            name (str): Name of container.
            namespace (str): Optional namespace name.
            options (dict): Optional loader options.

        """

        product_type = context["product"]["productType"]

        #  get all representations for this version
        filename = self._get_abc(
            context["project"]["name"], context["version"]["id"]
        )
        if not filename:
            filename = self.filepath_from_context(context)

        folder_name = context["folder"]["name"]
        namespace = namespace or unique_namespace(
            folder_name + "_",
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="_",
        )

        # Ensure V-Ray for Maya is loaded.
        cmds.loadPlugin("vrayformaya", quiet=True)

        with maintained_selection():
            cmds.namespace(addNamespace=namespace)
            with namespaced(namespace, new=False):
                nodes, group_node = self.create_vray_proxy(
                    name, filename=filename)

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
        # type: (dict, dict) -> None
        """Update container with specified representation."""
        node = container['objectName']
        assert cmds.objExists(node), "Missing container"

        members = cmds.sets(node, query=True) or []
        vraymeshes = cmds.ls(members, type="VRayProxy")
        assert vraymeshes, "Cannot find VRayMesh in container"

        #  get all representations for this version
        repre_entity = context["representation"]
        filename = self._get_abc(
            context["project"]["name"], context["version"]["id"]
        )
        if not filename:
            filename = get_representation_path(repre_entity)

        for vray_mesh in vraymeshes:
            cmds.setAttr("{}.fileName".format(vray_mesh),
                         filename,
                         type="string")

        # Update metadata
        cmds.setAttr("{}.representation".format(node),
                     repre_entity["id"],
                     type="string")

    def remove(self, container):
        # type: (dict) -> None
        """Remove loaded container."""
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
        # type: (dict, dict) -> None
        """Switch loaded representation."""
        self.update(container, context)

    def create_vray_proxy(self, name, filename):
        # type: (str, str) -> (list, str)
        """Re-create the structure created by VRay to support vrmeshes

        Args:
            name (str): Name of the asset.
            filename (str): File name of vrmesh.

        Returns:
            nodes(list)

        """

        if name is None:
            name = os.path.splitext(os.path.basename(filename))[0]

        parent = cmds.createNode("transform", name=name)
        proxy = cmds.createNode(
            "VRayProxy", name="{}Shape".format(name), parent=parent)
        cmds.setAttr(proxy + ".fileName", filename, type="string")
        cmds.connectAttr("time1.outTime", proxy + ".currentFrame")

        return [parent, proxy], parent

    def _get_abc(self, project_name, version_id):
        # type: (str) -> str
        """Get abc representation file path if present.

        If here is published Alembic (abc) representation published along
        vray proxy, get is file path.

        Args:
            project_name (str): Project name.
            version_id (str): Version hash id.

        Returns:
            str: Path to file.
            None: If abc not found.

        """
        self.log.debug(
            "Looking for abc in published representations of this version.")
        abc_rep = ayon_api.get_representation_by_name(
            project_name, "abc", version_id
        )
        if abc_rep:
            self.log.debug("Found, we'll link alembic to vray proxy.")
            file_name = get_representation_path(abc_rep)
            self.log.debug("File: {}".format(file_name))
            return file_name

        return ""
