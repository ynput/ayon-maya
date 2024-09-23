from maya import cmds
import math
import json
import collections
import ayon_api
from ayon_maya.api import plugin
from ayon_maya.api.lib import unique_namespace
from ayon_core.pipeline import (
    load_container,
    get_representation_path,
    discover_loader_plugins,
    loaders_from_representation,
    get_current_project_name
)
from maya.api import OpenMaya as om
from ayon_maya.api.pipeline import containerise


class LayoutLoader(plugin.Loader):
    """Layout Loader(json)"""

    product_types = {"layout"}
    representations = {"json"}

    label = "Layout Loader(json)"
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

    def get_asset(self, instance_name):
        container = [
            con for con in cmds.ls(f"{instance_name}*")
            if con.endswith("_CON")
        ][0]
        namespace = cmds.getAttr(f"{container}.namespace")
        asset = [asset for asset in cmds.ls(f"{namespace}:*", assemblies=True)][0]
        return asset

    def _process_element(self, filepath, options, loaded_options=None):

        with open(filepath, "r") as fp:
            data = json.load(fp)

        all_loaders = discover_loader_plugins()

        if loaded_options is None:
            loaded_options = []

        # get the list of representations by using version id
        repre_entities_by_version_id = self._get_repre_entities_by_version_id(
            data
        )
        for element in data:
            repre_id = None
            repr_format = None
            version_id = element.get("version")
            if version_id:
                repre_entities = repre_entities_by_version_id[version_id]
                if not repre_entities:
                    self.log.error(
                        f"No valid representation found for version"
                        f" {version_id}")
                    continue
                extension = element.get("extension")
                # always use the first representation to load
                repre_entity = next((repre_entity for repre_entity in repre_entities
                                    if repre_entity["name"] == extension), None)
                repre_id = repre_entity["id"]
                repr_format = repre_entity["name"]

            # If reference is None, this element is skipped, as it cannot be
            # imported in Maya
            if not repre_id:
                continue

            instance_name = element.get('instance_name')
            containers = [
                con for con in cmds.ls(f"{instance_name}*")
                if con.endswith("_CON")
            ]
            if not containers:
                if repre_id not in loaded_options:
                    loaded_options.append(repre_id)

                    product_type = element.get("product_type")
                    if product_type is None:
                        product_type = element.get("family")
                    loaders = loaders_from_representation(
                        all_loaders, repre_id)

                    loader = None

                    if repr_format:
                        loader = self._get_loader(loaders, product_type)

                    if not loader:
                        self.log.error(
                            f"No valid loader found for {repre_id}")
                        continue

                    options = {
                        # "asset_dir": asset_dir
                    }
                    load_container(
                        loader,
                        repre_id,
                        namespace=instance_name,
                        options=options
                    )
                instances = [
                    item for item in data
                    if ((item.get('version') and
                        item.get('version') == element.get('version')))]

                for instance in instances:
                    transform = instance["transform_matrix"]
                    instance_name = instance["instance_name"]
                    rotation = instance["rotation"]
                    self.set_transformation(instance_name, transform, rotation)

    def set_transformation(self, instance_name, transform, rotation):
        asset = self.get_asset(instance_name)
        maya_transform_matrix = [element for row in transform for element in row]
        transform_matrix = self.convert_transformation_matrix(
            maya_transform_matrix, rotation)
        cmds.xform(asset, matrix=transform_matrix)

    def convert_transformation_matrix(self, transform, rotation):
        """Convert matrix to list of transformation matrix for Unreal Engine import.

        Args:
            transform (list): Transformations of the asset
            rotation (list): Rotations of the asset

        Returns:
            List[om.MMatrix]: List of transformation matrix of the asset
        """
        transform_mm = om.MMatrix(transform)
        convert_transform = om.MTransformationMatrix(transform_mm)
        print(rotation)
        converted_rotation = om.MEulerRotation(
            math.radians(rotation["x"]), math.radians(rotation["y"]), math.radians(rotation["z"])
        )
        convert_transform.setRotation(converted_rotation)

        return convert_transform.asMatrix()

    def load(self, context, name, namespace, options):

        path = self.filepath_from_context(context)

        self.log.info(">>> loading json [ {} ]".format(path))
        self._process_element(path, options)
        folder_name = context["folder"]["name"]
        namespace = namespace or unique_namespace(
            folder_name + "_",
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="_",
        )

        return containerise(
            name=name,
            namespace=namespace,
            nodes=[],
            context=context,
            loader=self.__class__.__name__)

    def update(self, container, context):
        repre_entity = context["representation"]
        path = get_representation_path(repre_entity)
        self._process_element(path, options=None)
        # Update metadata
        node = container["objectName"]
        cmds.setAttr("{}.representation".format(node),
                     repre_entity["id"],
                     type="string")

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        if container is not None:
            members = cmds.sets(container['objectName'], query=True)
            cmds.lockNode(members, lock=False)
            cmds.delete([container['objectName']] + members)

            # Clean up the namespace
            try:
                cmds.namespace(removeNamespace=container['namespace'],
                            deleteNamespaceContent=True)
            except RuntimeError:
                pass
