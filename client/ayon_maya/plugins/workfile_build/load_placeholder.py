from __future__ import annotations
from maya import cmds

from ayon_core.pipeline.workfile.workfile_template_builder import (
    PlaceholderLoadMixin,
    LoadPlaceholderItem
)
from ayon_maya.api.lib import (
    get_container_transforms,
    get_node_parent,
    get_node_index_under_parent
)
from ayon_maya.api.workfile_template_builder import (
    MayaPlaceholderPlugin,
)


class MayaPlaceholderLoadPlugin(MayaPlaceholderPlugin, PlaceholderLoadMixin):
    identifier = "maya.load"
    label = "Maya load"

    item_class = LoadPlaceholderItem

    def _create_placeholder_name(self, placeholder_data):

        # Split builder type: context_assets, linked_assets, all_assets
        prefix, suffix = placeholder_data["builder_type"].split("_", 1)
        parts = [prefix]

        # add family if any
        placeholder_product_type = placeholder_data.get("product_type")
        if placeholder_product_type is None:
            placeholder_product_type = placeholder_data.get("family")

        if placeholder_product_type:
            parts.append(placeholder_product_type)

        # add loader arguments if any
        loader_args = placeholder_data["loader_args"]
        if loader_args:
            loader_args = eval(loader_args)
            for value in loader_args.values():
                parts.append(str(value))

        parts.append(suffix)
        placeholder_name = "_".join(parts)

        return placeholder_name.capitalize()

    def _get_loaded_repre_ids(self):
        loaded_representation_ids = self.builder.get_shared_populate_data(
            "loaded_representation_ids"
        )
        if loaded_representation_ids is None:
            try:
                containers = cmds.sets("AVALON_CONTAINERS", q=True)
            except ValueError:
                containers = []

            loaded_representation_ids = {
                cmds.getAttr(container + ".representation")
                for container in containers
            }
            self.builder.set_shared_populate_data(
                "loaded_representation_ids", loaded_representation_ids
            )
        return loaded_representation_ids

    def populate_placeholder(self, placeholder):
        self.populate_load_placeholder(placeholder)

    def repopulate_placeholder(self, placeholder):
        repre_ids = self._get_loaded_repre_ids()
        self.populate_load_placeholder(placeholder, repre_ids)

    def get_placeholder_options(self, options=None):
        return self.get_load_plugin_options(options)

    def load_succeed(self, placeholder, container):
        self._parent_in_hierarchy(placeholder, container)

    def _parent_in_hierarchy(self, placeholder, container):
        """Parent loaded container to placeholder's parent.

        ie : Set loaded content as placeholder's sibling

        Args:
            container (str): Placeholder loaded containers
        """

        if not container:
            return

        container_roots: list[str] = get_container_transforms(
            container, root=True
        )

        roots: list[str] = []
        for container_root in container_roots:
            # Bugfix: The get_container_transforms does not recognize the load
            # reference group currently
            # TODO: Remove this when it does
            parent = get_node_parent(container_root)
            if parent:
                container_root = parent

            roots.append(container_root)

        # Add the loaded roots to the holding sets if they exist
        holding_sets = cmds.listSets(object=placeholder.scene_identifier) or []
        for holding_set in holding_sets:
            cmds.sets(roots, forceElement=holding_set)

        # Parent the roots to the place of the placeholder locator and match
        # its matrix
        placeholder_form = cmds.xform(
            placeholder.scene_identifier,
            query=True,
            matrix=True,
            worldSpace=True
        )
        scene_parent = get_node_parent(placeholder.scene_identifier)
        for node in set(roots):
            cmds.xform(node, matrix=placeholder_form, worldSpace=True)

            if scene_parent != get_node_parent(node):
                if scene_parent:
                    node = cmds.parent(node, scene_parent)[0]
                else:
                    node = cmds.parent(node, world=True)[0]

            # Move loaded nodes in index order next to their placeholder node
            cmds.reorder(node, back=True)
            index = get_node_index_under_parent(placeholder.scene_identifier)
            cmds.reorder(node, front=True)
            cmds.reorder(node, relative=index + 1)
