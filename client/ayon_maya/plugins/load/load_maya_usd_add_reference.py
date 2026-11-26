# -*- coding: utf-8 -*-
from maya import cmds

from ayon_maya.api import plugin


class MayaUsdProxyReferenceUsd(plugin.Loader):
    """Add a USD Reference to a prim in a Maya USD Proxy Shape stage.

    Select a USD prim in a Maya USD stage to add the reference to. With no
    USD prim selected a new stage is created and the reference is added to
    its `/root` prim.

    The AYON container data is stored in the `customData` of the added
    `Sdf.Reference` so that each loaded reference is its own container, even
    when multiple are loaded onto the same prim.

    """

    product_base_types = {"model", "usd", "pointcache", "animation"}
    product_types = product_base_types
    representations = {"*"}
    extensions = {"usd", "usda", "usdc", "usdz", "abc"}

    label = "USD Add Reference"
    order = 0
    icon = "code-fork"
    color = "orange"

    # Where the USD edits of a new stage are saved, defined in settings
    new_stage_usd_edits = "maya_scene"

    def load(self, context, name=None, namespace=None, options=None):
        # Make sure we can load the plugin
        cmds.loadPlugin("mayaUsdPlugin", quiet=True)

        from ayon_maya.api import usdlib

        ufe_path = usdlib.get_load_target_ufe_path(
            share_new_stage=self.new_stage_usd_edits == "maya_usd_preference"
        )
        prim = usdlib.ufe_path_to_prim(ufe_path)

        path = self.filepath_from_context(context)
        data = usdlib.get_container_data(
            loader=self.__class__.__name__,
            name=name,
            namespace=namespace or "",
            context=context,
        )
        proxy = ufe_path.split(",", 1)[0]
        return usdlib.add_reference_container(proxy, prim, path, data)

    def update(self, container, context):
        # type: (dict, dict) -> None
        """Update container with specified representation."""
        from ayon_maya.api import usdlib

        path = self.filepath_from_context(context)
        usdlib.update_reference_container(
            container,
            path=path,
            data={
                "representation": context["representation"]["id"],
                "project_name": context["project"]["name"],
            }
        )

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        # type: (dict) -> None
        """Remove loaded container."""
        from ayon_maya.api import usdlib

        usdlib.remove_reference_container(container)
