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
    """Retrieve USD stage from a mayaUsdProxyShape node.

    Matches the stage by comparing the root layer identifier stored on the
    proxy shape's filePath attribute against all stages in the USD StageCache.

    Args:
        shape_long (str): Full DAG path to the mayaUsdProxyShape node.

    Returns:
        pxr.Usd.Stage
    """
    from pxr import UsdUtils

    cache = UsdUtils.StageCache.Get()
    all_stages = cache.GetAllStages()
    if not all_stages:
        raise RuntimeError(
            "USD StageCache is empty after creating proxy shape. "
            "The stage may not have been registered yet."
        )

    # The most recently created stage will be last in the cache
    # Match by checking the proxy shape's stageCacheId attribute
    try:
        cache_id_val = int(cmds.getAttr(shape_long + ".outStageCacheId"))
        for stage in all_stages:
            if cache.GetId(stage).ToLongInt() == cache_id_val:
                return stage
    except Exception:
        pass

    # Fallback: return the most recently added stage
    return list(all_stages)[-1]


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


def _prim_path_from_context(context):
    """Build a USD prim path from the AYON load context.

    Uses the folder hierarchy to mirror the project structure in USD:
        /assets/characters/cone_character
        /assets/props/rock
        /shots/sq010/sh010

    Args:
        context (dict): AYON load context.

    Returns:
        str: USD prim path string.
    """
    folder = context.get("folder", {})
    path = folder.get("path", "")  # e.g. "/assets/characters/cone_character"

    if path:
        # Sanitize: replace spaces/dashes with underscores, ensure no
        # double slashes, strip trailing slash
        import re
        prim_path = re.sub(r"[^a-zA-Z0-9_/]", "_", path).rstrip("/")
        if not prim_path.startswith("/"):
            prim_path = "/" + prim_path
        return prim_path

    # Fallback: use asset name only
    asset_name = folder.get("name", context.get("asset", "asset"))
    return "/" + asset_name


class MayaUsdProxyReferenceUsd(load.LoaderPlugin):
    """Add a USD Reference into mayaUsdProxyShape

    Builds the prim path from the AYON folder hierarchy so the USD structure
    mirrors the project organisation:
        /assets/characters/cone_character
        /assets/props/rock

    """

    product_types = {"model", "usd", "pointcache", "animation"}
    representations = ["usd", "usda", "usdc", "usdz", "abc"]

    label = "USD Add Reference"
    order = 0
    icon = "code-fork"
    color = "orange"

    identifier_key = "ayon_identifier"

    def load(self, context, name=None, namespace=None, options=None):

        from pxr import Sdf, UsdGeom

        selection = list(iter_ufe_usd_selection())
        if not selection:
            _shape_long, stage = _create_stage_with_new_layer()
            root_layer = stage.GetRootLayer()

            # Use project path as prim path, define each ancestor
            prim_path = _prim_path_from_context(context)
            self._define_prim_hierarchy(stage, prim_path)
            root_layer.defaultPrim = prim_path.strip("/").split("/")[0]
            prim = stage.GetPrimAtPath(prim_path)
        else:
            assert len(selection) == 1, "Select only one PRIM please"
            ufe_path = selection[0]
            prim = mayaUsd.ufe.ufePathToPrim(ufe_path)

            # If a stage root is selected, create hierarchy under it
            if str(prim.GetPath()) == "/":
                stage = prim.GetStage()
                prim_path = _prim_path_from_context(context)
                self._define_prim_hierarchy(stage, prim_path)
                prim = stage.GetPrimAtPath(prim_path)

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

    def _define_prim_hierarchy(self, stage, prim_path):
        """Ensure all ancestor Xform prims exist for the given path."""
        from pxr import UsdGeom
        from pxr import Sdf

        parts = prim_path.strip("/").split("/")
        current = ""
        for part in parts:
            current += "/" + part
            if not stage.GetPrimAtPath(current):
                UsdGeom.Xform.Define(stage, current)

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
