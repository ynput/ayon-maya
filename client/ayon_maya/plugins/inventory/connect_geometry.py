from collections import defaultdict

from maya import cmds

from ayon_core.pipeline import InventoryAction, get_repres_contexts
from ayon_maya.api.lib import get_id, get_container_members, set_id


class ConnectGeometry(InventoryAction):
    """Connect geometries within containers.

    Source container will connect to the target containers, by searching for
    matching geometry IDs (cbid).
    Source containers are of product type: "animation" and "pointcache".
    The connection with be done with a live world space blendshape.
    """

    label = "Connect Geometry"
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

        # Categorize containers by family.
        containers_by_product_base_type = defaultdict(list)
        repre_ids = {
            container["representation"]
            for container in containers
        }
        repre_contexts_by_id = get_repres_contexts(repre_ids)
        for container in containers:
            repre_id = container["representation"]
            repre_context = repre_contexts_by_id[repre_id]

            product_entity = repre_context["product"]
            product_base_type = product_entity.get("productBaseType")
            if not product_base_type:
                product_base_type = product_entity["productType"]

            containers_by_product_base_type[product_base_type].append(
                container
            )

        # Validate to only 1 source container.
        source_containers = containers_by_product_base_type["animation"]
        source_containers += containers_by_product_base_type["pointcache"]
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

        source_object = source_containers[0]["objectName"]

        # Collect matching geometry transforms based cbId attribute.
        target_containers = []
        for product_base_type, containers in (
            containers_by_product_base_type.items()
        ):
            if product_base_type in {"animation", "pointcache"}:
                continue
            target_containers.extend(containers)

        source_data = self.get_container_data(source_object)
        matches = []
        node_types = set()
        for target_container in target_containers:
            target_data = self.get_container_data(
                target_container["objectName"]
            )
            node_types.update(target_data["node_types"])
            for id, transform in target_data["ids"].items():
                source_match = source_data["ids"].get(id)
                if source_match:
                    matches.append([source_match, transform])

        # Message user about what is about to happen.
        if not matches:
            self.display_warning("No matching geometries found.")
            return

        message = "Connecting geometries:\n\n"
        for match in matches:
            message += "{} > {}\n".format(match[0], match[1])

        choice = self.display_warning(message, show_cancel=True)
        if choice is False:
            return

        # Setup live worldspace blendshape connection.
        for source, target in matches:
            self.connect_geometry(source, target)

        # Update Xgen if in any of the containers.
        if "xgmPalette" in node_types:
            cmds.xgmPreview()

    def connect_geometry(self, source: str, target: str):
        # Get the target mesh shape before applying the blendshape,
        # because we may need to validate the ID on the output mesh of
        # the blendshape.
        if cmds.objectType(target, isAType="deformableShape"):
            target_shapes = [target]
        else:
            target_shapes = cmds.listRelatives(
                target,
                type="deformableShape",
                fullPath=True,
                noIntermediate=True,
            ) or []

        # Add blendshape
        blendshape = cmds.blendShape(source, target)[0]
        cmds.setAttr(blendshape + ".origin", 0)
        cmds.setAttr(blendshape + "." + target.split(":")[-1], 1)

        if not target_shapes:
            self.log.warning(
                "No shape found for target: {}".format(target)
            )
            return
        target_shape = target_shapes[0]

        # If the target was a referenced mesh then it may have generated
        # a new "DeformedShape" node which may be lacking any custom
        # attributes the original mesh had, like e.g. `cbId`. We will
        # want to make sure to preserve those attributes so look
        # assignments can still work.
        if not cmds.referenceQuery(target_shape, isNodeReferenced=True):
            return

        # Target mesh has no ID to maintain, so we can skip this.
        if not get_id(target_shape):
            return

        output = cmds.listConnections(
            f"{blendshape}.outputGeometry[0]",
            source=False,
            destination=True,
            shapes=True
        )[0]
        if output != target_shape and not get_id(output):
            self.log.info(
                "Transferring ID from target shape to new output shape: "
                f"{target_shape} -> {output}"
            )
            set_id(output, get_id(target_shape))

    def get_container_data(self, container):
        """Collects data about the container nodes.

        Args:
            container (dict): Container instance.

        Returns:
            data (dict):
                "node_types": All node types in container nodes.
                "ids": If the node is a mesh, we collect its parent transform
                    id.
        """
        data = {"node_types": set(), "ids": {}}
        for node in get_container_members(container):
            node_type = cmds.nodeType(node)
            data["node_types"].add(node_type)

            # Only interested in mesh transforms for connecting geometry with
            # blendshape.
            if node_type != "mesh":
                continue

            transform = cmds.listRelatives(node, parent=True, fullPath=True)[0]
            data["ids"][get_id(transform)] = transform

        return data

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
