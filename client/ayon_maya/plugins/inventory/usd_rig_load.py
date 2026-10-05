from __future__ import annotations

from maya import cmds

from ayon_core.pipeline import InventoryAction
from ayon_maya.api.lib import (
    UsdMayaReference,
    discard_usd_maya_references,
    enable_usd_maya_references,
    get_container_members,
    get_main_window,
    get_selected_usd_maya_references,
    get_usd_maya_references,
)


def _get_proxies(containers: list[dict]) -> list[str]:
    proxies = []
    for container in containers:
        members = get_container_members(container)
        proxies.extend(cmds.ls(members, type="mayaUsdProxyShape", long=True))
    return proxies


def _pick_references(
    references: list[UsdMayaReference], title: str
) -> list[UsdMayaReference]:
    """Let the user pick from the references, unless there is just one."""
    if len(references) <= 1:
        return references

    from qtpy import QtWidgets

    dialog = QtWidgets.QDialog(get_main_window())
    dialog.setWindowTitle(title)
    layout = QtWidgets.QVBoxLayout(dialog)
    list_widget = QtWidgets.QListWidget()
    list_widget.setSelectionMode(
        QtWidgets.QAbstractItemView.ExtendedSelection)
    for reference in references:
        label = f"{reference.asset_prim_path}  ({reference.namespace})"
        item = QtWidgets.QListWidgetItem(label)
        list_widget.addItem(item)
        item.setSelected(True)
    layout.addWidget(list_widget)
    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if not dialog.exec_():
        return []
    return [
        reference for index, reference in enumerate(references)
        if list_widget.item(index).isSelected()
    ]


class LoadUsdRigs(InventoryAction):
    """Load the rigs embedded in a USD asset and create animation instances.

    Rigs are `MayaReference` prims in the USD. When prims are selected in
    the USD proxy (e.g. in the Outliner) only the rigs of those assets are
    loaded, otherwise the rigs of the selected USD containers can be picked.
    """

    label = "Load USD rigs"
    icon = "male"
    color = "#888888"

    @staticmethod
    def is_compatible(container):
        return container.get("loader") == "MayaUsdLoader"

    def process(self, containers):
        proxies = _get_proxies(containers)

        # Prefer the rigs of a USD prim selection
        references = [
            reference
            for reference in get_selected_usd_maya_references(proxies)
            if not reference.edited
        ]
        if not references:
            references = [
                reference for reference in get_usd_maya_references(proxies)
                if not reference.edited
            ]
            references = _pick_references(references, "Load USD rigs")

        enable_usd_maya_references(references, log=self.log)


class UnloadUsdRigs(InventoryAction):
    """Unload rigs loaded from a USD asset and remove their instances."""

    label = "Unload USD rigs"
    icon = "trash"
    color = "#888888"

    @staticmethod
    def is_compatible(container):
        return container.get("loader") == "MayaUsdLoader"

    def process(self, containers):
        proxies = _get_proxies(containers)
        references = [
            reference for reference in get_usd_maya_references(proxies)
            if reference.edited
        ]
        references = _pick_references(references, "Unload USD rigs")
        discard_usd_maya_references(references=references)
