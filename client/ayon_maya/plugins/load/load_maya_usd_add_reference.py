# -*- coding: utf-8 -*-
import re
import uuid

import qargparse
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
    """Flat — just the asset name: /cone_character"""
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


_PRIM_PATH_BUILDERS = [
    # (enum_label, key, builder_fn)
    ("Folder Path  (/assets/character/cone_character)", "folder_path", _prim_path_folder),
    ("Flat  (/cone_character)",                         "flat",         _prim_path_flat),
    ("By Folder Type  (/character/cone_character)",     "by_type",      _prim_path_by_type),
    ("Folder + Product  (.../cone_character/usdMain)",  "folder_product",_prim_path_folder_product),
    ("Custom",                                          "custom",       None),
]

_PRIM_PATH_LABELS = [label for label, _, _ in _PRIM_PATH_BUILDERS]
_PRIM_PATH_KEYS   = [key   for _, key, _ in _PRIM_PATH_BUILDERS]


def _resolve_prim_path(context, mode_index, custom_path=""):
    """Resolve the final USD prim path from the chosen mode index."""
    label, key, builder = _PRIM_PATH_BUILDERS[mode_index]

    if key == "custom":
        path = (custom_path or "").strip()
        if path:
            return path if path.startswith("/") else "/" + path
        # fallback to folder_path
        return _prim_path_folder(context)

    return builder(context)


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------

def _define_prim_hierarchy(stage, prim_path):
    """Ensure all ancestor Xform prims exist for the given USD path."""
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

    getStage() in this version of mayaUsd accepts the plain DAG path
    without a '|world' prefix.
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
    """Find any mayaUsdProxyShape in the scene and return (shape, stage)."""
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
        raise RuntimeError("Could not find created proxy shape: {}".format(shape))

    stage = _get_stage_from_proxy_shape(shape_long[0])
    if not stage:
        raise RuntimeError(
            "Could not get USD stage from proxy: {}".format(shape_long[0])
        )
    return shape_long[0], stage


# ---------------------------------------------------------------------------
# Loader plugin
# ---------------------------------------------------------------------------

class MayaUsdProxyReferenceUsd(load.LoaderPlugin):
    """Add a USD Reference into a mayaUsdProxyShape stage.

    Options dialog appears on right-click > USD Add Reference to choose
    the prim path strategy:
      - Folder Path:     /assets/character/cone_character  (default)
      - Flat:            /cone_character
      - By Folder Type:  /character/cone_character
      - Folder+Product:  /assets/character/cone_character/usdMain
      - Custom:          user-defined path

    Stage resolution (in order of priority):
    1. USD prim selected (UFE) -> reference added directly, no path built.
    2. mayaUsdProxyShape selected -> options dialog, hierarchy built in stage.
    3. No selection -> first proxy in scene used.
    4. No proxy -> new stage created.
    """

    product_types = {"model", "usd", "pointcache", "animation"}
    representations = ["usd", "usda", "usdc", "usdz", "abc"]

    label = "USD Add Reference"
    order = 0
    icon = "code-fork"
    color = "orange"

    identifier_key = "ayon_identifier"

    options = [
        qargparse.Enum(
            "prim_path_mode",
            label="Prim Path Mode",
            items=_PRIM_PATH_LABELS,
            default=0,
            help=(
                "How to build the USD prim path for this asset.\n\n"
                "Folder Path:    /assets/character/cone_character\n"
                "Flat:           /cone_character\n"
                "By Folder Type: /character/cone_character\n"
                "Folder+Product: /assets/character/cone_character/usdMain\n"
                "Custom:         enter a path manually below"
            )
        ),
        qargparse.String(
            "custom_prim_path",
            label="Custom Prim Path",
            default="",
            help=(
                "Used only when Prim Path Mode is set to 'Custom'.\n"
                "Example: /assets/character/cone_character"
            )
        ),
    ]

    def load(self, context, name=None, namespace=None, options=None):

        from pxr import Sdf

        options = options or {}
        stage = None
        prim = None

        # Priority 1: USD prim selected via UFE — add reference directly
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

        # Build hierarchy using chosen prim path mode
        if prim is None and stage is not None:
            mode_index = options.get("prim_path_mode", 0)
            custom_path = options.get("custom_prim_path", "")
            prim_path = _resolve_prim_path(context, mode_index, custom_path)

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
