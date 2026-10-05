# -*- coding: utf-8 -*-
"""Extract USD overlay that adds the rig animation as variant on the asset."""
import os

import pyblish.api
from ayon_core.pipeline import publish
from ayon_core.pipeline.publish.lib import get_instance_expected_output_path
from ayon_maya.api import plugin
from ayon_maya.api.lib import get_usd_maya_reference_for_nodes

try:
    from pxr import Sdf
except ImportError:
    Sdf = None

VARIANT_SET_NAME = "Animation"
# Representation name of the extracted animation cache
CACHE_REPRESENTATION = "usd_anim"
CACHE_OUTPUT_NAME = "anim"


class ExtractRigAnimationUsdOverlay(plugin.MayaExtractorPlugin):
    """Overlay animation cache onto the USD asset that embeds the rig.

    For animation instances of rigs loaded through a USD `MayaReference`
    prim (see `CreateUsdRigAnimation`) this turns the extracted animation
    USD cache (from `Extract USD Animation`, which must be enabled) into a
    contribution layer:

        over "<asset prim>" (variantSet "Animation") {
            variant "<product name>" {
                over "<root>" (references = <animation cache>) {}
            }
        }

    The `usd` representation is that overlay layer so that the USD layer
    contributions can add it into e.g. the shot's animation layer. The
    animation cache itself is published as the `usd_anim` representation
    and is referenced by the overlay.
    """

    label = "Extract Rig Animation (USD Overlay)"
    families = ["animation"]
    # Run right after `ExtractMayaUsdAnim`
    order = pyblish.api.ExtractorOrder + 0.01

    def process(self, instance):
        if "usd" not in instance.data.get("families", []):
            return

        if instance.data.get("farm"):
            self.log.debug("Should be processed on farm, skipping.")
            return

        if Sdf is None:
            self.log.warning("USD is not available; skipping.")
            return

        representations = instance.data.setdefault("representations", [])
        cache_repre = next(
            (r for r in representations
             if r["name"] == "usd" and r["ext"] == "usd"),
            None
        )
        if cache_repre is None:
            self.log.warning(
                "No USD animation cache found. Enable 'Extract USD "
                "Animation' to publish the rig animation as USD overlay.")
            return

        reference = get_usd_maya_reference_for_nodes(instance[:])
        if reference is None:
            self.log.warning(
                "Rig of instance '%s' was not loaded through a USD "
                "MayaReference prim; skipping USD overlay.", instance.name)
            return

        # Rename the cache representation so `usd` becomes the overlay.
        cache_repre["name"] = CACHE_REPRESENTATION
        cache_repre["outputName"] = CACHE_OUTPUT_NAME
        cache_file = cache_repre["files"]
        cache_source = os.path.join(cache_repre["stagingDir"], cache_file)

        overlay_path = get_instance_expected_output_path(
            instance, representation_name="usd", ext="usd")
        base, ext = os.path.splitext(overlay_path)
        cache_path = f"{base}_{CACHE_OUTPUT_NAME}{ext}"
        cache_path = cache_path.replace("\\", "/")

        cache_layer = Sdf.Layer.FindOrOpen(cache_source)
        if cache_layer is None:
            self.log.error("Unable to open animation cache: %s", cache_source)
            return
        root_names = [prim.name for prim in cache_layer.rootPrims]

        variant_name = instance.data["productName"]
        layer = Sdf.Layer.CreateAnonymous()
        asset_spec = Sdf.CreatePrimInLayer(
            layer, Sdf.Path(reference.asset_prim_path))
        asset_spec.specifier = Sdf.SpecifierOver
        asset_spec.variantSetNameList.Prepend(VARIANT_SET_NAME)
        variant_set = Sdf.VariantSetSpec(asset_spec, VARIANT_SET_NAME)
        variant = Sdf.VariantSpec(variant_set, variant_name)
        asset_spec.variantSelections[VARIANT_SET_NAME] = variant_name
        for root_name in root_names:
            child = Sdf.PrimSpec(
                variant.primSpec, root_name, Sdf.SpecifierOver)
            child.referenceList.Prepend(
                Sdf.Reference(cache_path, Sdf.Path(f"/{root_name}"))
            )

        staging_dir = self.staging_dir(instance)
        filename = f"{instance.name}_overlay.usd"
        layer.Export(os.path.join(staging_dir, filename),
                     args={"format": "usda"})
        representations.append({
            "name": "usd",
            "ext": "usd",
            "files": filename,
            "stagingDir": staging_dir,
        })
        self.log.debug(
            "Extracted USD animation overlay for '%s' onto '%s'",
            variant_name, reference.asset_prim_path)
