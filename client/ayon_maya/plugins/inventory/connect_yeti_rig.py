import os
import json
from collections import defaultdict

from maya import cmds

from ayon_core.pipeline import (
    InventoryAction,
    get_repres_contexts,
    get_current_project_name,
)
from ayon_maya.api.lib import (
    get_container_members,
    get_id,
    get_representation_path_by_project,
)


class ConnectYetiRig(InventoryAction):
    """Connect Yeti Rig with an animation or pointcache."""

    label = "Connect Yeti Rig"
    icon = "link"
    color = "white"

    def process(self, containers):
        # Validate selection is more than 1.
        message = (
            "Only 1 container selected. 2+ containers needed for this action."
        )
        if len(containers) == 1:
            self.display_warning(message)
            return

        # Categorize containers by product type.
        containers_by_product_type = defaultdict(list)
        repre_ids = {
            container["representation"]
            for container in containers
        }
        repre_contexts_by_id = get_repres_contexts(repre_ids)
        for container in containers:
            repre_id = container["representation"]
            repre_context = repre_contexts_by_id[repre_id]

            product_type = repre_context["product"]["productType"]

            containers_by_product_type.setdefault(product_type, [])
            containers_by_product_type[product_type].append(container)

        # Validate to only 1 source container.
        source_containers = containers_by_product_type.get("animation", [])
        source_containers += containers_by_product_type.get("pointcache", [])
        source_container_namespaces = [
            x["namespace"] for x in source_containers
        ]
        message = (
            "{} animation containers selected:\n\n{}\n\nOnly select 1 of type "
            "\"animation\" or \"pointcache\".".format(
                len(source_containers), source_container_namespaces
            )
        )
        if len(source_containers) != 1:
            self.display_warning(message)
            return

        source_container = source_containers[0]
        source_ids = self.nodes_by_id(source_container)
        source_project = source_container.get(
            "project_name", get_current_project_name()
        )

        # Target containers.
        target_ids = {}
        inputs = []

        yeti_rig_containers = containers_by_product_type.get("yetiRig")
        if not yeti_rig_containers:
            self.display_warning(
                "Select at least one yetiRig container"
            )
            return

        for container in yeti_rig_containers:
            target_ids.update(self.nodes_by_id(container))
            repre_id = container["representation"]

            maya_file = get_representation_path_by_project(
                repre_contexts_by_id[repre_id]["representation"],
                source_project
            )
            _, ext = os.path.splitext(maya_file)
            settings_file = maya_file.replace(ext, ".rigsettings")
            if not os.path.exists(settings_file):
                continue

            with open(settings_file) as f:
                inputs.extend(json.load(f)["inputs"])

            # Compare loaded connections to scene.
            for input in inputs:
                source_node = source_ids.get(input["sourceID"])
                target_node = target_ids.get(input["destinationID"])

                if not source_node or not target_node:
                    self.log.debug(
                        "Could not find nodes for input:\n" +
                        json.dumps(input, indent=4, sort_keys=True)
                    )
                    continue
                source_attr, target_attr = input["connections"]

                if not cmds.attributeQuery(
                    source_attr, node=source_node, exists=True
                ):
                    self.log.debug(
                        "Could not find attribute {} on node {} for "
                        "input:\n{}".format(
                            source_attr,
                            source_node,
                            json.dumps(input, indent=4, sort_keys=True)
                        )
                    )
                    continue

                if not cmds.attributeQuery(
                    target_attr, node=target_node, exists=True
                ):
                    self.log.debug(
                        "Could not find attribute {} on node {} for "
                        "input:\n{}".format(
                            target_attr,
                            target_node,
                            json.dumps(input, indent=4, sort_keys=True)
                        )
                    )
                    continue

                source_plug = "{}.{}".format(
                    source_node, source_attr
                )
                target_plug = "{}.{}".format(
                    target_node, target_attr
                )
                if cmds.isConnected(
                    source_plug, target_plug, ignoreUnitConversion=True
                ):
                    self.log.debug(
                        "Connection already exists: {} -> {}".format(
                            source_plug, target_plug
                        )
                    )
                    continue

                cmds.connectAttr(source_plug, target_plug, force=True)
                self.log.debug(
                    "Connected attributes: {} -> {}".format(
                        source_plug, target_plug
                    )
                )

    def nodes_by_id(self, container):
        ids = {}
        for member in get_container_members(container):
            id = get_id(member)
            if not id:
                continue
            ids[id] = member

        return ids

    def display_warning(self, message, show_cancel=False):
        """Show feedback to user.

        Returns:
            bool
        """

        from qtpy import QtWidgets

        accept = QtWidgets.QMessageBox.Ok
        if show_cancel:
            buttons = accept | QtWidgets.QMessageBox.Cancel
        else:
            buttons = accept

        state = QtWidgets.QMessageBox.warning(
            None,
            "",
            message,
            buttons=buttons,
            defaultButton=accept
        )

        return state == accept
