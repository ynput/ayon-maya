from ayon_maya.api import (
    lib,
    plugin
)
from ayon_core.lib import BoolDef


class CreateCamera(plugin.MayaCreator):
    """Single baked camera"""

    identifier = "io.openpype.creators.maya.camera"
    label = "Camera"
    product_type = "camera"
    icon = "video-camera"

    def get_instance_attr_defs(self):

        defs = lib.collect_animation_defs(create_context=self.create_context)

        defs.extend([
            BoolDef("bakeToWorldSpace",
                    label="Bake to World-Space",
                    tooltip="Bake to World-Space",
                    default=True),
        ])

        return defs


class CreateCameraRig(plugin.MayaCreator):
    """Complex hierarchy with camera."""

    identifier = "io.openpype.creators.maya.camerarig"
    label = "Camera Rig"
    product_type = "camerarig"
    icon = "video-camera"

    def create(self, product_name, instance_data, pre_create_data):

        instance = super(CreateCameraRig, self).create(product_name,
                                                       instance_data,
                                                       pre_create_data)

        instance_node = instance.get("instance_node")

        self.log.info("Creating Camera Rig instance set up ...")
        cameras = cmds.sets(name=product_name + "_cam", empty=True)
        cmds.sets([cameras], forceElement=instance_node)
