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
    """Flat - just the asset name: /cone_character"""
    folder = context.get("folder", {})
    name = folder.get("name", context.get("asset", "asset"))
    return "/" + _sanitize(name)


def _prim_path_by_type(context):
    """By folder type: /character/cone_character

    Uses the parent folder name (content type) from the path,
    not the AYON folderType which is Asset/Shot/etc.
    E.g., from '/assets/character/cone_character' extracts 'character'.
    """
    folder = context.get("folder", {})
    name = folder.get("name", context.get("asset", "asset"))

    # Extract the content type from the folder path
    # e.g., '/assets/character/cone_character' -> 'character'
    path = folder.get("path", "")
    if path:
        parts = path.strip("/").split("/")
        # Get the second-to-last component (the content type)
        if len(parts) >= 2:
            folder_type = parts[-2]  # e.g., 'character', 'environment'
            return "/{}/{}".format(_sanitize(folder_type), _sanitize(name))

    # Fallback if path doesn't have the expected structure
    return "/" + _sanitize(name)


def _prim_path_folder_product(context):
    """Folder path + product name: /assets/character/cone_character/usdMain"""
    base = _prim_path_folder(context)
    product = context.get("product", {})
    product_name = product.get("name", context.get("subset", ""))
    if product_name:
        return base + "/" + _sanitize(product_name)
    return base


# (label shown in UI, internal key, builder function)
_PRIM_PATH_BUILDERS = [
    ("Folder Path",    "folder_path",    _prim_path_folder),
    ("Flat",           "flat",           _prim_path_flat),
    ("By Folder Type", "by_type",        _prim_path_by_type),
    ("Folder+Product", "folder_product", _prim_path_folder_product),
    ("Custom",         "custom",         None),
]

_PRIM_PATH_LABELS = [label for label, _, _ in _PRIM_PATH_BUILDERS]

# Build lookup dicts: exact label, stripped label, and key
_PRIM_PATH_BY_LABEL         = {label: (key, builder) for label, key, builder in _PRIM_PATH_BUILDERS}
_PRIM_PATH_BY_LABEL_STRIP   = {label.strip(): (key, builder) for label, key, builder in _PRIM_PATH_BUILDERS}
_PRIM_PATH_BY_KEY           = {key: (key, builder) for _, key, builder in _PRIM_PATH_BUILDERS}


def _lookup_mode(mode):
    """Resolve mode to (key, builder) regardless of what qargparse returns.

    Handles: int index, exact label, stripped label, internal key.
    Always prints the resolved result for debugging.

    Returns:
        (key, builder_fn) tuple. builder_fn is None for 'custom'.
    """
    if isinstance(mode, int):
        result = _PRIM_PATH_BUILDERS[mode]
        key, builder = result[1], result[2]
        print("[USD Ref] mode=int({}) -> key='{}'".format(mode, key))
        return key, builder

    mode_str = str(mode)
    print("[USD Ref] mode='{}'  (type={})".format(mode_str, type(mode).__name__))

    # 1. exact label
    if mode_str in _PRIM_PATH_BY_LABEL:
        key, builder = _PRIM_PATH_BY_LABEL[mode_str]
        print("[USD Ref]   matched by exact label -> key='{}'".format(key))
        return key, builder

    # 2. stripped label (handles trailing spaces)
    stripped = mode_str.strip()
    if stripped in _PRIM_PATH_BY_LABEL_STRIP:
        key, builder = _PRIM_PATH_BY_LABEL_STRIP[stripped]
        print("[USD Ref]   matched by stripped label -> key='{}'".format(key))
        return key, builder

    # 3. prefix match (handles labels like "Flat  (/cone_character)")
    for label, (key, builder) in _PRIM_PATH_BY_LABEL.items():
        if mode_str.startswith(label) or stripped.startswith(label.strip()):
            print("[USD Ref]   matched by prefix '{}' -> key='{}'".format(label, key))
            return key, builder

    # 4. internal key
    if mode_str in _PRIM_PATH_BY_KEY:
        key, builder = _PRIM_PATH_BY_KEY[mode_str]
        print("[USD Ref]   matched by key -> key='{}'".format(key))
        return key, builder

    print("[USD Ref]   WARNING: no match found, falling back to folder_path")
    return "folder_path", _prim_path_folder


