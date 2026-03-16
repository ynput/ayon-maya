# -*- coding: utf-8 -*-
import uuid

from ayon_core.pipeline import load
from ayon_core.pipeline.load import get_representation_path_from_context
from ayon_maya.api.usdlib import (
    containerise_prim,
    iter_ufe_usd_selection
)

from maya import cmds
import mayaUsd


def _get_stage_from_shape(shape_long):
    """Retrieve USD stage from a mayaUsdProxyShape via its stage cache ID.

    Args:
        shape_long (str): Full DAG path to the mayaUsdProxyShape node.

    Returns:
        pxr.Usd.Stage
    """
    from pxr import UsdUtils

    # The proxy shape stores the stage cache ID on the outStageCacheId plug
    cache_id_val = cmds.getAttr(shape_long + ".outStageCacheId")
    cache_id = UsdUtils.StageCache.Id.FromLongInt(int(cache_id_val))
    stage = UsdUtils.StageCache.Get().Find(cache_id)
    if not stage:
        raise RuntimeError(
            f"Could not retrieve stage from cache for shape: {shape_long}\n"
            f"Cache ID was: {cache_id_val}"
        )
    return stage


def _create_stage_with_new_layer():
    """Create a new mayaUsdProxyShape stage and return (shape_long, stage)."""
    cmds.loadPlugin("mayaUsdPlugin", quiet=True)

    try:
        import mayaUsd_createStageWithNewLayer
        shape = mayaUsd_createStageWithNewLayer.createStageWithNewLayer()
    except Exception:
        parent = cmds.createNode("transform", name="stage")
        shape = mayaUsd.ufe.createStageWithNewLayer(parent)

    shape_long = cmds.ls(shape, long=True)
    if not shape_long:
        raise RuntimeError(f"Could not find created proxy shape: {shape}")

    stage = _get_stage_from_shape(shape_long[0])
    return shape_long[0], stage


class MayaUsdProxyReferenceUsd(load.LoaderPlugin):
    """Add a USD Reference into mayaUsdProxyShape

    TODO: It'd be much easier if this loader would be capable of returning the
        available containers in the scene based on the AYON URLs inside a USD
        stage. That way we could potentially avoid the need the custom
        identifier, stay closer to USD native data and rely solely on the
        AYON:asset=blue,subset=modelMain,version=1 url

    """

    product_types = {"model", "usd", "pointcache", "animation"}
    representations = ["usd", "usda", "usdc", "usdz", "abc"]

    label = "USD Add Reference"
    order = 0
    icon = "code-fork"
    color = "orange"

    identifier_key = "ayon_identifier"

    def load(self, context, name=None, namespace=None, options=None):

        from pxr import Sdf

        selection = list(iter_ufe_usd_selection())
        if not selection:
            from pxr import UsdGeom

            _shape_long, stage = _create_stage_with_new_layer()

            prim_path = "/root"
            UsdGeom.Xform.Define(stage, prim_path)
            root_layer = stage.GetRootLayer()
            root_layer.defaultPrim = prim_path
            prim = stage.GetPrimAtPath(prim_path)
        else:
            assert len(selection) == 1, "Select only one PRIM please"
            ufe_path = selection[0]
            prim = mayaUsd.ufe.ufePathToPrim(ufe_path)

        if not prim:
            raise RuntimeError("Invalid primitive")

        path = get_representation_path_from_context(context)
        references = prim.GetReferences()

        identifier = str(prim.GetPath()) + ":" + str(uuid.uuid4())
        identifier_data = {self.identifier_key: identifier}
        reference = Sdf.Reference(assetPath=path,
                                  customData=identifier_data)

        success = references.AddReference(reference)
        if not success:
            raise RuntimeError("Failed to add reference")

        container = containerise_prim(
            prim,
            name=name,
            namespace=namespace or "",
            context=context,
            loader=self.__class__.__name__
        )

        return container

    def update(self, container, context):
        # type: (dict, dict) -> None
        """Update container with specified representation."""

        from pxr import Sdf

        prim = container["prim"]
        path = self.filepath_from_context(context)
        for references, index in self._get_prim_references(prim):
            reference = references[index]
            new_reference = Sdf.Reference(
                assetPath=path,
                customData=reference.customData,
                layerOffset=reference.layerOffset,
                primPath=reference.primPath
            )
            references[index] = new_reference

        prim.SetCustomDataByKey(
            "ayon:representation", context["representation"]["id"]
        )

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        # type: (dict) -> None
        """Remove loaded container."""
        prim = container["prim"]

        related_references = reversed(list(self._get_prim_references(prim)))
        for references, index in related_references:
            references.remove(references[index])

        prim.ClearCustomDataByKey("ayon")

    def _get_prim_references(self, prim):

        for prim_spec in prim.GetPrimStack():
            if not prim_spec:
                continue

            if not prim_spec.hasReferences:
                continue

            prepended_items = prim_spec.referenceList.prependedItems
            for index, _reference in enumerate(prepended_items):
                yield prepended_items, index
