import sys
import time
import logging

import ayon_api
from qtpy import QtWidgets, QtCore

from ayon_core import style
from ayon_core.pipeline import get_current_project_name
from ayon_core.tools.utils.lib import qt_app_context
from ayon_maya.api.lib import (
    assign_look_by_version,
    get_main_window
)

from maya import cmds
# old api for MFileIO
import maya.OpenMaya
import maya.api.OpenMaya as om

from .widgets import (
    AssetOutliner,
    LookOutliner
)
from .commands import (
    get_workfile,
    remove_unused_looks
)
from .vray_proxies import vrayproxy_assign_look
from . import arnold_standin

module = sys.modules[__name__]
module.window = None


class MayaLookAssignerWindow(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super(MayaLookAssignerWindow, self).__init__(parent=parent)

        self.log = logging.getLogger(__name__)

        # Store callback references
        self._callbacks = []
        self._connections_set_up = False

        filename = get_workfile()

        self.setObjectName("lookManager")
        self.setWindowTitle("Look Manager 1.4.0 - [{}]".format(filename))
        self.setWindowFlags(QtCore.Qt.Window)
        self.setParent(parent)

        self.resize(750, 500)

        self.setup_ui()

        # Force refresh check on initialization
        self._on_renderlayer_switch()

    def setup_ui(self):
        """Build the UI"""

        main_splitter = QtWidgets.QSplitter(self)

        # Assets (left)
        asset_outliner = AssetOutliner(main_splitter)

        # Looks (right)
        looks_widget = QtWidgets.QWidget(main_splitter)

        look_outliner = LookOutliner(looks_widget)  # Database look overview

        assign_selected = QtWidgets.QCheckBox(
            "Assign to selected only", looks_widget
        )
        assign_selected.setToolTip("Whether to assign only to selected nodes "
                                   "or to the full asset")
        remove_unused_btn = QtWidgets.QPushButton(
            "Remove Unused Looks", looks_widget
        )

        looks_layout = QtWidgets.QVBoxLayout(looks_widget)
        looks_layout.addWidget(look_outliner)
        looks_layout.addWidget(assign_selected)
        looks_layout.addWidget(remove_unused_btn)

        main_splitter.addWidget(asset_outliner)
        main_splitter.addWidget(looks_widget)
        main_splitter.setSizes([350, 200])

        # Footer
        status = QtWidgets.QStatusBar(self)
        status.setSizeGripEnabled(False)
        status.setFixedHeight(25)
        warn_layer = QtWidgets.QLabel(
            "Current Layer is not defaultRenderLayer", self
        )
        warn_layer.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        warn_layer.setStyleSheet("color: #DD5555; font-weight: bold;")
        warn_layer.setFixedHeight(25)

        footer = QtWidgets.QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addWidget(status)
        footer.addWidget(warn_layer)

        # Build up widgets
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.addWidget(main_splitter)
        main_layout.addLayout(footer)

        # Set column width
        asset_outliner.view.setColumnWidth(0, 200)
        look_outliner.view.setColumnWidth(0, 150)

        asset_outliner.selection_changed.connect(
            self.on_asset_selection_changed)

        asset_outliner.refreshed.connect(
            lambda: self.echo("Loaded assets..")
        )

        look_outliner.menu_apply_action.connect(self.on_process_selected)
        remove_unused_btn.clicked.connect(remove_unused_looks)

        # Open widgets
        self.asset_outliner = asset_outliner
        self.look_outliner = look_outliner
        self.status = status
        self.warn_layer = warn_layer

        # Buttons
        self.remove_unused = remove_unused_btn
        self.assign_selected = assign_selected

        self._first_show = True

    def setup_connections(self):
        """Connect interactive widgets with actions"""
        if self._connections_set_up:
            return

        # Maya renderlayer switch callback
        callback = om.MEventMessage.addEventCallback(
            "renderLayerManagerChange",
            self._on_renderlayer_switch
        )
        self._callbacks.append(callback)
        self._connections_set_up = True

    def remove_connection(self):
        # Delete callbacks
        for callback in self._callbacks:
            om.MMessage.removeCallback(callback)

        self._callbacks = []
        self._connections_set_up = False

    def showEvent(self, event):
        self.setup_connections()
        super(MayaLookAssignerWindow, self).showEvent(event)
        if self._first_show:
            self._first_show = False
            self.setStyleSheet(style.load_stylesheet())

    def closeEvent(self, event):
        self.remove_connection()
        super(MayaLookAssignerWindow, self).closeEvent(event)

    def _on_renderlayer_switch(self, *args):
        """Callback that updates on Maya renderlayer switch"""

        if maya.OpenMaya.MFileIO.isNewingFile():
            # Don't perform a check during file open or file new as
            # the renderlayers will not be in a valid state yet.
            return

        layer = cmds.editRenderLayerGlobals(query=True,
                                            currentRenderLayer=True)
        if layer != "defaultRenderLayer":
            self.warn_layer.show()
        else:
            self.warn_layer.hide()

    def echo(self, message):
        self.status.showMessage(message, 1500)

    def refresh(self):
        """Refresh the content"""

        # Get all containers and information
        self.asset_outliner.clear()
        found_items = self.asset_outliner.get_all_assets()
        if not found_items:
            self.look_outliner.clear()

    def on_asset_selection_changed(self):
        """Get selected items from asset loader and fill look outliner"""

        items = self.asset_outliner.get_selected_items()
        self.look_outliner.clear()
        self.look_outliner.add_items(items)

    def on_process_selected(self):
        """Process all selected looks for the selected assets"""

        assets = self.asset_outliner.get_selected_items()
        assert assets, "No asset selected"

        # Collect the looks we want to apply (by name)
        look_items = self.look_outliner.get_selected_items()
        looks = {look["product"] for look in look_items}

        selection = self.assign_selected.isChecked()
        asset_nodes = self.asset_outliner.get_nodes(selection=selection)

        project_name = get_current_project_name()
        start = time.time()
        for i, (asset, item) in enumerate(asset_nodes.items()):

            # Label prefix
            prefix = "({}/{})".format(i + 1, len(asset_nodes))

            # Assign the first matching look relevant for this asset
            # (since assigning multiple to the same nodes makes no sense)
            assign_look = next(
                (
                    product_entity
                    for product_entity in item["looks"]
                    if product_entity["name"] in looks
                ),
                None
            )
            if not assign_look:
                self.echo(
                    "{} No matching selected look for {}".format(prefix, asset)
                )
                continue

            # Get the latest version of this asset's look product
            version_entity = ayon_api.get_last_version_by_product_id(
                project_name, assign_look["id"], fields={"id"}
            )

            product_name = assign_look["name"]
            self.echo("{} Assigning {} to {}\t".format(
                prefix, product_name, asset
            ))
            nodes = item["nodes"]

            # Assign Vray Proxy look.
            if cmds.pluginInfo('vrayformaya', query=True, loaded=True):
                self.echo("Getting vray proxy nodes ...")
                vray_proxies = set(cmds.ls(type="VRayProxy", long=True))

                for vp in vray_proxies:
                    if vp in nodes:
                        vrayproxy_assign_look(vp, product_name)

                nodes = list(set(nodes).difference(vray_proxies))
            else:
                self.echo(
                    "Could not assign to VRayProxy because vrayformaya plugin "
                    "is not loaded."
                )

            # Assign Arnold Standin look.
            if cmds.pluginInfo("mtoa", query=True, loaded=True):
                # If the current renderer is Arnold we also allow assigning
                # to gpuCache nodes. If not, then we skip it because Arnold may
                # be loaded even if unused as renderer in current project.
                types = ["aiStandIn"]
                renderer = cmds.getAttr("defaultRenderGlobals.currentRenderer")
                if renderer == "arnold":
                    types.append("gpuCache")
                arnold_standins = cmds.ls(nodes, type=types, long=True)
                for standin in arnold_standins:
                    arnold_standin.assign_look_by_version(
                        standin, version_id=version_entity["id"])

                nodes = list(set(nodes).difference(arnold_standins))
            else:
                self.echo(
                    "Could not assign to aiStandIn because mtoa plugin is not "
                    "loaded."
                )

            # Assign look
            if nodes:
                assign_look_by_version(
                    nodes, version_id=version_entity["id"]
                )

        end = time.time()

        self.echo("Finished assigning.. ({0:.3f}s)".format(end - start))


def show():
    """Display Loader GUI

    Arguments:
        debug (bool, optional): Run loader in debug-mode,
            defaults to False

    """

    try:
        module.window.close()
        del module.window
    except (RuntimeError, AttributeError):
        pass

    # Get Maya main window
    mainwindow = get_main_window()

    with qt_app_context():
        window = MayaLookAssignerWindow(parent=mainwindow)
        window.show()

        module.window = window
