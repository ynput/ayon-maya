from ayon_maya.api import (
    lib,
    plugin
)
from ayon_core.lib import (
    BoolDef,
    NumberDef,
    EnumDef
)

TRANSPARENCIES = [
    "preset",
    "simple",
    "object sorting",
    "weighted average",
    "depth peeling",
    "alpha cut"
]


class CreateReview(plugin.MayaCreator):
    """Playblast reviewable"""

    identifier = "io.openpype.creators.maya.review"
    label = "Review"
    # product_type to be defined in the project settings
    # use product_base_type instead
    # see https://github.com/ynput/ayon-core/issues/1297
    product_base_type = product_type = "review"
    icon = "video-camera"

    useMayaTimeline = True
    panZoom = False

    def get_attr_defs_for_instance(self, instance):
        create_context = self.create_context
        defs = lib.collect_animation_defs(create_context=create_context)

        # Option for using Maya or folder frame range in settings.
        if not self.useMayaTimeline:
            # Update the defaults to be the folder frame range
            frame_range = lib.get_frame_range()
            defs_by_key = {attr_def.key: attr_def for attr_def in defs}
            for key, value in frame_range.items():
                if key not in defs_by_key:
                    raise RuntimeError("Attribute definition not found to be "
                                       "updated for key: {}".format(key))
                attr_def = defs_by_key[key]
                attr_def.default = value

        product_name: str = instance.data["productName"]
        folder_path: str = instance.data["folderPath"]
        task_name: str = instance.data["task"]
        task_entity = create_context.get_task_entity(folder_path, task_name)
        preset = lib.get_capture_preset(
            task_name,
            task_entity["taskType"] if task_entity else None,
            product_name,
            create_context.get_current_project_settings(),
            log=self.log
        )

        defs.extend([
            NumberDef("review_width",
                      label="Review width",
                      tooltip="A value of zero will use the folder resolution.",
                      decimals=0,
                      minimum=0,
                      default=preset["Resolution"]["width"]),
            NumberDef("review_height",
                      label="Review height",
                      tooltip="A value of zero will use the folder resolution.",
                      decimals=0,
                      minimum=0,
                      default=preset["Resolution"]["height"]),
            BoolDef("keepImages",
                    label="Keep Images",
                    tooltip="Whether to also publish along the image sequence "
                            "next to the video reviewable.",
                    default=False),
            BoolDef("isolate",
                    label="Isolate render members of instance",
                    tooltip="When enabled only the members of the instance "
                            "will be included in the playblast review.",
                    default=preset["Generic"]["isolate_view"]),
            BoolDef("imagePlane",
                    label="Show Image Plane",
                    default=preset["ViewportOptions"]["imagePlane"]),
            EnumDef("transparency",
                    label="Transparency",
                    items=TRANSPARENCIES),
            BoolDef("panZoom",
                    label="Enable camera pan/zoom",
                    default=preset["Generic"]["pan_zoom"]),
            EnumDef("displayLights",
                    label="Display Lights",
                    items=lib.DISPLAY_LIGHTS_ENUM),
        ])

        return defs
