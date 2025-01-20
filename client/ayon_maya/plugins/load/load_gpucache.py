import maya.cmds as cmds
from ayon_core.settings import get_project_settings
from ayon_maya.api.pipeline import imprint_container
from ayon_maya.api import plugin
from ayon_maya.api.plugin import get_load_color_for_product_type


class GpuCacheLoader(plugin.Loader):
    """Load Alembic as gpuCache"""

    product_types = {"model", "animation", "proxyAbc", "pointcache"}
    representations = {"abc", "gpu_cache"}

    label = "Load Gpu Cache"
    order = -5
    icon = "code-fork"
    color = "orange"

    def load(self, context, name, namespace, data):
        folder_name = context["folder"]["name"]

        cmds.loadPlugin("gpuCache", quiet=True)

        # Create GPU cache
        label = "{}_{}".format(folder_name, name)
        transform_name = label + "_#"
        transform = cmds.createNode("transform", name=transform_name)
        cache = cmds.createNode("gpuCache",
                                parent=transform,
                                name="{0}Shape".format(transform_name))

        # Colorize root transform
        project_name = context["project"]["name"]
        settings = get_project_settings(project_name)
        color = get_load_color_for_product_type("model", settings)
        if color is not None:
            red, green, blue = color
            cmds.setAttr(transform + ".useOutlinerColor", 1)
            cmds.setAttr(
                transform + ".outlinerColor", red, green, blue
            )

        # Set the cache filepath
        path = self.filepath_from_context(context)
        cmds.setAttr(cache + '.cacheFileName', path, type="string")
        cmds.setAttr(cache + '.cacheGeomPath', "|", type="string")    # root

        imprint_container(
            cache,
            name=name,
            namespace=namespace,
            context=context,
            loader=self.__class__.__name__,
            prefix="AYON_")

        return cache

    def update(self, container, context):
        cache = container["objectName"]

        # Update the cache
        path = self.filepath_from_context(context)
        cmds.setAttr(cache + ".cacheFileName", path, type="string")

        # Update representation id
        cmds.setAttr(cache + ".AYON_representation",
                     context["representation"]["id"],
                     type="string")

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        # Remove shape and parent transforms
        # If the shape was instanced, remove each transform
        cache = container['objectName']
        paths = cmds.ls(cache, allPaths=True, long=True)
        transforms = cmds.listRelatives(paths, parent=True, fullPath=True)

        members = transforms + [cache]
        cmds.delete(members)