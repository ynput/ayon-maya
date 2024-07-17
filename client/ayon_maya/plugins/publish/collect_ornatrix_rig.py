import os
from typing import List, Dict, Any
import pyblish.api
from ayon_core.pipeline.publish import KnownPublishError
from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds


ORNATRIX_NODES = {
    "HairFromGuidesNode", "GuidesFromMeshNode",
    "MeshFromStrandsNode", "SurfaceCombNode"
}


class CollectOxRig(plugin.MayaInstancePlugin):
    """Collect all information of the Ornatrix Rig"""

    order = pyblish.api.CollectorOrder + 0.4
    label = "Collect Ornatrix Rig"
    families = ["oxrig"]

    def process(self, instance):
        ornatrix_nodes = cmds.ls(instance.data["setMembers"], long=True)
        self.log.debug(f"Getting ornatrix nodes: {ornatrix_nodes}")

        ornatrix_resources = []
        ornatrix_nodes_list = []

        # Use `set` to avoid duplicate resource data
        for node in set(ornatrix_nodes):
            # Get Yeti resources (textures)
            resources = self.get_texture_resources(node)
            ornatrix_resources.extend(resources)

        instance.data["resources"] = ornatrix_resources
        self.log.debug(instance.data["resources"])
        for node in ornatrix_nodes:
            ox_node_list = self.get_ox_nodes(node)
            ornatrix_nodes_list.extend(ox_node_list)

        instance.data["ornatrix_nodes"] = ornatrix_nodes_list
        self.log.debug(instance.data["ornatrix_nodes"])

    def get_ox_nodes(self, node: str) -> List[str]:
        all_ox_nodes = []
        node_shape = cmds.listRelatives(node, shapes=True)
        if not node_shape:
            return []

        ox_nodes = cmds.ls(
            cmds.listConnections(node_shape, destination=True) or [],
            type=ORNATRIX_NODES)
        if ox_nodes:
            all_ox_nodes.append(node)
        return all_ox_nodes

    def get_texture_resources(self, node: str) -> List[Dict[str, Any]]:
        resources = []
        node_shape = cmds.listRelatives(node, shapes=True)
        if not node_shape:
            return []

        ox_nodes = cmds.ls(
            cmds.listConnections(node_shape, destination=True) or [],
            type=ORNATRIX_NODES)

        ox_file_nodes = cmds.listConnections(ox_nodes,
                                             destination=False,
                                             type="file") or []
        if not ox_file_nodes:
            return []
        for file_node in ox_file_nodes:
            texture_attr = "{}.fileTextureName".format(file_node)
            texture = cmds.getAttr("{}.fileTextureName".format(file_node))
            files = []
            if os.path.isabs(texture):
                self.log.debug("Texture is absolute path, ignoring "
                               "image search paths for: %s" % texture)
                files = lib.search_textures(texture)
            else:
                root = cmds.workspace(query=True, rootDirectory=True)
                filepath = os.path.join(root, texture)
                files = lib.search_textures(filepath)
                if files:
                    continue

            if not files:
                raise KnownPublishError(
                    f"No texture found for: {texture}")

            item = {
                "node": node,
                "files": files,
                "source": texture,
                "texture_attribute": texture_attr
            }

            resources.append(item)

        return resources
