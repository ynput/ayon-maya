import json

from maya import cmds
import ayon_api

from ayon_maya.api import (
    lib,
    plugin
)
from ayon_core.lib import (
    BoolDef,
    NumberDef,
    EnumDef
)
from ayon_core.pipeline import CreatedInstance

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
    product_type = "review"
    icon = "video-camera"

    useMayaTimeline = True
    panZoom = False

    # Overriding "create" method to prefill values from settings.
    def create(self, product_name, instance_data, pre_create_data):

        members = list()
        if pre_create_data.get("use_selection"):
            members = cmds.ls(selection=True)

        project_name = self.project_name
        folder_path = instance_data["folderPath"]
        task_name = instance_data["task"]
        folder_entity = ayon_api.get_folder_by_path(
            project_name, folder_path, fields={"id"}
        )
        task_entity = ayon_api.get_task_by_name(
            project_name, folder_entity["id"], task_name, fields={"taskType"}
        )
        preset = lib.get_capture_preset(
            task_name,
            task_entity["taskType"],
            product_name,
            self.project_settings,
            self.log
        )
        self.log.debug(
            "Using preset: {}".format(
                json.dumps(preset, indent=4, sort_keys=True)
            )
        )

        with lib.undo_chunk():
            instance_node = cmds.sets(members, name=product_name)
            instance_data["instance_node"] = instance_node
            instance = CreatedInstance(
                self.product_type,
                product_name,
                instance_data,
                self)

            creator_attribute_defs_by_key = {
                x.key: x for x in instance.creator_attribute_defs
            }
            mapping = {
                "review_width": preset["Resolution"]["width"],
                "review_height": preset["Resolution"]["height"],
                "isolate": preset["Generic"]["isolate_view"],
                "imagePlane": preset["ViewportOptions"]["imagePlane"],
                "panZoom": preset["Generic"]["pan_zoom"]
            }
            for key, value in mapping.items():
                creator_attribute_defs_by_key[key].default = value

            self._add_instance_to_context(instance)

            self.imprint_instance_node(instance_node,
                                       data=instance.data_to_store())
            return instance

    def get_instance_attr_defs(self):

        defs = lib.collect_animation_defs(create_context=self.create_context)

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

        defs.extend([
            NumberDef("review_width",
                      label="Review width",
                      tooltip="A value of zero will use the folder resolution.",
                      decimals=0,
                      minimum=0,
                      default=0),
            NumberDef("review_height",
                      label="Review height",
                      tooltip="A value of zero will use the folder resolution.",
                      decimals=0,
                      minimum=0,
                      default=0),
            BoolDef("keepImages",
                    label="Keep Images",
                    tooltip="Whether to also publish along the image sequence "
                            "next to the video reviewable.",
                    default=False),
            BoolDef("isolate",
                    label="Isolate render members of instance",
                    tooltip="When enabled only the members of the instance "
                            "will be included in the playblast review.",
                    default=False),
            BoolDef("imagePlane",
                    label="Show Image Plane",
                    default=True),
            EnumDef("transparency",
                    label="Transparency",
                    items=TRANSPARENCIES),
            BoolDef("panZoom",
                    label="Enable camera pan/zoom",
                    default=True),
            EnumDef("displayLights",
                    label="Display Lights",
                    items=lib.DISPLAY_LIGHTS_ENUM),
        ])

        return defs
