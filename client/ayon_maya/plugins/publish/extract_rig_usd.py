import os

import pyblish.api
from ayon_core.pipeline import PublishError
from ayon_core.pipeline.publish.lib import get_instance_expected_output_path
from ayon_maya.api import plugin

try:
    from pxr import Sdf
    has_usd = True
except ImportError:
    has_usd = False


def create_maya_reference_prim_spec(
    parent: "Sdf.PrimSpecHandle",
    prim_name: str,
    path: str,
    namespace: str
):
    """Create MayaReference Prim Spec under parent"""

    prim_spec = Sdf.PrimSpec(
        parent,
        prim_name,
        Sdf.SpecifierDef,
        "MayaReference"
    )
    reference_spec = Sdf.AttributeSpec(
        prim_spec, "mayaReference", Sdf.ValueTypeNames.Asset)
    reference_spec.default = path

    auto_edit_spec = Sdf.AttributeSpec(
        prim_spec, "mayaAutoEdit", Sdf.ValueTypeNames.Bool)
    auto_edit_spec.default = False

    namespace_spec = Sdf.AttributeSpec(
        prim_spec, "mayaNamespace", Sdf.ValueTypeNames.String)
    namespace_spec.default = namespace

    return prim_spec


class ExtractRigUSD(plugin.MayaExtractorPlugin):
    """Generate USD file for USD asset contribution"""

    # Run after CollectUSDLayerContributionsMayaRig in `ayon-core`
    order = pyblish.api.ExtractorOrder + 0.1
    label = "Extract Rig USD"
    families = ["rig"]
    enabled = has_usd

    def process(self, instance):
        if not instance.data.get("has_usd_contribution", False):
            return

        rig_published_filepath = self.get_maya_rig_published_path(instance)

        # Create required hierarchy
        # {folder[name]/rig/{product_name} - for example `hero/rig/rigMain`
        product_name = instance.data["productName"]

        # Generate the USD data
        layer = Sdf.Layer.CreateAnonymous()
        folder_name = instance.data["folderEntity"]["name"]
        asset_prim_root = Sdf.PrimSpec(
            layer.pseudoRoot,
            folder_name,
            Sdf.SpecifierDef,
            "Xform"
        )
        rig_prim_root = Sdf.PrimSpec(
            asset_prim_root,
            "rig",
            Sdf.SpecifierDef,
            "Scope"
        )
        create_maya_reference_prim_spec(
            rig_prim_root,
            prim_name=product_name,
            path=rig_published_filepath,
            namespace=folder_name
        )

        # Write the output USD file
        staging_dir = self.staging_dir(instance)
        filename = f"{instance.name}.usd"
        path = os.path.join(staging_dir, filename)
        layer.Export(path)

        # Add the representation
        representation = {
            'name': "usd",
            'ext': "usd",
            'files': filename,
            "stagingDir": staging_dir
        }
        instance.data.setdefault("representations", []).append(representation)

    def get_maya_rig_published_path(self, instance):
        # We need to reference the relative published `.ma` file for this
        # instance; either by AYON Entity URI if enabled, otherwise by
        # relative path to the published file.
        # TODO: The rig file may be either `ma` or `mb` representation. We
        #  should support both.

        representations = instance.data["representations"]
        for repre in representations:
            if repre["name"] in {"ma", "mb"}:
                rig_maya_repre: dict = repre
                break
        else:
            raise PublishError(
                "Unable to find rig maya scene representation in"
                f" {representations}")

        rig_published_filepath: str = get_instance_expected_output_path(
            instance,
            representation_name=rig_maya_repre["name"],
            ext=rig_maya_repre.get("ext"),
        )

        usd_published_filepath: str = get_instance_expected_output_path(
            instance,
            representation_name="usd",
            ext="usd"
        )

        relative_path = os.path.relpath(
            rig_published_filepath,
            start=os.path.dirname(usd_published_filepath))
        return f"./{relative_path}"  # usd anchored relative path
