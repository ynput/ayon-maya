import collections

from ayon_api import (
    get_folder_by_name,
    get_folder_by_path,
    get_folders,
    get_tasks,
)
from maya import cmds  # noqa: F401

from ayon_maya.api import plugin
from ayon_core.lib import BoolDef, EnumDef, TextDef
from ayon_core.pipeline import (
    Creator,
    get_current_folder_path,
    get_current_project_name,
)
from ayon_core.pipeline.create import CreatorError


class CreateMultishotLayout(plugin.MayaCreator):
    """Create a multi-shot layout in the Maya scene.

    This creator will create a Camera Sequencer in the Maya scene based on
    the shots found under the specified folder. The shots will be added to
    the sequencer in the order of their clipIn and clipOut values. For each
    shot a Layout will be created.

    """
    identifier = "io.openpype.creators.maya.multishotlayout"
    label = "Multi-shot Layout"
    product_type = "layout"
    icon = "project-diagram"

    def get_pre_create_attr_defs(self):
        # Present artist with a list of parents of the current context
        # to choose from. This will be used to get the shots under the
        # selected folder to create the Camera Sequencer.

        """
        Todo: `get_folder_by_name` should be switched to `get_folder_by_path`
              once the fork to pure AYON is done.

        Warning: this will not work for projects where the folder name
                 is not unique across the project until the switch mentioned
                 above is done.
        """

        project_name = get_current_project_name()
        folder_path = get_current_folder_path()
        if "/" in folder_path:
            current_folder = get_folder_by_path(project_name, folder_path)
        else:
            current_folder = get_folder_by_name(
                project_name, folder_name=folder_path
            )

        current_path_parts = current_folder["path"].split("/")

        # populate the list with parents of the current folder
        # this will create menu items like:
        # [
        #   {
        #       "value": "",
        #       "label": "project (shots directly under the project)"
        #   }, {
        #       "value": "shots/shot_01", "label": "shot_01 (current)"
        #   }, {
        #       "value": "shots", "label": "shots"
        #   }
        # ]

        # add the project as the first item
        items_with_label = [
            {
                "label": f"{self.project_name} "
                         "(shots directly under the project)",
                "value": ""
            }
        ]

        # go through the current folder path and add each part to the list,
        # but mark the current folder.
        for part_idx, part in enumerate(current_path_parts):
            label = part
            if label == current_folder["name"]:
                label = f"{label} (current)"

            value = "/".join(current_path_parts[:part_idx + 1])

            items_with_label.append({"label": label, "value": value})

        return [
            EnumDef("shotParent",
                    default=current_folder["name"],
                    label="Shot Parent Folder",
                    items=items_with_label,
                    ),
            BoolDef("groupLoadedAssets",
                    label="Group Loaded Assets",
                    tooltip="Enable this when you want to publish group of "
                            "loaded asset",
                    default=False),
            TextDef("taskName",
                    label="Associated Task Name",
                    tooltip=("Task name to be associated "
                             "with the created Layout"),
                    default="layout"),
        ]

    def create(self, product_name, instance_data, pre_create_data):
        shots = list(
            self.get_related_shots(folder_path=pre_create_data["shotParent"])
        )
        if not shots:
            # There are no shot folders under the specified folder.
            # We are raising an error here but in the future we might
            # want to create a new shot folders by publishing the layouts
            # and shot defined in the sequencer. Sort of editorial publish
            # in side of Maya.
            raise CreatorError((
                "No shots found under the specified "
                f"folder: {pre_create_data['shotParent']}."))

        # Get layout creator
        layout_creator_id = "io.openpype.creators.maya.layout"
        layout_creator: Creator = self.create_context.creators.get(
            layout_creator_id)
        if not layout_creator:
            raise CreatorError(
                f"Creator {layout_creator_id} not found.")

        folder_ids = {s["id"] for s in shots}
        folder_entities = get_folders(self.project_name, folder_ids)
        task_entities = get_tasks(
            self.project_name, folder_ids=folder_ids
        )
        task_entities_by_folder_id = collections.defaultdict(dict)
        for task_entity in task_entities:
            folder_id = task_entity["folderId"]
            task_name = task_entity["name"]
            task_entities_by_folder_id[folder_id][task_name] = task_entity

        folder_entities_by_id = {fe["id"]: fe for fe in folder_entities}
        for shot in shots:
            # we are setting shot name to be displayed in the sequencer to
            # `shot name (shot label)` if the label is set, otherwise just
            # `shot name`. So far, labels are used only when the name is set
            # with characters that are not allowed in the shot name.
            if not shot["active"]:
                continue

            # get task for shot
            folder_id = shot["id"]
            folder_entity = folder_entities_by_id[folder_id]
            task_entities = task_entities_by_folder_id[folder_id]

            layout_task_name = None
            layout_task_entity = None
            if pre_create_data["taskName"] in task_entities:
                layout_task_name = pre_create_data["taskName"]
                layout_task_entity = task_entities[layout_task_name]

            shot_name = shot['name']
            if shot["label"] and shot["label"] != shot_name:
                shot_name += f" ({shot['label']})"

            cmds.shot(sequenceStartTime=shot["attrib"]["clipIn"],
                      sequenceEndTime=shot["attrib"]["clipOut"],
                      shotName=shot_name)

            # Create layout instance by the layout creator

            instance_data = {
                "folderPath": shot["path"],
                "variant": layout_creator.get_default_variant()
            }
            if layout_task_name:
                instance_data["task"] = layout_task_name

            layout_creator.create(
                product_name=layout_creator.get_product_name(
                    self.project_name,
                    folder_entity,
                    layout_task_entity,
                    layout_creator.get_default_variant(),
                ),
                instance_data=instance_data,
                pre_create_data={
                    "groupLoadedAssets": pre_create_data["groupLoadedAssets"]
                }
            )

    def get_related_shots(self, folder_path: str):
        """Get all shots related to the current folder.

        Get all folders of type Shot under specified folder.

        Args:
            folder_path (str): Path of the folder.

        Returns:
            list: List of dicts with folder data.

        """
        # if folder_path is None, project is selected as a root
        # and its name is used as a parent id
        parent_id = self.project_name
        if folder_path:
            current_folder = get_folder_by_path(
                project_name=self.project_name,
                folder_path=folder_path,
            )
            parent_id = current_folder["id"]

        # get all child folders of the current one
        return get_folders(
            project_name=self.project_name,
            parent_ids=[parent_id],
            fields=[
                "attrib.clipIn", "attrib.clipOut",
                "attrib.frameStart", "attrib.frameEnd",
                "name", "label", "path", "folderType", "id"
            ]
        )
