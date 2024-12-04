import json
import math
import os
import uuid
from typing import List

from ayon_api import get_representation_by_id
from ayon_maya.api import plugin
from ayon_maya.api.lib import get_highest_in_hierarchy, get_container_members
from maya import cmds
from maya.api import OpenMaya as om


def is_valid_uuid(value) -> bool:
    """Return whether value is a valid UUID"""
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


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
    project_container = "AVALON_CONTAINERS"

    def process(self, instance):
        # Define extract output file path
        stagingdir = self.staging_dir(instance)

        # Perform extraction
        self.log.debug("Performing extraction..")

        if "representations" not in instance.data:
            instance.data["representations"] = []

        json_data = []
        # TODO representation queries can be refactored to be faster
        project_name = instance.context.data["projectName"]
        members = [member.lstrip('|') for member in instance.data["setMembers"]]
        for asset in members:
            # Find the container
            project_container = self.project_container
            container_list = cmds.ls(project_container)
            if len(container_list) == 0:
                self.log.warning("Project container is not found!")
                self.log.warning("The asset(s) may not be properly loaded after published") # noqa
                continue

            grp_loaded_ass = instance.data.get("groupLoadedAssets", False)
            if grp_loaded_ass:
                asset_list = cmds.listRelatives(asset, children=True)
                # WARNING This does override 'asset' variable from parent loop
                #   is it correct?
                for asset in asset_list:
                    grp_name = asset.split(':')[0]
            else:
                grp_name = asset.split(':')[0]
            containers = cmds.ls("{}*_CON".format(grp_name))
            if len(containers) == 0:
                self.log.warning("{} isn't from the loader".format(asset))
                self.log.warning("It may not be properly loaded after published") # noqa
                continue

            container_dict = self.process_containers(containers)
            for container, container_root in container_dict.items():
                representation_id = cmds.getAttr(
                    "{}.representation".format(container))

                # Ignore invalid UUID is the representation for whatever reason
                # is invalid
                if not is_valid_uuid(representation_id):
                    self.log.warning(
                        f"Skipping container with invalid UUID: {container}")
                    continue

                # TODO: Once we support managed products from another project
                #  we should be querying here using the project name from the
                #  container instead.
                representation = get_representation_by_id(
                    project_name,
                    representation_id,
                    fields={"versionId", "context", "name"}
                )
                if not representation:
                    self.log.warning(
                        "Representation not found in current project "
                        "for container: {}".format(container))
                    continue

                version_id = representation["versionId"]
                # TODO use product entity to get product type rather than
                #    data in representation 'context'
                repre_context = representation["context"]
                product_type = repre_context.get("product", {}).get("type")
                if not product_type:
                    product_type = repre_context.get("family")

                json_element = {
                    "product_type": product_type,
                    "instance_name": cmds.getAttr(
                        "{}.namespace".format(container)),
                    "representation": str(representation_id),
                    "version": str(version_id),
                    "extension": repre_context["ext"],
                    "host": self.hosts
                }

                local_matrix = cmds.xform(
                    container_root, query=True, matrix=True)
                local_rotation = cmds.xform(
                    container_root, query=True, rotation=True, euler=True)

                t_matrix = self.create_transformation_matrix(local_matrix, local_rotation)

                json_element["transform_matrix"] = [
                    list(row)
                    for row in t_matrix
                ]

                basis_list = [
                    1, 0, 0, 0,
                    0, 1, 0, 0,
                    0, 0, 1, 0,
                    0, 0, 0, 1
                ]

                basis_mm = om.MMatrix(basis_list)
                b_matrix = convert_matrix_to_4x4_list(basis_mm)

                json_element["basis"] = []
                for row in b_matrix:
                    json_element["basis"].append(list(row))

                json_element["rotation"] = {
                    "x": local_rotation[0],
                    "y": local_rotation[1],
                    "z": local_rotation[2]
                }
                json_data.append(json_element)
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

        instance.data["representations"].append(json_representation)

        self.log.debug("Extracted instance '%s' to: %s",
                       instance.name, json_representation)

    def process_containers(self, containers):
        """Allow to collect the asset containers through sub-assembly workflow if
        there is a layout container.

        Args:
            containers (list[str]): Ayon asset containers

        Returns:
            dict[str, str]: container mapping to its related root transform node
        """
        all_containers_set = {}
        for container in containers:
            if cmds.getAttr(f"{container}.loader") == "LayoutLoader":
                # Flatten container layout loader products to their individual loaded containers
                member_containers = get_container_members(container)
                # Recursively process each member container
                children_containers = self.process_containers(member_containers)
                all_containers_set.update(children_containers)
            else:
                members = get_container_members(container)
                transforms = cmds.ls(members, transforms=True)
                roots = get_highest_in_hierarchy(transforms)
                if roots:
                    # Assume just a single root node
                    all_containers_set[container] = roots[0]

        return all_containers_set

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
        convert_translation = om.MVector(convert_translation.x, convert_translation.z, convert_translation.y)
        convert_scale = convert_transform.scale(om.MSpace.kObject)
        convert_transform.setTranslation(convert_translation, om.MSpace.kWorld)
        converted_rotation = om.MEulerRotation(
            math.radians(rotation[0]), math.radians(rotation[2]), math.radians(rotation[1])
        )
        convert_transform.setRotation(converted_rotation)
        convert_transform.setScale([convert_scale[0], convert_scale[2], convert_scale[1]], om.MSpace.kObject)

        return convert_transform.asMatrix()
