from maya import cmds

from ayon_core.settings import get_project_settings
from ayon_core.pipeline import get_representation_path
from ayon_maya.api import plugin
from ayon_maya.api.pipeline import containerise
from ayon_maya.api.lib import maintained_selection, unique_namespace
from ayon_maya.api.plugin import get_load_color_for_product_type
from ayon_core.lib import EnumDef


class OxAlembicLoader(plugin.Loader):
    """Ornatrix Alembic Loader"""

    product_types = {"oxcache"}
    representations = {"abc"}

    label = "Ornatrix Alembic Loader"
    order = -10
    icon = "code-fork"
    color = "orange"

    @classmethod
    def get_options(cls, contexts):
        return [
            EnumDef(
                "import_options",
            label="Import Options for Ornatrix Cache",
            items={
                0: "Hair",
                1: "Guide"
            },
            default=0,
        )
    ]

    def load(self, context, name, namespace, options):
        cmds.loadPlugin("Ornatrix", quiet=True)
        # Build namespace
        folder_name = context["folder"]["name"]
        if namespace is None:
            namespace = self.create_namespace(folder_name)

        path = self.filepath_from_context(context)
        path = path.replace("\\", "/")

        ox_import_options = "; importAs={}".format(
            options.get("import_options"))
        group_name = "{}:{}".format(namespace, name)
        project_name = context["project"]["name"]

        new_nodes = []
        with maintained_selection():
            nodes = cmds.file(
                path,
                i=True,
                type="Ornatrix Alembic Import",
                namespace=namespace,
                returnNewNodes=True,
                groupName=group_name,
                options=ox_import_options
            )
            nodes = cmds.ls(nodes)
            shapes = cmds.ls(nodes, shapes=True)
            ox_node = cmds.ls(nodes, type="BakedHairNode")
            new_nodes = (list(set(nodes) - set(shapes)- set(ox_node)))
        group_node = cmds.group(new_nodes, name=group_name)

        settings = get_project_settings(project_name)
        product_type = context["product"]["productType"]
        color = get_load_color_for_product_type(product_type, settings)
        if color is not None:
            red, green, blue = color
            cmds.setAttr(group_node + ".useOutlinerColor", 1)
            cmds.setAttr(group_node + ".outlinerColor", red, green, blue)

        new_nodes.append(group_node)

        self[:] = new_nodes

        return containerise(
            name=name,
            namespace=namespace,
            nodes=new_nodes,
            context=context,
            loader=self.__class__.__name__
        )


    def update(self, container, context):
        path = self.filepath_from_context(context)
        members = cmds.sets(container['objectName'], query=True)
        ox_nodes = cmds.ls(members, type="BakedHairNode", long=True)
        for node in ox_nodes:
            cmds.setAttr(f"{node}.sourceFilePath1", path, type="string")

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):

        namespace = container["namespace"]
        nodes = container["nodes"]

        self.log.info("Removing '%s' from Maya.." % container["name"])

        nodes = cmds.ls(nodes, long=True)
        cmds.delete(nodes)

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
        namespace = unique_namespace(
            asset_name,
            prefix=prefix,
            suffix="_"
        )

        return namespace
