from __future__ import annotations
import math
import json
import collections
from typing import Any

import ayon_api
from ayon_maya.api import plugin
from ayon_maya.api.lib import (
    unique_namespace,
    get_container_members,
    get_highest_in_hierarchy
)
from ayon_maya.api.pipeline import containerise
from ayon_core.pipeline import (
    load_container,
    discover_loader_plugins,
    loaders_from_representation,
    get_current_project_name
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

    def _get_repre_entities_by_version_id(
        self,
        data: dict
    ) -> dict[str, list[dict]]:
        version_ids = {
            element.get("version")
            for element in data
        }
        version_ids.discard(None)
        if not version_ids:
            return {}

        output = collections.defaultdict(list)
        project_name = get_current_project_name()
        repre_entities = ayon_api.get_representations(
            project_name,
            representation_names={"fbx", "abc"},
            version_ids=version_ids,
            fields={"id", "versionId", "name"}
        )
        for repre_entity in repre_entities:
            version_id = repre_entity["versionId"]
            output[version_id].append(repre_entity)
        return dict(output)

    @staticmethod
    def _get_loader(loaders: list, product_type: str, loader_name: str):
        if not loader_name:
            if product_type in {
                "rig", "model", "camera",
                "animation", "staticMesh",
                "skeletalMesh"}:
                    loader_name = "ReferenceLoader"
            else:
                return None

        for loader in loaders:
            if loader.__name__ == loader_name:
                return loader

        return None

    def get_container_root(self, container, element):
        """Get the container root and check with the
        namespace of the root aligning to the instance_name
        from element.
        If it does not match, the instance_name from the element
        is set to the namespace of the container root.

        Args:
            container (str): containers
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


    def _process_element(
        self,
        element: dict[str, Any],
        repre_entities_by_version_id: dict[str, list[dict]]
    ) -> list[str]:
        """Load one of the elements from a layout JSON file.

        Each element will specify a version for which we will load
        the first representation
        """
        repre_id = None
        repr_format = None
        version_id = element.get("version")
        if version_id:
            repre_entities = repre_entities_by_version_id[version_id]
            if not repre_entities:
                self.log.error(
                    "No valid representation found for version"
                    f" {version_id}")
                return []
            # always use the first representation to load
            # If reference is None, this element is skipped, as it cannot be
            # imported in Maya, repre_entities must always be the first one
            repre_entity = repre_entities[0]
            repre_id = repre_entity["id"]
            repr_format = repre_entity["name"]

        # If reference is None, this element is skipped, as it cannot be
        # imported in Maya
        if not repr_format:
            self.log.warning(
                f"Representation name not defined for element: {element}")
            return []

        # Filter available loaders by representation
        instance_name: str = element['instance_name']
        all_loaders = discover_loader_plugins()
        product_type = element.get("product_type")
        if product_type is None:
            product_type = element.get("family")
        loaders = loaders_from_representation(
            all_loaders, repre_id)

        # Find the right loader for the element
        loader = self._get_loader(
            loaders,
            product_type,
            element.get("loader", "")
        )
        if not loader:
            self.log.error(
                f"No valid loader found for {repre_id}")
            return []

        # Load it, and transform the root to match the JSON element.
        # TODO: Currently load API does not enforce a return data structure
        #  from the `Loader.load` call. In Maya ReferenceLoader may return
        #  a list of container nodes (objectSet names) but others may return a
        #  single container node.
        result = load_container(
            loader,
            repre_id,
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

    def _get_asset_container_by_instance_name(self, container_node, element):
        """Get existing asset container by instance name

        Args:
            container_node (str): container_node
            element (dict[str, Any]): element data

        Returns:
            list: asset container
        """
        container_nodes = cmds.sets(container_node, query=True)
        instance_name = element.get("instance_name")
        return [
            node for node in container_nodes if instance_name in node
        ]

    def load(self, context, name, namespace, options):
        path = self.filepath_from_context(context)
        self.log.info(f">>> loading json [ {path} ]")
        with open(path, "r") as fp:
            data = json.load(fp)

        # get the list of representations by using version id
        repre_entities_by_version_id = self._get_repre_entities_by_version_id(
            data
        )
        containers: list[str] = []
        for element in data:
            loaded_containers = self._process_element(
                element,
                repre_entities_by_version_id
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
            nodes=assets,
            context=context,
            loader=self.__class__.__name__)

    def update(self, container, context):
        repre_entity = context["representation"]
        path = self.filepath_from_context(context)
        self.log.info(f">>> loading json [ {path} ]")
        with open(path, "r") as fp:
            data = json.load(fp)

        # get the list of representations by using version id
        repre_entities_by_version_id = self._get_repre_entities_by_version_id(
            data
        )

        node = container["objectName"]
        for element in data:
            asset_container = self._get_asset_container_by_instance_name(
                node, element)
            if asset_container:
                self.set_transformation(asset_container, element)
            else:
                elements = self._process_element(
                    element, repre_entities_by_version_id
                )
                cmds.sets(elements, add=node)

        # Update metadata
        cmds.setAttr("{}.representation".format(node),
                     repre_entity["id"],
                     type="string")

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        members = cmds.sets(container['objectName'], query=True)
        cmds.lockNode(members, lock=False)
        cmds.delete([container['objectName']] + members)
        # Clean up the namespace
        try:
            cmds.namespace(removeNamespace=container['namespace'],
                        deleteNamespaceContent=True)
        except RuntimeError:
            pass