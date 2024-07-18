import os
from typing import List, Dict, Any
import pyblish.api
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

        # Use `set` to avoid duplicate resource data
        ornatrix_resources = []
        for node in set(ornatrix_nodes):
            # Get Yeti resources (textures)
            resources = self.get_texture_resources(node)
            ornatrix_resources.extend(resources)

        instance.data["resources"] = ornatrix_resources
        self.log.debug("Collected Ornatrix resources: "
                       "{}".format(instance.data["resources"]))

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
                self.log.warning(f"No texture found for: {texture}")
                continue

            item = {
                "node": node,
                "files": files,
                "source": texture,
                "texture_attribute": texture_attr
            }

            resources.append(item)

        return resources
