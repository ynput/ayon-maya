from maya import cmds
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
        if product_type in {"rig", "model", "camera", "animation"}:
            name = "ReferenceLoader"

        if name == "":
            return None

        for loader in loaders:
            if loader.__name__ == name:
                return loader

        return None


    def _process(self, filepath, options, loaded_options=None):

        with open(filepath, "r") as fp:
            data = json.load(fp)

        all_loaders = discover_loader_plugins()

        if not loaded_options:
            loaded_options = []

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
                repre_entity = repre_entities[0]
                repre_id = repre_entity["id"]
                repr_format = repre_entity["name"]


            # If reference is None, this element is skipped, as it cannot be
            # imported in Maya
            if not repre_id:
                continue

            instance_name = element.get('asset_name')

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
                assets = [asset for asset in cmds.ls(f"{instance_name}*")
                          if asset.endswith("_CON")]
                if not assets:
                    assets = load_container(
                        loader,
                        repre_id,
                        namespace=instance_name,
                        options=options
                    )
                    if not assets:
                        return []
                instances = [
                    item for item in data
                    if ((item.get('version') and
                        item.get('version') == element.get('version')))]

                for instance in instances:
                    transform = instance.get('transform')

                return assets

    def load(self, context, name, namespace, options):

        path = self.filepath_from_context(context)

        self.log.info(">>> loading json [ {} ]".format(path))
        asset = self._process(path, options)
        folder_name = context["folder"]["name"]
        namespace = namespace or unique_namespace(
            folder_name + "_",
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="_",
        )
        print(asset)
        # TODO: implement the function to load all the assets and set transforms
        return containerise(
            name=name,
            namespace=namespace,
            nodes=[],
            context=context,
            loader=self.__class__.__name__)

    def update(self, container, context):
        repre_entity = context["representation"]
        path = get_representation_path(repre_entity)
        # Update metadata
        node = container["objectName"]
        cmds.setAttr("{}.representation".format(node),
                     repre_entity["id"],
                     type="string")
        self.log.info("... updated")

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
