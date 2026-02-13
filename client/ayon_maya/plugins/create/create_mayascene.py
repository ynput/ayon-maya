from ayon_maya.api import plugin


class CreateMayaScene(plugin.MayaCreator):
    """Raw Maya Scene file export"""

    identifier = "io.openpype.creators.maya.mayascene"
    name = "mayaScene"
    label = "Maya Scene"
    product_base_type = "mayascene"
    product_type = product_base_type
    icon = "file-archive-o"
