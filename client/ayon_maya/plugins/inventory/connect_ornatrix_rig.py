import os
import json
from collections import defaultdict

from maya import cmds
from typing import List, Dict, Any
from ayon_core.pipeline import (
    InventoryAction,
    get_repres_contexts,
    get_representation_path,
)
from ayon_maya.api.lib import namespaced


def get_node_name(path: str) -> str:
    """Return maya node name without namespace or parents

    Examples:
        >>> get_node_name("|grp|node")
        "node"
        >>> get_node_name("|foobar:grp|foobar:child")
        "child"
        >>> get_node_name("|foobar:grp|lala:bar|foobar:test:hello_world")
        "hello_world"
    """
    return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]


class ConnectOrnatrixRig(InventoryAction):
    """Connect Ornatrix Rig with an animation or pointcache."""

    label = "Connect Ornatrix Rig"
    icon = "link"
    color = "white"

    def process(self, containers):
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
        source_repre_id = source_container["representation"]
        source_namespace = source_container["namespace"]

        # Validate source representation is an alembic.
        source_path = get_representation_path(
            repre_contexts_by_id[source_repre_id]["representation"]
        ).replace("\\", "/")
        message = "Animation container \"{}\" is not an alembic:\n{}".format(
            source_container["namespace"], source_path
        )
        if not source_path.endswith(".abc"):
            self.display_warning(message)
            return

        ox_rig_containers = containers_by_product_type.get("oxrig")
        if not ox_rig_containers:
            self.display_warning(
                "Select at least one oxrig container"
            )
            return

        for container in ox_rig_containers:
            repre_id = container["representation"]
            maya_file = get_representation_path(
                repre_contexts_by_id[repre_id]["representation"]
            )

            # Get base filename without extension
            # TODO: We should actually get the actual representation paths
            #   through the parent version entity so that we get the
            #   representation's paths supporting the template system instead
            #   of assuming the files live next to the loaded rig file directly
            # of the `.oxg.zip` and the `.rigsettings` instead of computing the
            # relative paths
            if maya_file.endswith(".oxg.zip"):
                base = maya_file[-len(".oxg.zip")]  # strip off multi-dot ext
            else:
                base = os.path.splitext(maya_file)[0]

            settings_file = base + ".rigsettings"
            if not os.path.exists(settings_file):
                continue

            with open(settings_file, "r") as fp:
                source_nodes: List[Dict[str, Any]] = json.load(fp)
            if not source_nodes:
                self.log.warning(
                    f"No source nodes in the .rigsettings file "
                    f"to process: {settings_file}")
                continue

            grooms_file = base + ".oxg.zip"

            with namespaced(":" + source_namespace,
                            new=False, relative_names=True):
                for node in source_nodes:
                    node_name = get_node_name(node["node"])
                    target_node = cmds.ls(node_name)
                    if not target_node:
                        self.log.warning(
                            "No target node found for '%s' searching in "
                            "namespace: %s", node_name, source_namespace)
                        self.display_warning(
                            "No target node found "
                            "in \"animation\" or \"pointcache\"."
                        )
                        return
                    cmds.select(target_node)
                    cmds.OxLoadGroom(path=grooms_file)

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
