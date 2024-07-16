import os
import json
from collections import defaultdict

from maya import cmds
from typing import List, Dict, Any, Optional
from ayon_core.pipeline import (
    InventoryAction,
    get_repres_contexts,
    get_representation_path,
    get_current_project_name
)
from ayon_maya.api.lib import get_container_members
from ayon_api import (
    get_representation_by_id,
    get_representation_by_name
)


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


def connect(src, dest):
    """Connect attribute but ignore warnings on existing connections"""
    if not cmds.isConnected(src, dest):
        cmds.connectAttr(src, dest, force=True)


def get_sibling_representation(project_name: str,
                               representation_id: str,
                               representation_name: str) -> Optional[dict]:
    """Return sibling representation entity under parent version from
    representation id."""
    repre_entity = get_representation_by_id(project_name, representation_id,
                                            fields={"versionId"})
    version_id = repre_entity["versionId"]
    return get_representation_by_name(
        project_name, representation_name, version_id=version_id)


def connect_mesh(source, target):
    # TODO: Should we hide the destination mesh to avoid meshes appearing
    #  directly on top of each other?
    connect(f"{source}.worldMesh[0]", f"{target}.inMesh")
    connect(f"{source}.worldMatrix[0]",
            f"{target}.offsetParentMatrix")


class ConnectOrnatrixRig(InventoryAction):
    """Connect Ornatrix Rig with an animation or pointcache.

    Connect one animation or pointcache instance to one or multiple ornatrix
    rig instances.
    """

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

        # Define a mapping to quickly search among the members
        source_nodes = get_container_members(source_container)
        source_nodes_by_name = {
            get_node_name(node_path): node_path
            for node_path in source_nodes
        }

        project_name = get_current_project_name()
        for container in ox_rig_containers:
            # Get relevant ornatrix rig .rigsettings representation path
            repre_id = container["representation"]
            settings_repre = get_sibling_representation(
                project_name,
                repre_id,
                representation_name="rigsettings")
            if not settings_repre:
                continue
            settings_file = get_representation_path(settings_repre)
            if not os.path.exists(settings_file):
                continue

            with open(settings_file, "r") as fp:
                rig_source_nodes: List[Dict[str, Any]] = json.load(fp)
            if not rig_source_nodes:
                self.log.warning(
                    f"No source nodes in the .rigsettings file "
                    f"to process: {settings_file}")
                continue

            rig_nodes = get_container_members(container)

            # Find the node in the source
            for node in rig_source_nodes:
                node_name = get_node_name(node["node"])

                # Find the source node we want to connect to the target rig
                source_node = source_nodes_by_name.get(node_name)
                if not source_node:
                    self.log.warning(
                        "No source node found for '%s' searching in "
                        "namespace: %s", node_name, source_namespace)
                    self.display_warning(
                        "No source node found "
                        "in \"animation\" or \"pointcache\"."
                    )
                    return

                # Find matching target node
                for target_node in rig_nodes:
                    if get_node_name(target_node) != node_name:
                        continue

                    # Connect source mesh to target mesh
                    self.log.info("Connecting mesh %s -> %s",
                                  source_node, target_node)
                    connect_mesh(source_node, target_node)

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