def _resolve_prim_path(context, mode, custom_path=""):
    """Resolve the final USD prim path from the chosen mode.

    Args:
        context (dict): AYON load context.
        mode (str | int): Value from qargparse.Enum (label string or int index).
        custom_path (str): Used only when mode resolves to 'custom'.

    Returns:
        str: Absolute USD prim path.
    """
    key, builder = _lookup_mode(mode)

    if key == "custom":
        path = (custom_path or "").strip()
        if path:
            return path if path.startswith("/") else "/" + path
        print("[USD Ref] custom path empty, falling back to folder_path")
        return _prim_path_folder(context)

    return builder(context)


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------

def _define_prim_hierarchy(stage, prim_path):
    """Ensure all ancestor Xform prims exist for the given USD path."""
    from pxr import UsdGeom

    # Normalize the path: strip trailing slashes, ensure leading slash
    prim_path = "/" + prim_path.strip("/") if prim_path.strip("/") else "/"

    # Split into components, filtering out empty ones
    parts = [p for p in prim_path.strip("/").split("/") if p]

    if not parts:
        raise RuntimeError("Invalid prim path: {}".format(prim_path))

    # Create all ancestors and the target prim
    current = ""
    for part in parts:
        current += "/" + part
        existing = stage.GetPrimAtPath(current)
        # Only create if it doesn't exist AND is not valid
        if not existing or not existing.IsValid():
            # Use Xform.Define which will reuse if it already exists as a spec
            xform = UsdGeom.Xform.Define(stage, current)
            if not xform or not xform.GetPrim().IsValid():
                # Fallback: create as a generic prim if Xform.Define fails
                stage.DefinePrim(current, "Xform")

    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        raise RuntimeError("Failed to create prim at path: {}".format(prim_path))
    return prim


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
        base_prim = None

        # Priority 1: USD prim selected via UFE - use as base for hierarchy
        ufe_selection = list(iter_ufe_usd_selection())
        if ufe_selection:
            assert len(ufe_selection) == 1, "Select only one USD prim please"
            base_prim = mayaUsd.ufe.ufePathToPrim(ufe_selection[0])
            if base_prim and base_prim.IsValid():
                # Get the stage from the selected prim
                from pxr import Usd
                stage = base_prim.GetStage()

        # Priority 2: mayaUsdProxyShape (or its transform) is selected
        if stage is None:
            proxy_shape = _get_selected_proxy_shape()
            if proxy_shape:
                stage = _get_stage_from_proxy_shape(proxy_shape)

        # Priority 3: no selection - find any proxy stage in the scene
        if stage is None:
            _shape, stage = _find_any_proxy_stage()

        # Priority 4: no proxy in scene - create one
        if stage is None:
            _shape, stage = _create_new_proxy_stage()

        # Resolve the prim path using the chosen mode
        mode = options.get("prim_path_mode", 0)
        custom_path = options.get("custom_prim_path", "")
        key, _ = _lookup_mode(mode)
        prim_path = _resolve_prim_path(context, mode, custom_path)
        print("[USD Ref] resolved prim_path: '{}' (mode={})".format(prim_path, key))

        # Determine final prim path based on selection and mode
        final_prim_path = prim_path

        # If a prim is selected and mode is NOT custom, append to selected prim
        if base_prim is not None and base_prim.IsValid() and key != "custom":
            base_path = str(base_prim.GetPath()).rstrip("/")
            final_prim_path = base_path + prim_path
            print("[USD Ref] selected prim base: '{}', appending: {} -> '{}'".format(
                base_path, prim_path, final_prim_path
            ))
        elif key == "custom":
            # Custom path is always absolute, even if prim is selected
            print("[USD Ref] custom mode: using path as-is (ignoring selected prim)")

        # Create the prim hierarchy
        prim = _define_prim_hierarchy(stage, final_prim_path)

        # Set defaultPrim if we're at root level and don't have one
        if not base_prim and key != "custom":
            root_prim_name = final_prim_path.strip("/").split("/")[0]
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
