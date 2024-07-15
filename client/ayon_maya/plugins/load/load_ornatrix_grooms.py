from ayon_core.settings import get_project_settings
from ayon_maya.api import lib
from ayon_maya.api.pipeline import containerise
from ayon_maya.api import plugin
from ayon_maya.api.plugin import get_load_color_for_product_type
from maya import cmds, mel


class OxOrnatrixGrooms(plugin.Loader):
    """Load Ornatrix Grooms"""

    product_types = {"oxrig"}
    representations = {"oxg.zip"}

    label = "Load Ornatrix Grooms"
    order = -9
    icon = "code-fork"

    def load(self, context, name=None, namespace=None, data=None):
        cmds.loadPlugin("Ornatrix", quiet=True)

        # prevent loading the presets with the selected meshes
        cmds.select(deselect=True)

        product_type = context["product"]["productType"]
        # Build namespace
        folder_name = context["folder"]["name"]
        if namespace is None:
            namespace = self.create_namespace(folder_name)

        path = self.filepath_from_context(context)
        path = path.replace("\\", "/")

        nodes = [mel.eval(f'OxLoadGroom -path "{path}";')]

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
