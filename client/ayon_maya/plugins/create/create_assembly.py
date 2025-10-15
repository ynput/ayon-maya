from ayon_maya.api import plugin


class CreateAssembly(plugin.MayaCreator):
    """A grouped package of loaded content"""

    identifier = "io.openpype.creators.maya.assembly"
    label = "Assembly"
    # product_type to be defined in the project settings
    # use product_base_type instead
    # see https://github.com/ynput/ayon-core/issues/1297
    product_base_type = product_type = "assembly"
    icon = "cubes"
