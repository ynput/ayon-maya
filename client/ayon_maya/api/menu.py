import os
import json
import logging
from functools import partial

from qtpy import QtWidgets, QtGui

import maya.utils
import maya.cmds as cmds

from ayon_core.pipeline import (
    get_current_folder_path,
    get_current_task_name,
    registered_host
)
from ayon_core.pipeline.workfile import BuildWorkfile
from ayon_core.tools.utils import host_tools
from ayon_maya.api import lib, lib_rendersettings
from ayon_core.settings import get_project_settings
from ayon_core.pipeline import get_current_project_name

from .lib import get_main_window, IS_HEADLESS
from ..tools import show_look_assigner
from .workfile_template_builder import (
    create_placeholder,
    update_placeholder,
    build_workfile_template,
    update_workfile_template
)
from ayon_core.pipeline.context_tools import version_up_current_workfile
from ayon_core.tools.workfile_template_build import open_template_ui
from .workfile_template_builder import MayaTemplateBuilder
from .testing import (
    run_tests_on_repository_workfile,
    test_create_on_repository_workfile,
    test_publish_on_repository_workfile,
    test_load_on_repository_workfile,
    run_tests,
    test_create,
    test_publish,
    test_load
)

log = logging.getLogger(__name__)

MENU_NAME = "op_maya_menu"


def _get_menu(menu_name=None):
    """Return the menu instance if it currently exists in Maya"""
    if menu_name is None:
        menu_name = MENU_NAME

    widgets = {w.objectName(): w for w in QtWidgets.QApplication.allWidgets()}
    return widgets.get(menu_name)


def get_context_label():
    return "{}, {}".format(
        get_current_folder_path(),
        get_current_task_name()
    )


