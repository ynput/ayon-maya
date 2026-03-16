# -*- coding: utf-8 -*-
import re
import uuid

from ayon_core.pipeline import load
from ayon_core.pipeline.load import get_representation_path_from_context
from ayon_maya.api.usdlib import (
    containerise_prim,
    iter_ufe_usd_selection
)

from maya import cmds
import mayaUsd


# ---------------------------------------------------------------------------
# Prim path builders
# ---------------------------------------------------------------------------

def _sanitize(value):
    """Replace USD-invalid characters with underscores."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", value).strip("_") or "_"


def _prim_path_folder(context):
    """Full folder path: /assets/character/cone_character"""
    folder = context.get("folder", {})
    path = folder.get("path", "")
    if path:
        sanitized = "/".join(
            _sanitize(p) for p in path.strip("/").split("/") if p
        )
        return "/" + sanitized
    return "/" + _sanitize(folder.get("name", "asset"))


def _prim_path_flat(context):
    """Flat: just the asset name — /cone_character"""
    folder = context.get("folder", {})
    name = folder.get("name", context.get("asset", "asset"))
    return "/" + _sanitize(name)


def _prim_path_by_type(context):
    """By folder type: /character/cone_character"""
    folder = context.get("folder", {})
    folder_type = folder.get("folderType", folder.get("type", ""))
    name = folder.get("name", context.get("asset", "asset"))
    if folder_type:
        return "/{}/{}".format(_sanitize(folder_type.lower()), _sanitize(name))
    return "/" + _sanitize(name)


def _prim_path_folder_product(context):
    """Folder path + product name: /assets/character/cone_character/usdMain"""
    base = _prim_path_folder(context)
    product = context.get("product", {})
    product_name = product.get("name", context.get("subset", ""))
    if product_name:
        return base + "/" + _sanitize(product_name)
    return base


_PRIM_PATH_BUILDERS = {
    "folder_path":      _prim_path_folder,
    "flat":             _prim_path_flat,
    "by_type":          _prim_path_by_type,
    "folder_product":   _prim_path_folder_product,
}


def _prim_path_from_context(context, options=None):
    """Resolve the target prim path based on the selected mode.

    Args:
        context (dict): AYON load context.
        options (dict): Loader options from the UI.

    Returns:
        str: Absolute USD prim path.
    """
    options = options or {}
    mode = options.get("prim_path_mode", "folder_path")

    if mode == "custom":
        custom = options.get("custom_prim_path", "").strip()
        if custom:
            return custom if custom.startswith("/") else "/" + custom
        # Fall back to folder_path if custom is empty
        mode = "folder_path"

    builder = _PRIM_PATH_BUILDERS.get(mode, _prim_path_folder)
    return builder(context)


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------

def _define_prim_hierarchy(stage, prim_path):
    """Ensure all ancestor Xform prims exist for the given USD path.

    Args:
        stage (pxr.Usd.Stage): The USD stage.
        prim_path (str): Absolute prim path.

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
    """Get the USD stage from a proxy shape DAG path.

    In this version of mayaUsd, getStage() accepts the plain DAG path
    without the '|world' prefix.
    """
    return mayaUsd.ufe.getStage(shape_long)


def _get_selected_proxy_shape():
    """Return the DAG path of a mayaUsdProxyShape in the current selection."""
    shapes = cmds.ls(selection=True, type="mayaUsdProxyShape", long=True) or []
    if shapes:
        return shapes[0]

    transforms = cmds.ls(selection=True, long=True) or []
    for transform in transforms:
        children = cmds.listRelatives(
            transform, shapes=True, type="mayaUsdProxyShape", fullPath=True
        ) or []
        if children:
            return children[0]

    return None


def _find_any_proxy_stage():
    """Find any mayaUsdProxyShape in the scene and return its stage."""
    shapes = cmds.ls(type="mayaUsdProxyShape", long=True) or []
    for shape in shapes:
        stage = _get_stage_from_proxy_shape(shape)
        if stage:
            return shape, stage
    return None, None


