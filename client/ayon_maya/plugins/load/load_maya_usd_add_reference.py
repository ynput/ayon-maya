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


def _prim_path_from_context(context):
    """Build a USD prim path that mirrors the AYON folder hierarchy.

    Examples:
        /assets/character/cone_character
        /assets/prop/rock
        /shots/sq010/sh010

    Args:
        context (dict): AYON load context.

    Returns:
        str: Absolute USD prim path.
    """
    import re

    folder = context.get("folder", {})
    path = folder.get("path", "")  # e.g. "/assets/characters/cone_character"

    if path:
        prim_path = re.sub(r"[^a-zA-Z0-9_/]", "_", path).rstrip("/")
        if not prim_path.startswith("/"):
            prim_path = "/" + prim_path
        return prim_path

    # Fallback: use asset name only
    return "/" + re.sub(
        r"[^a-zA-Z0-9_]", "_", folder.get("name", context.get("asset", "asset"))
    )


def _define_prim_hierarchy(stage, prim_path):
    """Ensure all ancestor Xform prims exist for the given USD path.

    Args:
        stage (pxr.Usd.Stage): The USD stage to define prims on.
        prim_path (str): Absolute prim path, e.g. '/assets/character/cone_character'.

    Returns:
        pxr.Usd.Prim: The leaf prim at prim_path.
    """
    from pxr import UsdGeom

    parts = prim_path.strip("/").split("/")
    current = ""
    for part in parts:
        current += "/" + part
        existing = stage.GetPrimAtPath(current)
        if not existing or not existing.IsValid():
            UsdGeom.Xform.Define(stage, current)

    return stage.GetPrimAtPath(prim_path)


def _get_stage_from_proxy_shape(shape_long):
    """Get the USD stage from a proxy shape using its UFE path.

    Args:
        shape_long (str): Full Maya DAG path to the proxy shape.

    Returns:
        pxr.Usd.Stage or None
    """
    ufe_path = "|world" + shape_long
    return mayaUsd.ufe.getStage(ufe_path)


def _find_any_proxy_stage():
    """Find any mayaUsdProxyShape in the scene and return its stage.

    Returns:
        (shape_long, stage) tuple or (None, None) if no proxy found.
    """
    shapes = cmds.ls(type="mayaUsdProxyShape", long=True) or []
    for shape in shapes:
        stage = _get_stage_from_proxy_shape(shape)
        if stage:
            return shape, stage
    return None, None


def _create_new_proxy_stage():
    """Create a new mayaUsdProxyShape and return (shape_long, stage)."""
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

    stage = _get_stage_from_proxy_shape(shape_long[0])
    if not stage:
        raise RuntimeError(
            f"Could not get USD stage from newly created proxy: {shape_long[0]}\n"
            f"Try selecting a USD prim in an existing stage before loading."
        )
    return shape_long[0], stage


class MayaUsdProxyReferenceUsd(load.LoaderPlugin):
    """Add a USD Reference into a mayaUsdProxyShape stage.

    Workflow:
    - With a USD prim selected in the Outliner: adds the reference directly
      to that prim.
    - With no USD prim selected: finds the first proxy stage in the scene
      (or creates one) and builds the prim hierarchy from the AYON folder
      path before adding the reference.

    The prim path mirrors the AYON project structure, e.g.:
        /assets/character/cone_character
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
        if selection:
            # Primary workflow: user selected a prim — use it directly
            assert len(selection) == 1, "Select only one USD prim please"
            prim = mayaUsd.ufe.ufePathToPrim(selection[0])
        else:
            # No USD prim selected: find or create a proxy stage, then
            # build the hierarchy from the AYON folder path
            _shape, stage = _find_any_proxy_stage()
            if stage is None:
                _shape, stage = _create_new_proxy_stage()

            prim_path = _prim_path_from_context(context)
            prim = _define_prim_hierarchy(stage, prim_path)

            # Set defaultPrim to the root of our path
            root_prim_name = prim_path.strip("/").split("/")[0]
            if not stage.GetRootLayer().defaultPrim:
                stage.GetRootLayer().defaultPrim = root_prim_name

        if not prim or not prim.IsValid():
            raise RuntimeError("Invalid primitive — could not resolve prim path.")

        path = get_representation_path_from_context(context)
        references = prim.GetReferences()

        identifier = str(prim.GetPath()) + ":" + str(uuid.uuid4())
        identifier_data = {self.identifier_key: identifier}
        reference = Sdf.Reference(assetPath=path, customData=identifier_data)

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
