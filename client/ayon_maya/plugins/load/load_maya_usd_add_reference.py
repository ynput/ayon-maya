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
    "folder_path":    (_prim_path_folder,   "Folder Path"),
    "flat":           (_prim_path_flat,     "Flat"),
    "by_type":        (_prim_path_by_type,  "By Folder Type"),
    "folder_product": (_prim_path_folder_product, "Folder + Product"),
    "custom":         (None,                "Custom"),
}


def _prim_path_from_context(context, mode, custom_path=""):
    """Resolve the target prim path based on the selected mode."""
    if mode == "custom":
        path = custom_path.strip()
        if path:
            return path if path.startswith("/") else "/" + path
        mode = "folder_path"

    builder, _ = _PRIM_PATH_BUILDERS.get(mode, _PRIM_PATH_BUILDERS["folder_path"])
    return builder(context)


# ---------------------------------------------------------------------------
# Prim path dialog
# ---------------------------------------------------------------------------

def _show_prim_path_dialog(context):
    """Show a modal dialog for prim path mode selection.

    Returns:
        (mode, custom_path) tuple, or (None, None) if cancelled.
    """
    from qtpy import QtWidgets, QtCore

    # Pre-compute previews for each mode
    previews = {}
    for key, (builder, _) in _PRIM_PATH_BUILDERS.items():
        if builder is not None:
            try:
                previews[key] = builder(context)
            except Exception:
                previews[key] = ""

    class PrimPathDialog(QtWidgets.QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("USD Add Reference — Prim Path")
            self.setMinimumWidth(480)
            self.setWindowFlags(
                self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint
            )

            layout = QtWidgets.QVBoxLayout(self)
            layout.setSpacing(8)

            # Mode selector
            mode_layout = QtWidgets.QFormLayout()
            self.mode_combo = QtWidgets.QComboBox()
            for key, (_, label) in _PRIM_PATH_BUILDERS.items():
                display = label
                if key in previews and previews[key]:
                    display = "{}  →  {}".format(label, previews[key])
                self.mode_combo.addItem(display, key)
            mode_layout.addRow("Mode:", self.mode_combo)
            layout.addLayout(mode_layout)

            # Preview label
            self.preview_label = QtWidgets.QLabel()
            self.preview_label.setStyleSheet(
                "color: #aaa; font-family: monospace; padding: 4px;"
            )
            self.preview_label.setWordWrap(True)
            layout.addWidget(self.preview_label)

            # Custom path field
            custom_layout = QtWidgets.QFormLayout()
            self.custom_field = QtWidgets.QLineEdit()
            self.custom_field.setPlaceholderText(
                "/assets/character/cone_character"
            )
            self.custom_field.setEnabled(False)
            custom_layout.addRow("Custom path:", self.custom_field)
            layout.addLayout(custom_layout)

            # Buttons
            btn_box = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Ok
                | QtWidgets.QDialogButtonBox.Cancel
            )
            btn_box.accepted.connect(self.accept)
            btn_box.rejected.connect(self.reject)
            layout.addWidget(btn_box)

            # Connections
            self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
            self.custom_field.textChanged.connect(self._on_custom_changed)
            self._on_mode_changed(0)

        def _on_mode_changed(self, _index):
            key = self.mode_combo.currentData()
            is_custom = key == "custom"
            self.custom_field.setEnabled(is_custom)
            if not is_custom:
                preview = previews.get(key, "")
                self.preview_label.setText(
                    "Prim path: <b>{}</b>".format(preview)
                )
            else:
                self._on_custom_changed(self.custom_field.text())

        def _on_custom_changed(self, text):
            path = text.strip()
            if path:
                self.preview_label.setText(
                    "Prim path: <b>{}</b>".format(
                        path if path.startswith("/") else "/" + path
                    )
                )
            else:
                self.preview_label.setText(
                    "<i>Enter a custom prim path above</i>"
                )

        def result_values(self):
            return (
                self.mode_combo.currentData(),
                self.custom_field.text().strip(),
            )

    # Get Maya main window as parent
    try:
        from ayon_core.tools.utils import get_qt_app  # noqa
        from maya import OpenMayaUI
        import shiboken2
        from qtpy import QtWidgets as _QtW
        ptr = OpenMayaUI.MQtUtil.mainWindow()
        parent = shiboken2.wrapInstance(int(ptr), _QtW.QWidget)
    except Exception:
        parent = None

    dialog = PrimPathDialog(parent=parent)
    if dialog.exec_() == QtWidgets.QDialog.Accepted:
        return dialog.result_values()
    return None, None


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
    """Get the USD stage from a proxy shape DAG path."""
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

    A dialog appears on load to choose the prim path strategy:
      - Folder Path:     /assets/character/cone_character  (default)
      - Flat:            /cone_character
      - By Folder Type:  /character/cone_character
      - Folder+Product:  /assets/character/cone_character/usdMain
      - Custom:          user-defined path

    Workflow (in order of priority):
    1. USD prim selected -> reference added directly to it (no dialog).
    2. ProxyShape selected -> dialog shown, hierarchy built in that stage.
    3. No selection -> first proxy in scene used.
    4. No proxy in scene -> new stage created.
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

        stage = None
        prim = None

        # Priority 1: USD prim selected via UFE — skip dialog, use prim directly
        ufe_selection = list(iter_ufe_usd_selection())
        if ufe_selection:
            assert len(ufe_selection) == 1, "Select only one USD prim please"
            prim = mayaUsd.ufe.ufePathToPrim(ufe_selection[0])

        # Priorities 2-4: resolve stage
        if prim is None:
            proxy_shape = _get_selected_proxy_shape()
            if proxy_shape:
                stage = _get_stage_from_proxy_shape(proxy_shape)

        if prim is None and stage is None:
            _shape, stage = _find_any_proxy_stage()

        if prim is None and stage is None:
            _shape, stage = _create_new_proxy_stage()

        # Show dialog and build hierarchy when we have a stage but no prim
        if prim is None and stage is not None:
            mode, custom_path = _show_prim_path_dialog(context)
            if mode is None:
                # User cancelled
                return None

            prim_path = _prim_path_from_context(context, mode, custom_path)
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
