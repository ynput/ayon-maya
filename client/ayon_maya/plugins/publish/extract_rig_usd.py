# -*- coding: utf-8 -*-
"""Extract USD layer with a MayaReference prim for the published rig."""
import os

import pyblish.api
from ayon_core.pipeline.publish.lib import get_instance_expected_output_path
from ayon_maya.api import plugin

try:
    from pxr import Sdf
    from ayon_core.pipeline.usdlib import (
        get_or_define_prim_spec,
        get_standard_default_prim_name,
        set_layer_defaults,
    )
except ImportError:
    Sdf = None


def create_maya_reference_prim_spec(parent, prim_name, path, namespace):
    """Create a `MayaReference` prim spec that references a Maya scene file.

    Maya USD can load these prims as regular Maya references.

    Arguments:
        parent (Sdf.PrimSpec): Parent prim spec.
        prim_name (str): Name of the prim to create.
        path (str): Path to the Maya scene file (.ma or .mb).
        namespace (str): Namespace to use when loading the reference.

    Returns:
        Sdf.PrimSpec: The created prim spec.

    """
    prim_spec = Sdf.PrimSpec(
        parent, prim_name, Sdf.SpecifierDef, "MayaReference"
    )
    reference_spec = Sdf.AttributeSpec(
        prim_spec, "mayaReference", Sdf.ValueTypeNames.Asset)
    reference_spec.default = Sdf.AssetPath(path)
    auto_edit_spec = Sdf.AttributeSpec(
        prim_spec, "mayaAutoEdit", Sdf.ValueTypeNames.Bool)
    auto_edit_spec.default = False
    namespace_spec = Sdf.AttributeSpec(
        prim_spec, "mayaNamespace", Sdf.ValueTypeNames.String)
    namespace_spec.default = namespace
    return prim_spec


class ExtractRigUSD(plugin.MayaExtractorPlugin):
    """Extract a USD layer referencing the published rig Maya scene.

    The layer contains a `MayaReference` prim so that the rig can be
    contributed into a USD asset by the USD layer contribution workflow.
    """

    label = "Extract Rig (USD MayaReference)"
    families = ["rig"]
    # Run right after ExtractRig, before the USD contribution extractors
    order = pyblish.api.ExtractorOrder + 0.01

    def process(self, instance):
        if "usd" not in instance.data.get("families", []):
            return

        if Sdf is None:
            self.log.warning("USD is not available; skipping USD extraction.")
            return

        # Find the rig scene representation published by ExtractRig
        rig_repre = next(
            (
                repre for repre in instance.data.get("representations", [])
                if repre["name"] in {"ma", "mb"}
            ),
            None
        )
        if rig_repre is None:
            self.log.warning(
                "No Maya scene representation found; skipping USD "
                "MayaReference extraction.")
            return

        rig_path = get_instance_expected_output_path(
            instance,
            representation_name=rig_repre["name"],
            ext=rig_repre["ext"]
        )
        rig_path = str(rig_path).replace("\\", "/")

        folder_path = instance.data["folderPath"]
        default_prim = get_standard_default_prim_name(folder_path)
        product_name = instance.data["productName"]

        layer = Sdf.Layer.CreateAnonymous()
        set_layer_defaults(layer, default_prim=default_prim)
        root_spec = get_or_define_prim_spec(
            layer, Sdf.Path(f"/{default_prim}"), "Xform")
        create_maya_reference_prim_spec(
            root_spec,
            prim_name=product_name,
            path=rig_path,
            namespace=product_name
        )

        staging_dir = self.staging_dir(instance)
        filename = f"{instance.name}.usd"
        filepath = os.path.join(staging_dir, filename)
        layer.Export(filepath, args={"format": "usda"})

        instance.data.setdefault("representations", []).append({
            "name": "usd",
            "ext": "usd",
            "files": filename,
            "stagingDir": staging_dir,
        })
        self.log.debug("Extracted rig USD MayaReference to: %s", filepath)
