from maya import cmds
import re
import math
import json
import collections
import ayon_api
from ayon_maya.api import plugin
from ayon_maya.api.lib import (
    unique_namespace,
    get_container_members,
    get_highest_in_hierarchy
)
from ayon_core.pipeline import (
    load_container,
    discover_loader_plugins,
    loaders_from_representation,
    get_current_project_name
)
from maya.api import OpenMaya as om
from ayon_maya.api.pipeline import containerise


class LayoutLoader(plugin.Loader):
    """Layout Loader (json)"""

    product_types = {"layout"}
    representations = {"json"}

    label = "Load Layout"
    order = -10
    icon = "code-fork"
    color = "orange"

    def _get_repre_entities_by_version_id(self, data):
        version_ids = {
            element.get("version")
            for element in data
        }
        version_ids.discard(None)

        output = collections.defaultdict(list)
        if not version_ids:
            return output

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
        return output

    @staticmethod
    def _get_loader(loaders, product_type):
        name = ""
        if product_type in {
            "rig", "model", "camera",
            "animation", "staticMesh",
            "skeletalMesh"}:
                name = "ReferenceLoader"

        if name == "":
            return None

        for loader in loaders:
            if loader.__name__ == name:
                return loader

        return None

    def _get_instance_name(self, instance_name):
        """
        Splits the given instance name and convert it into the asset name.

        Args:
        instance_name (str): Instance name.

        Returns:
        str: asset name.
        """
        pattern = r'([a-zA-Z]+)_(\d+|[a-zA-Z]+)'
        reg_matches = re.findall(pattern, instance_name)
        asset_name = '_'.join(['_'.join(match) for match in reg_matches])
        return asset_name

    def get_asset(self, containers, instance_name):
        # TODO: Improve this logic to support multiples of same asset
        #  and to avoid bugs with containers getting renamed by artists
        # Find container names that starts with 'instance name'
        asset_name = self._get_instance_name(instance_name)
        containers = [con for con in containers if con.startswith(asset_name)]
        # Get the highest root node from the loaded container
        for container in containers:
            members = get_container_members(container)
            transforms = cmds.ls(members, transforms=True)
            roots = get_highest_in_hierarchy(transforms)
            root = next(iter(roots), None)
            if root is not None:
                return root

    def _process_element(self, element, repre_entities_by_version_id):
        repre_id = None
        repr_format = None
        version_id = element.get("version")
        if version_id:
            repre_entities = repre_entities_by_version_id[version_id]
            if not repre_entities:
                self.log.error(
                    "No valid representation found for version"
                    f" {version_id}")
                return
            # always use the first representation to load
            # If reference is None, this element is skipped, as it cannot be
            # imported in Maya, repre_entities must always be the first one
            repre_entity = repre_entities[0]
            repre_id = repre_entity["id"]
            repr_format = repre_entity["name"]

        # If reference is None, this element is skipped, as it cannot be
        # imported in Maya
        if not repr_format:
            self.log.warning(f"Representation name not defined for element: {element}")
            return


        instance_name: str = element['instance_name']
        all_loaders = discover_loader_plugins()
        product_type = element.get("product_type")
        if product_type is None:
            product_type = element.get("family")
        loaders = loaders_from_representation(
            all_loaders, repre_id)

        loader = self._get_loader(loaders, product_type)

        if not loader:
            self.log.error(
                f"No valid loader found for {repre_id}")
            return
        options = {
            # "asset_dir": asset_dir
        }
        assets = load_container(
            loader,
            repre_id,
            namespace=instance_name,
            options=options
        )

        self.set_transformation(assets, element)
        return assets

    def set_transformation(self, assets, element):
        instance_name = element["instance_name"]
        asset = self.get_asset(assets, instance_name)
        unreal_import = True if "unreal" in element.get("host", []) else False
        if unreal_import:
            transform = element["transform"]
            self._set_transformation(asset, transform)
        else:
            transform = element["transform_matrix"]
            rotation = element["rotation"]
            # flatten matrix to a list
            maya_transform_matrix = [element for row in transform for element in row]
            self._convert_transformation_matrix(asset, maya_transform_matrix, rotation)

    def _set_transformation(self, asset, transform):
        translation = [
            transform["translation"]["x"],
            transform["translation"]["z"],
            transform["translation"]["y"]
            ]

        rotation = [
            math.degrees(transform["rotation"]["x"]),
            math.degrees(transform["rotation"]["z"]),
            math.degrees(transform["rotation"]["y"]),
        ]
        scale = [
            transform["scale"]["x"],
            transform["scale"]["z"],
            transform["scale"]["y"]
        ]
        print(asset, translation, rotation, scale)
        cmds.xform(
            asset,
            translation=translation,
            rotation=rotation,
            scale=scale
        )

    def _convert_transformation_matrix(self, asset, transform, rotation):
        """Convert matrix to list of transformation matrix for Unreal Engine import.

        Args:
            transform (list): Transformations of the asset
            rotation (list): Rotations of the asset

        Returns:
            List[om.MMatrix]: List of transformation matrix of the asset
        """
        transform_mm = om.MMatrix(transform)
        convert_transform = om.MTransformationMatrix(transform_mm)
        converted_rotation = om.MEulerRotation(
            math.radians(rotation["x"]), math.radians(rotation["y"]), math.radians(rotation["z"])
        )
        convert_transform.setRotation(converted_rotation)
        cmds.xform(asset, matrix=convert_transform.asMatrix())

    def load(self, context, name, namespace, options):
        path = self.filepath_from_context(context)
        self.log.info(f">>> loading json [ {path} ]")
        with open(path, "r") as fp:
            data = json.load(fp)

        # get the list of representations by using version id
        repre_entities_by_version_id = self._get_repre_entities_by_version_id(
            data
        )
        assets = []
        for element in data:
            elements = self._process_element(element, repre_entities_by_version_id)
            assets.extend(elements)

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

        existing_containers = get_container_members(container)
        # TODO: Supports to load non-existing containers
        for element in data:
            self.set_transformation(existing_containers, element)
        # Update metadata
        node = container["objectName"]
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