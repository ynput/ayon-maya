from __future__ import annotations
import math
import json
import collections
from typing import Any, Optional

import ayon_api
from ayon_maya.api import plugin
from ayon_maya.api.lib import (
    unique_namespace,
    get_container_members,
    get_highest_in_hierarchy
)
from ayon_maya.api.pipeline import containerise
from ayon_core.pipeline.load import (
    get_representation_contexts,
    get_loaders_by_name,
    load_with_repre_context,
)
from maya import cmds
from maya.api import OpenMaya as om


class LayoutLoader(plugin.Loader):
    """Layout Loader (json)"""

    product_types = {"layout"}
    representations = {"json"}

    label = "Load Layout"
    order = -10
    icon = "code-fork"
    color = "orange"

    # For JSON elements where we don't know what representation
    # to use, prefer to load the representation in this order.
    repre_order_by_name: dict[str, int] = {
        key: i for i, key in enumerate([
            "fbx", "abc", "usd", "vdb", "ma"
        ])
    }

    def _get_repre_contexts_by_version_id(
        self,
        data: dict,
        context: dict
    ) -> dict[str, list[dict[str, dict]]]:
        """Fetch all representation contexts for all version ids in data
        at once - as optimal query."""
        version_ids = {
            element.get("version")
            for element in data
        }
        version_ids.discard(None)
        if not version_ids:
            return {}

        output = collections.defaultdict(list)
        project_name: str = context["project"]["name"]
        repre_entities = ayon_api.get_representations(
            project_name,
            version_ids=version_ids
        )
        repre_contexts = get_representation_contexts(
            project_name,
            repre_entities
        )
        for repre_context in repre_contexts.values():
            version_id = repre_context["version"]["id"]
            output[version_id].append(repre_context)
        return dict(output)

    def get_container_root(self, container, element):
        """Get the container root and check with the
        namespace of the root aligning to the instance_name
        from element.
        If it does not match, the instance_name from the element
        is set to the namespace of the container root.

        Args:
            container (str): container node name.
            element (dict[str, Any]): element data from layout json

        Returns:
            str: container root dag node.
        """
        # TODO: Improve this logic to support multiples of same asset
        #  and to avoid bugs with containers getting renamed by artists
        # Get the highest root node from the loaded container
        members = get_container_members(
            container,
            include_reference_associated_nodes=True
        )
        roots = get_highest_in_hierarchy(members)

        # Assume only one root for a loaded container, use the first one.
        root = next(iter(roots), None)
        if not root:
            raise RuntimeError(
                f"Unable to find asset root for container: {container}"
            )

        # For loading multiple layouts with the same namespaces
        # Once namespace is already found, it would be replaced
        # by new namespace but still applies the correct
        # transformation data
        element["instance_name"] = cmds.getAttr(f"{container}.namespace")
        return root

    @staticmethod
    def _get_loader_name(product_type: str) -> Optional[str]:
        if product_type in {
            "rig", "model", "camera",
            "animation", "staticMesh",
            "skeletalMesh"
        }:
            return "ReferenceLoader"
        return None

    def _process_element(
        self,
        element: dict[str, Any],
        repre_contexts_by_version_id: dict[str, list[dict]]
    ) -> list[str]:
        """Load one of the elements from a layout JSON file.

        Each element will specify a version for which we will load
        the first representation.
        """
        version_id = element.get("version")
        if not version_id:
            self.log.warning(
                f"No version id found in element: {element}")
            return []

        repre_contexts: list[dict] = repre_contexts_by_version_id.get(
            version_id, []
        )
        if not repre_contexts:
            self.log.error(
                "No representations found for version id:"
                f" {version_id}")
            return []

        def _sort_by_preferred_order(_repre_context: dict) -> int:
            _repre_name: str = _repre_context["representation"]["name"]
            return self.repre_order_by_name.get(
                _repre_name,
                len(self.repre_order_by_name) + 1
            )

        repre_contexts.sort(key=_sort_by_preferred_order)

        # Get preferred loader
        loader_name: Optional[str] = element.get("loader")
        if not loader_name:
            product_type = element.get("product_type")
            if product_type is None:
                # Backwards compatibility
                product_type = element.get("family")
            loader_name = self._get_loader_name(product_type)

        # Find loader plugin
        # TODO: Cache the loaders by name once
        loader = get_loaders_by_name().get(loader_name, None)
        if not loader:
            self.log.error(
                f"No valid loader '{loader_name}' found for: {element}"
            )
            return []

        # Find a matching representation for the loader among
        # the ordered representations of the version
        # TODO: We should actually figure out from the published data what
        #   representation is actually preferred instead of guessing
        #   a first entry that is compatible with the loader
        supported_repre_context: Optional[dict[str, dict[str, Any]]] = None
        for repre_context in repre_contexts:
            if loader.is_loader_compatible(repre_context):
                supported_repre_context = repre_context

        if not supported_repre_context:
            self.log.error(
                f"Loader '{loader_name}' does not support"
                f" representation contexts: {repre_contexts}"
            )
            return []

        # Load the representation
        # TODO: Currently load API does not enforce a return data structure
        #  from the `Loader.load` call. In Maya ReferenceLoader may return
        #  a list of container nodes (objectSet names) but others may return a
        #  single container node.
        instance_name: str = element['instance_name']
        result = load_with_repre_context(
            loader,
            repre_context=supported_repre_context,
            namespace=instance_name
        )
        if isinstance(result, str):
            containers: list[str] = [result]
        elif isinstance(result, list):
            containers: list[str] = result
        else:
            self.log.warning(
                f"Loader {loader} returned invalid container data: {result}"
            )
            return []

        # Move the container root node
        for container in containers:
            self.set_transformation(container, element)
        return containers

    def set_transformation(self, container: str, element: dict[str, Any]):
        """Transform objects in the loaded container.

        1. Transform the root of the loaded container using the element's
           transform matrix.
        2. For object transformation in element `object_transform` data
           apply transformation overrides to children nodes.
        """
        container_root = self.get_container_root(container, element)

        if "unreal" in element.get("host", []):
            # Special behavior for Unreal import
            transform = element["transform"]
            self._set_transformation(container_root, transform)
            return

        transform = element["transform_matrix"]
        # flatten matrix to a list
        maya_transform_matrix: list[float] = [
            element for row in transform for element in row
        ]
        self._set_transformation_by_matrix(container_root,
                                           maya_transform_matrix)

        instance_name = element["instance_name"]
        for object_data in element.get("object_transform", []):
            for obj_name, transform_matrix in object_data.items():
                expected_name: str = f"{instance_name}:{obj_name}"
                obj_transforms = cmds.ls(
                    expected_name,
                    type="transform",
                    long=True
                )
                if not obj_transforms:
                    self.log.warning(
                        f"No transforms found for: {expected_name}"
                    )
                    continue
                if len(obj_transforms) > 1:
                    self.log.warning(
                        f"Multiple transforms found for {expected_name}. "
                        "Using the first one instead."
                    )
                    continue
                obj_root = obj_transforms[0]
                # flatten matrix to a list
                maya_transform_matrix: list[float] = [
                    element for row in transform_matrix for element in row
                ]
                self._set_transformation_by_matrix(
                    obj_root,
                    maya_transform_matrix
                )

    def _set_transformation(self, node: str, transform: dict):
        translation = [
            transform["translation"]["x"],
            transform["translation"]["z"],
            transform["translation"]["y"]
            ]

        rotation = [
            math.degrees(transform["rotation"]["x"]),
            -math.degrees(transform["rotation"]["z"]),
            math.degrees(transform["rotation"]["y"]),
        ]
        scale = [
            transform["scale"]["x"],
            transform["scale"]["z"],
            transform["scale"]["y"]
        ]
        cmds.xform(
            node,
            translation=translation,
            rotation=rotation,
            scale=scale
        )

    def _set_transformation_by_matrix(self, node: str, transform: list[float]):
        """Set transformation with transform matrix and rotation data
        for the imported asset.

        Args:
            node (str): Transform node name
            transform (list[float]): Transformations of the asset
        """
        transform_mm = om.MMatrix(transform)
        convert_transform = om.MTransformationMatrix(transform_mm)
        convert_translation = convert_transform.translation(om.MSpace.kWorld)
        convert_scale = convert_transform.scale(om.MSpace.kWorld)
        convert_rotation = convert_transform.rotation()
        rotation_degrees = [om.MAngle(convert_rotation.x).asDegrees(),
                            om.MAngle(convert_rotation.z).asDegrees(),
                            om.MAngle(convert_rotation.y).asDegrees()]
        translation = [
            convert_translation.x,
            convert_translation.z,
            convert_translation.y
        ]
        cmds.xform(
            node,
            translation=translation,
            rotation=rotation_degrees,
            scale=[convert_scale[0], convert_scale[2], convert_scale[1]]
        )

    def load(self, context, name, namespace, options):
        path = self.filepath_from_context(context)
        self.log.info(f">>> loading json [ {path} ]")
        with open(path, "r") as fp:
            data = json.load(fp)

        # get the list of representations by using version id
        repre_contexts_by_version_id = self._get_repre_contexts_by_version_id(
            data, context
        )
        containers: list[str] = []
        for element in data:
            loaded_containers = self._process_element(
                element,
                repre_contexts_by_version_id
            )
            containers.extend(loaded_containers)

        folder_name = context["folder"]["name"]
        namespace = namespace or unique_namespace(
            folder_name + "_",
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="_",
        )

        return containerise(
            name=name,
            namespace=namespace,
            nodes=containers,
            context=context,
            loader=self.__class__.__name__)

    def update(self, container, context):
        repre_entity = context["representation"]
        path = self.filepath_from_context(context)
        self.log.info(f">>> loading json [ {path} ]")
        with open(path, "r") as fp:
            data = json.load(fp)

        # get the list of representations by using version id
        repre_contexts_by_version_id = self._get_repre_contexts_by_version_id(
            data, context
        )

        container_node: str = container["objectName"]

        # On load, we collected the loaded containers into
        # the layout container, to update existing containers we match
        # them by those container node names.
        member_containers = get_container_members(container)

        for element in data:
            # Find a matching container node among the members
            # TODO: Make this lookup more reliable than just
            #  checking the container node name.
            instance_name: str = element.get("instance_name")
            update_containers: list[str] = [
                node for node in member_containers
                if instance_name in node
            ]
            if update_containers:
                # Update existing elements
                for update_container in update_containers:
                    self.set_transformation(update_container,
                                            element)
            else:
                # Load new elements and add them to container
                loaded_containers = self._process_element(
                    element, repre_contexts_by_version_id
                )
                cmds.sets(loaded_containers, add=container_node)

        # Update metadata
        cmds.setAttr("{}.representation".format(container_node),
                     repre_entity["id"],
                     type="string")

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        container_node: str = container['objectName']
        members = cmds.sets(container_node, query=True)
        cmds.lockNode(members, lock=False)
        cmds.delete([container_node] + members)
        # Clean up the namespace
        try:
            cmds.namespace(
                removeNamespace=container['namespace'],
                deleteNamespaceContent=True)
        except RuntimeError:
            pass