def _create_new_proxy_stage():
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

    stage = _get_stage_from_proxy_shape(shape_long[0])
    if not stage:
        raise RuntimeError(
            f"Could not get USD stage from newly created proxy: {shape_long[0]}"
        )
    return shape_long[0], stage


# ---------------------------------------------------------------------------
# Loader plugin
# ---------------------------------------------------------------------------

class MayaUsdProxyReferenceUsd(load.LoaderPlugin):
    """Add a USD Reference into a mayaUsdProxyShape stage.

    Workflow (in order of priority):
    1. USD prim selected in Outliner -> reference added directly to that prim.
    2. mayaUsdProxyShape (or its transform) selected -> loader builds the
       chosen prim hierarchy inside that stage.
    3. Nothing selected -> finds first proxy shape in scene, same as (2).
    4. No proxy in scene -> creates a new stage, same as (2).

    The prim path strategy is configurable via the Loader UI options panel.
    """

    product_types = {"model", "usd", "pointcache", "animation"}
    representations = ["usd", "usda", "usdc", "usdz", "abc"]

    label = "USD Add Reference"
    order = 0
    icon = "code-fork"
    color = "orange"

    identifier_key = "ayon_identifier"

    @classmethod
    def get_options(cls, contexts):
        """Options shown in the AYON Loader UI options panel."""
        # Preview the default path from the first context
        preview = ""
        if contexts:
            try:
                preview = _prim_path_folder(contexts[0])
            except Exception:
                pass

        return [
            {
                "name": "prim_path_mode",
                "label": "Prim Path Mode",
                "type": "enum",
                "default": "folder_path",
                "items": [
                    {
                        "label": "Folder Path  (e.g. {})".format(
                            preview or "/assets/character/cone_character"
                        ),
                        "value": "folder_path",
                    },
                    {
                        "label": "Flat  (e.g. /cone_character)",
                        "value": "flat",
                    },
                    {
                        "label": "By Folder Type  (e.g. /character/cone_character)",
                        "value": "by_type",
                    },
                    {
                        "label": "Folder + Product  (e.g. {}/usdMain)".format(
                            preview or "/assets/character/cone_character"
                        ),
                        "value": "folder_product",
                    },
                    {
                        "label": "Custom path",
                        "value": "custom",
                    },
                ],
            },
            {
                "name": "custom_prim_path",
                "label": "Custom Prim Path",
                "type": "text",
                "default": "",
                "placeholder": "/assets/character/cone_character",
            },
        ]

    def load(self, context, name=None, namespace=None, options=None):

        from pxr import Sdf

        stage = None
        prim = None

        # Priority 1: USD prim selected via UFE
        ufe_selection = list(iter_ufe_usd_selection())
        if ufe_selection:
            assert len(ufe_selection) == 1, "Select only one USD prim please"
            prim = mayaUsd.ufe.ufePathToPrim(ufe_selection[0])

        # Priority 2: mayaUsdProxyShape (or its transform) is selected
        if prim is None:
            proxy_shape = _get_selected_proxy_shape()
            if proxy_shape:
                stage = _get_stage_from_proxy_shape(proxy_shape)

        # Priority 3: no selection — find any proxy stage in the scene
        if prim is None and stage is None:
            _shape, stage = _find_any_proxy_stage()

        # Priority 4: no proxy in scene — create one
        if prim is None and stage is None:
            _shape, stage = _create_new_proxy_stage()

        # Build hierarchy from chosen prim path mode
        if prim is None and stage is not None:
            prim_path = _prim_path_from_context(context, options)
            prim = _define_prim_hierarchy(stage, prim_path)

            root_prim_name = prim_path.strip("/").split("/")[0]
            if not stage.GetRootLayer().defaultPrim:
                stage.GetRootLayer().defaultPrim = root_prim_name

        if not prim or not prim.IsValid():
            raise RuntimeError(
                "Could not resolve a valid USD prim to add the reference to."
            )

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
