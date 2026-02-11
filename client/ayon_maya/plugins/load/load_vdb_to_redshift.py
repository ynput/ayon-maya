import os
from typing import List

from ayon_core.settings import get_project_settings
from ayon_core.lib import BoolDef

from ayon_maya.api import plugin, lib
from ayon_maya.api.plugin import get_load_color_for_product_type
from ayon_maya.api.pipeline import containerise

from maya import cmds, mel


class LoadVDBtoRedShift(plugin.Loader):
    """Load OpenVDB in a Redshift Volume Shape

    Note that the RedshiftVolumeShape is created without a RedshiftVolume
    shader assigned. To get the Redshift volume to render correctly assign
    a RedshiftVolume shader (in the Hypershade) and set the density, scatter
    and emission channels to the channel names of the volumes in the VDB file.

    """

    product_base_types = {"vdbcache"}
    product_types = product_base_types
    representations = {"vdb"}

    label = "Load VDB to RedShift"
    icon = "cloud"
    color = "orange"

    options = [
        BoolDef("create_shader",
                label="Create Redshift Volume Shader",
                tooltip="When enabled create a Redshift Volume Shader and "
                        "assign it to the volume shape. Without a volume "
                        "shader assigned Redshift may not render the volume "
                        "at all.",
                default=True)
    ]

    def load(self, context, name=None, namespace=None, options=None):

        product_type = context["product"]["productType"]

        # Check if the plugin for redshift is available on the pc
        try:
            cmds.loadPlugin("redshift4maya", quiet=True)
        except Exception as exc:
            self.log.error("Encountered exception:\n%s" % exc)
            return

        # Check if viewport drawing engine is Open GL Core (compat)
        render_engine = None
        compatible = "OpenGL"
        if cmds.optionVar(exists="vp2RenderingEngine"):
            render_engine = cmds.optionVar(query="vp2RenderingEngine")

        if not render_engine or not render_engine.startswith(compatible):
            raise RuntimeError("Current scene's settings are incompatible."
                               "See Preferences > Display > Viewport 2.0 to "
                               "set the render engine to '%s<type>'"
                               % compatible)

        folder_name = context["folder"]["name"]
        namespace = namespace or lib.unique_namespace(
            folder_name + "_",
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="_",
        )

        # Root group
        label = "{}:{}".format(namespace, name)
        root = cmds.createNode("transform", name=label)

        project_name = context["project"]["name"]
        settings = get_project_settings(project_name)
        color = get_load_color_for_product_type(product_type, settings)
        if color is not None:
            red, green, blue = color
            cmds.setAttr(root + ".useOutlinerColor", 1)
            cmds.setAttr(root + ".outlinerColor", red, green, blue)

        # Create VR
        volume_node = cmds.createNode("RedshiftVolumeShape",
                                      name="{}RVSShape".format(label),
                                      parent=root)

        self._set_path(volume_node,
                       path=self.filepath_from_context(context),
                       representation=context["representation"])

        if options.get("create_shader", True):
            self._create_default_redshift_volume_shader(volume_node)

        nodes = [root, volume_node]
        self[:] = nodes

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__)

    def update(self, container, context):

        repre_entity = context["representation"]
        path = self.filepath_from_context(context)

        # Find VRayVolumeGrid
        members = cmds.sets(container['objectName'], query=True)
        grid_nodes = cmds.ls(members, type="RedshiftVolumeShape", long=True)
        assert len(grid_nodes) == 1, "This is a bug"

        # Update the VRayVolumeGrid
        self._set_path(grid_nodes[0], path=path, representation=repre_entity)

        # Update container representation
        cmds.setAttr(container["objectName"] + ".representation",
                     repre_entity["id"],
                     type="string")

    def remove(self, container):

        # Get all members of the AYON container, ensure they are unlocked
        # and delete everything
        members = cmds.sets(container['objectName'], query=True)
        cmds.lockNode(members, lock=False)
        cmds.delete([container['objectName']] + members)

        # Clean up the namespace
        try:
            cmds.namespace(removeNamespace=container['namespace'],
                           deleteNamespaceContent=True)
        except RuntimeError:
            pass

    def switch(self, container, context):
        self.update(container, context)

    @staticmethod
    def _set_path(grid_node,
                  path,
                  representation):
        """Apply the settings for the VDB path to the RedshiftVolumeShape"""

        if not os.path.exists(path):
            raise RuntimeError("Path does not exist: %s" % path)

        is_sequence = "frame" in representation["context"]
        cmds.setAttr(grid_node + ".useFrameExtension", is_sequence)

        # Set file path
        cmds.setAttr(grid_node + ".fileName", path, type="string")

        # Force refresh with the use frame extension
        # This makes sure we can directly retrieve the `.gridNames` attribute
        # and avoids potential 'Failed to find volume file' warnings that
        # appear once on load when Maya has not yet initialized use frame
        # extension behavior correctly on load yet.
        mel.eval(f'checkUseFrameExtension("{grid_node}")')

    def _create_default_redshift_volume_shader(
            self, volume_shape: str) -> List[str]:
        """Create RedshiftStandardVolume shader and assign it to the volume"""
        # TODO: Should this material become "managed" and get removed on
        #  removing the Redshift Volume itself? Currently it is not and it
        #  will linger in the scene as dangling unused material.

        # Create shading engine with RedshiftStandardVolume
        material = cmds.shadingNode("RedshiftStandardVolume", asShader=True)
        sg = cmds.shadingNode(
            "shadingEngine", asShader=True, name=f"{material}SG")
        cmds.connectAttr(f"{material}.outColor",
                         f"{sg}.volumeShader",
                         force=True)

        # Set default density name
        channel = "density"
        grid_names: List[str] = cmds.getAttr(f"{volume_shape}.gridNames")
        if grid_names and channel not in grid_names:
            channel = grid_names[0]
        cmds.setAttr("{}.density_name".format(material),
                     channel, type="string")

        # Assign shader to the volume shape
        cmds.sets(volume_shape, forceElement=sg)

        self.log.info(
            f"Created RedshiftStandardVolume: '{material}'"
            f" using channel '{channel}'")
        return [material, sg]
