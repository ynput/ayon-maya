# -*- coding: utf-8 -*-
"""Creator plugin for creating workfiles."""
from ayon_core.pipeline import CreatedInstance, AutoCreator
from ayon_maya.api import plugin
from maya import cmds


class CreateWorkfile(plugin.MayaCreatorBase, AutoCreator):
    """Workfile auto-creator."""
    identifier = "io.openpype.creators.maya.workfile"
    label = "Workfile"
    product_type = "workfile"
    icon = "fa5.file"

    default_variant = "Main"

    settings_category = "maya"
    is_mandatory = False

    def create(self):

        variant = self.default_variant
        current_instance = next(
            (
                instance for instance in self.create_context.instances
                if instance.creator_identifier == self.identifier
            ), None)

        project_entity = self.create_context.get_current_project_entity()
        project_name = project_entity["name"]
        folder_entity = self.create_context.get_current_folder_entity()
        folder_path = folder_entity["path"]
        task_entity = self.create_context.get_current_task_entity()
        task_name = task_entity["name"]
        host_name = self.create_context.host_name

        if current_instance is None:
            product_name = self.get_product_name(
                project_name,
                folder_entity,
                task_entity,
                variant,
                host_name,
            )
            data = {
                "folderPath": folder_path,
                "task": task_name,
                "variant": variant
            }
            data.update(
                self.get_dynamic_data(
                    project_name,
                    folder_entity,
                    task_entity,
                    variant,
                    host_name,
                    current_instance)
            )
            self.log.info("Auto-creating workfile instance...")
            current_instance = CreatedInstance(
                self.product_type, product_name, data, self
            )
            self._add_instance_to_context(current_instance)
        elif (
            current_instance["folderPath"] != folder_path
            or current_instance["task"] != task_name
        ):
            # Update instance context if is not the same
            product_name = self.get_product_name(
                project_name,
                folder_entity,
                task_entity,
                variant,
                host_name,
            )

            current_instance["folderPath"] = folder_path
            current_instance["task"] = task_name
            current_instance["productName"] = product_name

        # The 'mandatory' functionality is available since ayon-core 1.4.1
        #   or later.
        if hasattr(current_instance, "set_mandatory"):
            current_instance.set_mandatory(self.is_mandatory)

    def collect_instances(self):
        self.cache_instance_data(self.collection_shared_data)
        cached_instances = (
            self.collection_shared_data["maya_cached_instance_data"]
        )
        for node in cached_instances.get(self.identifier, []):
            node_data = self.read_instance_node(node)

            created_instance = CreatedInstance.from_existing(node_data, self)
            self._add_instance_to_context(created_instance)

    def remove_instances(self, instances):
        self._default_remove_instances(instances)

    def update_instances(self, update_list):
        for created_inst, _changes in update_list:
            data = created_inst.data_to_store()
            node = data.get("instance_node")
            if not node:
                node = self.create_node()
                created_inst["instance_node"] = node
                data = created_inst.data_to_store()

            self.imprint_instance_node(node, data)

    def create_node(self):
        node = cmds.sets(empty=True, name="workfileMain")
        cmds.setAttr(node + ".hiddenInOutliner", True)
        return node
