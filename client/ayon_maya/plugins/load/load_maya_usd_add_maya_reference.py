# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

from maya import cmds

from ayon_core.pipeline.load import LoadError
from ayon_maya.api import plugin
from ayon_maya.api.lib import unique_namespace


class MayaUsdProxyAddMayaReferenceLoader(plugin.Loader):
    """Add a Maya Reference prim to a Maya USD Proxy Shape stage.

    Select a USD prim in a Maya USD stage to add the MayaReference prim under.
    With no USD prim selected a new stage is created and the MayaReference
    prim is added under its `/root` prim.

    The AYON container data is stored in the `customData` of the created
    MayaReference prim.

    """

    product_base_types = {"*"}
    product_types = product_base_types
    representations = {"*"}
    extensions = {"ma", "mb"}

    label = "USD Add Maya Reference"
    order = 1
    icon = "code-fork"
    color = "orange"

    def load(self, context, name=None, namespace=None, options=None):
        # Make sure we can load the plugin
        cmds.loadPlugin("mayaUsdPlugin", quiet=True)

        import mayaUsd.ufe
        import mayaUsdAddMayaReference
        from pxr import Tf
        from ayon_maya.api import usdlib

        ufe_path = usdlib.get_load_target_ufe_path()
        parent_prim = usdlib.ufe_path_to_prim(ufe_path)

        folder_name = context["folder"]["name"]
        namespace = namespace or unique_namespace(
            folder_name + "_",
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="_",
        )
        prim_name = mayaUsd.ufe.uniqueChildName(
            parent_prim, Tf.MakeValidIdentifier(f"{folder_name}_{name}")
        )

        path = self.filepath_from_context(context)
        prim = mayaUsdAddMayaReference.createMayaReferencePrim(
            ufe_path,
            path,
            namespace,
            mayaReferencePrimName=prim_name,
            # TODO: Expose more of the arguments as load options
            # groupPrim (3-tuple, group name, type and kind)
            # variantSet (2-tuple, variant set name and variant name)
        )
        if not prim or not prim.IsValid():
            raise RuntimeError(
                f"Failed to add a Maya reference prim at: {ufe_path}"
            )

        data = usdlib.get_container_data(
            loader=self.__class__.__name__,
            name=name,
            namespace=namespace,
            context=context,
        )
        proxy = ufe_path.split(",", 1)[0]
        return usdlib.imprint_prim_container(proxy, prim, data)

    def _update_reference_path(self, prim, filepath):
        """Update MayaReference prim 'mayaReference' in nearest prim spec"""

        from pxr import Sdf

        # We want to update the authored opinion in the right place, e.g.
        # within a VariantSet if it's authored there. We go through the
        # PrimStack to find the first prim spec that authors an opinion
        # on the 'mayaReference' attribute where we have permission to
        # change it. This could technically mean we're altering it in
        # layers that we might not want to (e.g. a published USD file?)
        stack = prim.GetPrimStack()
        for prim_spec in stack:
            if "mayaReference" not in prim_spec.attributes:
                # prim spec defines no opinion on mayaReference attribute?
                continue

            attr = prim_spec.attributes["mayaReference"]
            if (
                attr.permission != Sdf.PermissionPublic
                or not prim_spec.layer.permissionToEdit
            ):
                self.log.debug(f"Not allowed to edit: {attr.path}")
                continue

            if filepath != attr.default:
                self.log.debug(
                    f"Updating {attr.path} - {attr.default} -> {filepath}")
                attr.default = filepath

            # Attribute is either updated or already set to
            # the value in that layer
            return

        # Just define in the current edit layer?
        attr = prim.GetAttribute("mayaReference")
        attr.Set(filepath)

    def update(self, container, context):
        # type: (dict, dict) -> None
        """Update container with specified representation."""
        from ayon_maya.api import usdlib

        prim = self._get_prim(container)
        filepath = self.filepath_from_context(context)
        self._update_reference_path(prim, filepath)

        # When edited as Maya data, update the Maya reference itself so the
        # artist's edits are kept
        pulled_node = self._get_pulled_node(prim)
        if pulled_node:
            reference_node = cmds.listConnections(
                f"{pulled_node}.message", type="reference", source=False
            )
            if not reference_node:
                raise LoadError(
                    f"No Maya reference found for: {pulled_node}")
            cmds.file(filepath, loadReference=reference_node[0])

        usdlib.update_prim_container(container, {
            "representation": context["representation"]["id"],
            "project_name": context["project"]["name"],
        })

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        # type: (dict) -> None
        """Remove loaded container."""
        from ayon_maya.api import usdlib

        stage = usdlib.get_proxy_stage(container["proxy"])
        prim = stage.GetPrimAtPath(container["prim_path"]) if stage else None
        if not prim:
            # The prim is not composed, e.g. it is in an unselected variant
            self._remove_prim_specs(container, composed_only=False)
            return

        pulled_node = self._get_pulled_node(prim)
        if pulled_node:
            cmds.mayaUsdDiscardEdits(pulled_node)
        self._remove_prim_specs(container, composed_only=True)

    @staticmethod
    def _remove_prim_specs(container, composed_only):
        from ayon_maya.api import usdlib

        prim_specs = list(
            usdlib.iter_container_prim_specs(container, composed_only)
        )
        for prim_spec in prim_specs:
            usdlib.ensure_layer_editable(prim_spec.layer)
        for prim_spec in prim_specs:
            usdlib.remove_spec(prim_spec)

    @staticmethod
    def _get_prim(container):
        from ayon_maya.api import usdlib

        return usdlib.ufe_path_to_prim(container["objectName"])

    @staticmethod
    def _get_pulled_node(prim) -> Optional[str]:
        """Return the Maya node of the prim if it is edited as Maya data."""
        import mayaUsd.lib

        return mayaUsd.lib.PrimUpdaterManager.readPullInformation(prim) or None