def install(project_settings):
    if cmds.about(batch=True):
        log.info("Skipping AYON menu initialization in batch mode..")
        return

    def add_menu():
        project_settings = get_project_settings(
            get_current_project_name()
        )

        pyblish_icon = host_tools.get_pyblish_icon()
        parent_widget = get_main_window()
        cmds.menu(
            MENU_NAME,
            label=os.environ.get("AYON_MENU_LABEL") or "AYON",
            tearOff=True,
            parent="MayaWindow"
        )

        # Create context menu
        cmds.menuItem(
            "currentContext",
            label=get_context_label(),
            parent=MENU_NAME,
            enable=False
        )

        cmds.setParent("..", menu=True)

        if project_settings["core"]["tools"]["ayon_menu"].get(
            "version_up_current_workfile"):
                cmds.menuItem(divider=True)
                cmds.menuItem(
                    "Version Up Workfile",
                    command=lambda *args: version_up_current_workfile()
                )

        cmds.menuItem(divider=True)

        cmds.menuItem(
            "Create...",
            command=lambda *args: host_tools.show_publisher(
                parent=parent_widget,
                tab="create"
            )
        )

        cmds.menuItem(
            "Load...",
            command=lambda *args: host_tools.show_loader(
                parent=parent_widget,
                use_context=True
            )
        )

        cmds.menuItem(
            "Publish...",
            command=lambda *args: host_tools.show_publisher(
                parent=parent_widget,
                tab="publish"
            ),
            image=pyblish_icon
        )

        cmds.menuItem(
            "Manage...",
            command=lambda *args: host_tools.show_scene_inventory(
                parent=parent_widget
            )
        )

        cmds.menuItem(
            "Library...",
            command=lambda *args: host_tools.show_library_loader(
                parent=parent_widget
            )
        )

        cmds.menuItem(divider=True)

        cmds.menuItem(
            "Work Files...",
            command=lambda *args: host_tools.show_workfiles(
                parent=parent_widget
            ),
        )

        cmds.menuItem(
            "Set Frame Range",
            command=lambda *args: lib.reset_frame_range()
        )

        cmds.menuItem(
            "Set Resolution",
            command=lambda *args: lib.reset_scene_resolution()
        )

        cmds.menuItem(
            "Set Colorspace",
            command=lambda *args: lib.set_colorspace(),
        )

        cmds.menuItem(
            "Set Render Settings",
            command=lambda *args: lib_rendersettings.RenderSettings().set_default_renderer_settings()    # noqa
        )

        cmds.menuItem(divider=True, parent=MENU_NAME)
        cmds.menuItem(
            "Build First Workfile",
            parent=MENU_NAME,
            command=lambda *args: BuildWorkfile().process()
        )

        cmds.menuItem(
            "Look assigner...",
            command=lambda *args: show_look_assigner(
                parent_widget
            )
        )

        cmds.menuItem(
            "Experimental tools...",
            command=lambda *args: host_tools.show_experimental_tools_dialog(
                parent_widget
            )
        )

        builder_menu = cmds.menuItem(
            "Template Builder",
            subMenu=True,
            tearOff=True,
            parent=MENU_NAME
        )
        cmds.menuItem(
            "Build Workfile from template",
            parent=builder_menu,
            command=build_workfile_template
        )
        cmds.menuItem(
            "Update Workfile from template",
            parent=builder_menu,
            command=update_workfile_template
        )
        cmds.menuItem(
            divider=True,
            parent=builder_menu
        )
        cmds.menuItem(
            "Open Template",
            parent=builder_menu,
            command=lambda *args: open_template_ui(
                MayaTemplateBuilder(registered_host()), get_main_window()
            ),
        )
        cmds.menuItem(
            "Create Placeholder",
            parent=builder_menu,
            command=create_placeholder
        )
        cmds.menuItem(
            "Update Placeholder",
            parent=builder_menu,
            command=update_placeholder
        )

        if not project_settings["maya"].get("workfile_testing", False):
            cmds.setParent(MENU_NAME, menu=True)
            return

        testing_menu = cmds.menuItem(
            "Testing",
            subMenu=True,
            tearOff=True,
            parent=MENU_NAME
        )
        cmds.menuItem(
            "Run Tests On Repository Workfile",
            parent=testing_menu,
            command=lambda *args: run_tests_on_repository_workfile()
        )
        cmds.menuItem(
            "Test Create On Repository Workfile",
            parent=testing_menu,
            command=lambda *args: test_create_on_repository_workfile()
        )
        cmds.menuItem(
            "Test Publish On Repository Workfile",
            parent=testing_menu,
            command=lambda *args: test_publish_on_repository_workfile()
        )
        cmds.menuItem(
            "Test Load On Repository Workfile",
            parent=testing_menu,
            command=lambda *args: test_load_on_repository_workfile()
        )
        cmds.menuItem(divider=True)
        cmds.menuItem(
            "Run Tests On Current Workfile",
            parent=testing_menu,
            command=lambda *args: run_tests()
        )
        cmds.menuItem(
            "Test Create On Current Workfile",
            parent=testing_menu,
            command=lambda *args: test_create()
        )
        cmds.menuItem(
            "Test Publish On Current Workfile",
            parent=testing_menu,
            command=lambda *args: test_publish()
        )
        cmds.menuItem(
            "Test Load On Current Workfile",
            parent=testing_menu,
            command=lambda *args: test_load()
        )

        cmds.setParent(MENU_NAME, menu=True)

    def add_scripts_menu(project_settings):
        try:
            import scriptsmenu.launchformaya as launchformaya
        except ImportError:
            log.warning(
                "Skipping studio.menu install, because "
                "'scriptsmenu' module seems unavailable."
            )
            return

        menu_settings = project_settings["maya"]["scriptsmenu"]
        menu_name = menu_settings["name"]
        config = menu_settings["definition"]

        if menu_settings.get("definition_type") == "definition_json":
            data = menu_settings["definition_json"]
            try:
                config = json.loads(data)
            except json.JSONDecodeError as exc:
                print("Skipping studio menu, error decoding JSON definition.")
                log.error(exc)
                return

        if not config:
            log.warning("Skipping studio menu, no definition found.")
            return

        # run the launcher for Maya menu
        studio_menu = launchformaya.main(
            title=menu_name.title(),
            objectName=menu_name.title().lower().replace(" ", "_")
        )

        # apply configuration
        studio_menu.build_from_configuration(studio_menu, config)

    # Allow time for uninstallation to finish.
    # We use Maya's executeDeferred instead of QTimer.singleShot
    # so that it only gets called after Maya UI has initialized too.
    # This is crucial with Maya 2020+ which initializes without UI
    # first as a QCoreApplication
    maya.utils.executeDeferred(add_menu)
    cmds.evalDeferred(partial(add_scripts_menu, project_settings),
                      lowestPriority=True)


def uninstall():
    menu = _get_menu()
    if menu:
        log.info("Attempting to uninstall ...")

        try:
            menu.deleteLater()
            del menu
        except Exception as e:
            log.error(e)


def popup():
    """Pop-up the existing menu near the mouse cursor."""
    menu = _get_menu()
    cursor = QtGui.QCursor()
    point = cursor.pos()
    menu.exec_(point)


def update_menu_task_label():
    """Update the task label in AYON menu to current session"""

    if IS_HEADLESS:
        return

    object_name = "{}|currentContext".format(MENU_NAME)
    if not cmds.menuItem(object_name, query=True, exists=True):
        log.warning("Can't find menuItem: {}".format(object_name))
        return

    label = get_context_label()
    cmds.menuItem(object_name, edit=True, label=label)
