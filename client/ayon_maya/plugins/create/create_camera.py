from ayon_maya.api import (
    lib,
    plugin
)
from ayon_core.lib import BoolDef


class CreateCamera(plugin.MayaCreator):
    """Single baked camera"""

    identifier = "io.openpype.creators.maya.camera"
    label = "Camera"
    # product_type to be defined in the project settings
    # use product_base_type instead
    # see https://github.com/ynput/ayon-core/issues/1297
    product_base_type = product_type = "camera"
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
