from __future__ import annotations
import json
import math
import os
import re
import uuid
import attr
from typing import Any, List, TYPE_CHECKING

import ayon_api
from ayon_core.pipeline import registered_host
from ayon_maya.api import plugin
from ayon_maya.api.lib import (
    get_highest_in_hierarchy,
    get_container_members,
    get_all_children
)
from maya import cmds
from maya.api import OpenMaya as om

if TYPE_CHECKING:
    import pyblish.api


BASIS_MATRIX = [
    [1, 0, 0, 0],
    [0, 1, 0, 0],
    [0, 0, 1, 0],
    [0, 0, 0, 1]
]


@attr.define
class Container:
    objectName: str
    namespace: str
    representation: str
    loader: str
    members: list[str]

    def __hash__(self):
        # container node is always unique in the scene
        return hash(self.objectName)


@attr.define
class LayoutElement:
    # Loaded representation
    product_type: str
    instance_name: str
    representation: str
    version: str
    extension: str
    host: List[str]
    loader: str

    # Transformation
    transform_matrix: List[List[float]]
    basis: List[List[float]]
    rotation: dict

    # Child object transformations by object name
    object_transform: list[dict[str, List[List[float]]]] = attr.ib(default=None)


def is_valid_uuid(value) -> bool:
    """Return whether value is a valid UUID"""
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def extract_number_from_namespace(namespace):
    """Extracts a number from the namespace.

    Args:
        namespace (str): namespace

    Returns:
        int: namespace number
    """
    matches = re.findall(r'(\d+)', namespace)
    return int(matches[-1]) if matches else 0


def convert_matrix_to_4x4_list(
        value) -> List[List[float]]:
    """Convert matrix or flat list to 4x4 matrix list
    Example:
        >>> convert_matrix_to_4x4_list(om.MMatrix())
        [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        >>> convert_matrix_to_4x4_list(
        ... [1, 0, 0, 0,
        ...  0, 1, 0, 0,
        ...  0, 0, 1, 0,
        ...  0, 0, 0, 1]
        ... )
        [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    """
    result = []
    value = list(value)
    for i in range(0, len(value), 4):
        result.append(list(value[i:i + 4]))
    return result


