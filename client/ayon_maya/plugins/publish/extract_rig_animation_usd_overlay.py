# -*- coding: utf-8 -*-
"""Extract USD overlay that adds the rig animation as variant on the asset."""
import os

import pyblish.api
from ayon_core.pipeline import KnownPublishError
from ayon_core.pipeline.publish.lib import get_instance_expected_output_path
from ayon_maya.api import plugin
from ayon_maya.api.lib import (
    USD_RIG_ANIMATION_CREATOR_ID,
    get_usd_maya_reference_for_nodes,
)

try:
    from pxr import Sdf, Vt
except ImportError:
    Sdf = None

VARIANT_SET_NAME = "Animation"
# Representation name of the extracted animation cache
CACHE_REPRESENTATION = "usd_anim"
CACHE_OUTPUT_NAME = "anim"
RESET_XFORM_STACK = "!resetXformStack!"


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

    A cache that is exported in world space resets the transform stack on
    its roots so that the transforms of the asset prim and its parents,
    e.g. from layout, are not applied again.
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

        reference = get_usd_maya_reference_for_nodes(instance[:])
        if reference is None and (
            instance.data.get("creator_identifier")
            != USD_RIG_ANIMATION_CREATOR_ID
        ):
            self.log.debug(
                "Rig was not loaded through a USD MayaReference prim; "
                "skipping USD overlay.")
            return

        representations = instance.data.setdefault("representations", [])
        cache_repre = next(
            (r for r in representations
             if r["name"] == "usd" and r["ext"] == "usd"),
            None
        )

        error = None
        if reference is None:
            error = (
                "The rig is not related to a MayaReference prim of a loaded "
                "USD so its animation can not be overlaid onto a USD asset."
            )
        elif cache_repre is None:
            error = (
                "No USD animation cache was extracted to overlay onto the "
                "USD asset. Enable 'Extract USD Animation' for the instance."
            )
        if error:
            # Without the overlay the USD contribution would add an invalid
            # layer, so only allow that if the instance does not contribute.
            if self.is_usd_contribution_enabled(instance):
                raise KnownPublishError(error)
            self.log.warning("%s Skipping USD overlay.", error)
            return

        # Rename the cache representation so `usd` becomes the overlay.
        cache_repre["name"] = CACHE_REPRESENTATION
        cache_repre["outputName"] = CACHE_OUTPUT_NAME
        cache_source = os.path.join(
            cache_repre["stagingDir"], cache_repre["files"])
        cache_layer = Sdf.Layer.FindOrOpen(cache_source)
        if cache_layer is None:
            raise KnownPublishError(
                f"Unable to open USD animation cache: {cache_source}")

        variant_name = instance.data["productName"]
        layer = Sdf.Layer.CreateAnonymous()
        # Match the time scaling of the cache
        for key in ("timeCodesPerSecond", "framesPerSecond"):
            if cache_layer.pseudoRoot.HasInfo(key):
                layer.pseudoRoot.SetInfo(
                    key, cache_layer.pseudoRoot.GetInfo(key))

        asset_spec = Sdf.CreatePrimInLayer(
            layer, Sdf.Path(reference.asset_prim_path))
        asset_spec.specifier = Sdf.SpecifierOver
        asset_spec.variantSetNameList.Prepend(VARIANT_SET_NAME)
        variant_set = Sdf.VariantSetSpec(asset_spec, VARIANT_SET_NAME)
        variant = Sdf.VariantSpec(variant_set, variant_name)
        asset_spec.variantSelections[VARIANT_SET_NAME] = variant_name
        cache_path = self.get_expected_cache_path(instance)
        worldspace = self.is_cache_in_worldspace(instance)
        for root_spec in cache_layer.rootPrims:
            child = Sdf.PrimSpec(
                variant.primSpec, root_spec.name, Sdf.SpecifierOver)
            child.referenceList.Prepend(
                Sdf.Reference(cache_path, root_spec.path)
            )
            if not worldspace:
                continue

            # The transform of the root is in world space, so it must not
            # inherit the transforms of the prims it is overlaid under.
            order_spec = root_spec.attributes.get("xformOpOrder")
            order = list(order_spec.default or []) if order_spec else []
            if RESET_XFORM_STACK not in order:
                order.insert(0, RESET_XFORM_STACK)
            Sdf.AttributeSpec(
                child,
                "xformOpOrder",
                Sdf.ValueTypeNames.TokenArray,
                Sdf.VariabilityUniform
            ).default = Vt.TokenArray(order)

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

    @staticmethod
    def is_usd_contribution_enabled(instance):
        """Return whether the instance contributes to a USD layer."""
        attr_values = instance.data.get("publish_attributes", {}).get(
            "CollectUSDLayerContributions", {})
        return bool(attr_values.get("contribution_enabled"))

    @staticmethod
    def is_cache_in_worldspace(instance):
        """Return whether the USD animation cache is exported in worldspace"""
        attr_values = instance.data.get("publish_attributes", {}).get(
            "ExtractMayaUsdAnim", {})
        return bool(attr_values.get("worldspace", True))

    @staticmethod
    def get_expected_cache_path(instance):
        """Return the expected publish path of the animation cache."""
        # The `outputName` of the representation is formatted in the publish
        # template as `output`, for which there is no argument.
        anatomy_data = instance.data["anatomyData"]
        output = anatomy_data.get("output")
        anatomy_data["output"] = CACHE_OUTPUT_NAME
        try:
            path = get_instance_expected_output_path(
                instance,
                representation_name=CACHE_REPRESENTATION,
                ext="usd"
            )
        finally:
            if output is None:
                del anatomy_data["output"]
            else:
                anatomy_data["output"] = output
        return str(path).replace("\\", "/")