class ExtractLayout(plugin.MayaExtractorPlugin):
    """Extract a layout."""

    label = "Extract Layout"
    families = ["layout"]

    def process(self, instance: pyblish.api.Instance):
        self.log.debug("Performing layout extraction..")
        allow_obj_transforms: bool = instance.data.get(
            "allowObjectTransforms",
            False
        )

        # Get all containers from the scene and their members so from the
        # layout instance members we can find what containers we have inside
        # the layout that we want to publish.
        host = registered_host()

        # Get containers, but ignore containers with invalid representation ids
        scene_containers: list[Container] = []
        for container in host.get_containers():
            if not is_valid_uuid(container.get("representation")):
                continue

            container_members = get_container_members(
                container,
                include_reference_associated_nodes=True
            )

            scene_containers.append(Container(
                objectName=container["objectName"],
                namespace=container["namespace"],
                representation=container["representation"],
                loader=container["loader"],
                members=container_members
            ))

        node_to_scene_container: dict[str, Container] = {}
        for scene_container in scene_containers:
            for container_member in scene_container.members:
                node_to_scene_container[container_member] = scene_container

        # Find all unique included containers from the layout instance members
        instance_set_members: list[str] = instance.data["setMembers"]
        included_containers: set[Container] = set()
        for node in instance_set_members:
            container = node_to_scene_container.get(node)
            if container:
                included_containers.add(container)

        # Include recursively children of LayoutLoader containers
        included_containers = self.include_layout_loader_children(
            included_containers, node_to_scene_container
        )

        # Query all representations from the included containers
        # TODO: Once we support managed products from another project we should
        #  be querying here using the project name from the container instead.
        project_name = instance.context.data["projectName"]
        representation_ids = {c.representation for c in included_containers}
        representations = ayon_api.get_representations(
            project_name,
            representation_ids=representation_ids,
            fields={"id", "versionId", "context", "name"}
        )
        representations_by_id = {r["id"]: r for r in representations}

        # Process each container found in the layout instance
        elements: list[LayoutElement] = []
        for container in included_containers:
            representation_id: str = container.representation
            representation = representations_by_id.get(representation_id)
            if not representation:
                self.log.warning(
                    "Representation not found in current project "
                    "for container: {}".format(container))
                continue

            element = self.get_container_element(
                container=container,
                representation=representation,
                allow_obj_transforms=allow_obj_transforms
            )
            self.log.debug("Layout element collected: %s", element)
            elements.append(element)

        # Sort by instance name
        elements = sorted(elements, key=lambda x: x.instance_name)
        json_data: list[dict] = [attr.asdict(element) for element in elements]

        # Define extract output file path
        stagingdir = self.staging_dir(instance)
        json_filename = "{}.json".format(instance.name)
        json_path = os.path.join(stagingdir, json_filename)
        with open(json_path, "w+") as file:
            json.dump(json_data, fp=file, indent=2)

        json_representation = {
            'name': 'json',
            'ext': 'json',
            'files': json_filename,
            "stagingDir": stagingdir,
        }
        instance.data.setdefault("representations", []).append(
            json_representation
        )

        self.log.debug("Extracted instance '%s' to: %s",
                       instance.name, json_representation)

    def include_layout_loader_children(
        self,
        containers: set[Container],
        node_to_scene_containers: dict[str, Container]
    ) -> set[Container]:

        """Include children containers of LayoutLoader containers
        recursively.

        Args:
            containers (set[Container]): Set of containers to process
            node_to_scene_containers (dict[str, Container]): Mapping of node to
                container in the scene

        Returns:
            set[Container]: Updated set of containers including children
        """
        all_containers_set = set(containers)
        for container in containers:
            if container.loader == "LayoutLoader":
                child_containers = set()
                for member in container.members:
                    child_containers.add(node_to_scene_containers.get(member))
                child_containers.discard(None)
                all_containers_set.update(child_containers)
                all_containers_set.update(
                    self.include_layout_loader_children(
                        child_containers,
                        node_to_scene_containers
                    )
                )
        return all_containers_set

    def get_container_element(
        self,
        container: Container,
        representation: dict[str, Any],
        allow_obj_transforms: bool
    ) -> LayoutElement:
        """Get layout element data from the container root."""

        container_root = self.get_container_root(container)
        # TODO use product entity to get product type rather than
        #    data in representation 'context'
        repre_context = representation["context"]
        product_type: str = repre_context.get("product", {}).get("type")
        if not product_type:
            product_type = repre_context.get("family")

        # Get transformation data
        local_matrix = cmds.xform(container_root, query=True, matrix=True)
        local_rotation = cmds.xform(
            container_root, query=True, rotation=True, euler=True
        )
        transform_matrix = self.create_transformation_matrix(local_matrix,
                                                             local_rotation)
        transform_matrix = [list(row) for row in transform_matrix]
        rotation = {
            "x": local_rotation[0],
            "y": local_rotation[1],
            "z": local_rotation[2]
        }

        element = LayoutElement(
            product_type=product_type,
            instance_name=container.namespace,
            representation=representation["id"],
            version=representation["versionId"],
            extension=repre_context["ext"],
            host=self.hosts,
            loader=container.loader,
            transform_matrix=transform_matrix,
            basis=BASIS_MATRIX,
            rotation=rotation,
        )
        if allow_obj_transforms:
            child_transforms = cmds.ls(
                get_all_children(
                    [container_root],
                    ignore_intermediate_objects=True
                ),
                type="transform",
                long=True
            )
            for child_transform in child_transforms:
                element.object_transform.append(
                    self.get_child_transform(
                        child_transform
                    )
                )
        return element

    def get_container_root(self, container):
        """Get the root transform from a given Container.

        Args:
            container (Container): Ayon loaded container

        Returns:
            str: container's root transform node
        """
        transforms = cmds.ls(container.members,
                             transforms=True,
                             references=False)
        roots = get_highest_in_hierarchy(transforms)
        if roots:
            root = roots[0].split("|")[1]
            return root

    def create_transformation_matrix(self, local_matrix, local_rotation):
        matrix = om.MMatrix(local_matrix)
        matrix = self.convert_transformation_matrix(matrix, local_rotation)
        t_matrix = convert_matrix_to_4x4_list(matrix)
        return t_matrix

    def convert_transformation_matrix(self, transform_mm: om.MMatrix, rotation: list) -> om.MMatrix:
        """Convert matrix to list of transformation matrix for Unreal Engine fbx asset import.

        Args:
            transform_mm (om.MMatrix): Local Matrix for the asset
            rotation (list): Rotations of the asset

        Returns:
            List[om.MMatrix]: List of transformation matrix of the asset
        """
        convert_transform = om.MTransformationMatrix(transform_mm)
        convert_translation = convert_transform.translation(om.MSpace.kWorld)
        convert_translation = om.MVector(
            convert_translation.x,
            convert_translation.z,
            convert_translation.y
        )
        convert_scale = convert_transform.scale(om.MSpace.kWorld)
        convert_transform.setTranslation(convert_translation, om.MSpace.kWorld)
        converted_rotation = om.MEulerRotation(
            math.radians(rotation[0]),
            math.radians(rotation[2]),
            math.radians(rotation[1])
        )
        convert_transform.setRotation(converted_rotation)
        convert_transform.setScale(
            [
                convert_scale[0],
                convert_scale[2],
                convert_scale[1]
            ],
            om.MSpace.kWorld)

        return convert_transform.asMatrix()

    def get_child_transform(self, child_transform):
        """Parse transform data of the container objects.
        Args:
            child_transform (str): transform node.
        Returns:
            dict: transform data of the transform object
        """
        local_matrix = cmds.xform(child_transform, query=True, matrix=True)
        local_rotation = cmds.xform(child_transform, query=True, rotation=True)
        transform_matrix = self.create_transformation_matrix(local_matrix, local_rotation)
        child_transform_name = child_transform.rsplit(":", 1)[-1]
        return {
            child_transform_name: transform_matrix
        }
