from __future__ import annotations

import os
from typing import Optional, Any

from ayon_core.host.interfaces import OpenWorkfileOptionalData
from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.pipeline.actions import (
    WorkfileSimpleActionPlugin,
    WorkfileActionSelection,
    WorkfileActionResult,
)


class OpenWithoutReferencesAction(WorkfileSimpleActionPlugin):
    """Open selected workfile with all references unloaded."""
    identifier = "maya.open-without-references"
    settings_category = "maya"

    label = "Open without references"
    order = 0
    icon = MaterialSymbolsIcon("link_off")
    tooltip = "Open the workfile with unloaded references"
    description = (
        "Useful for heavy scenes or for scenes that fail to open because"
        " of a broken reference. References can be loaded afterwards"
        " in the Reference Editor."
    )

    extensions = {".ma", ".mb"}

    def is_compatible(self, selection: WorkfileActionSelection) -> bool:
        if (
            not selection.is_workarea()
            or not selection.has_workfile()
            or not selection.folder_id
            or not selection.task_id
        ):
            return False

        workfile_info = selection.workfile_info
        if workfile_info is not None and not workfile_info.available:
            return False

        ext = os.path.splitext(selection.filepath)[1].lower()
        return ext in self.extensions

    def execute_simple_action(
        self,
        selection: WorkfileActionSelection,
        form_values: dict[str, Any],
    ) -> Optional[WorkfileActionResult]:
        # A result is returned when the user should be asked first, or
        #   when saving failed. Otherwise it is bool if workfile was saved.
        result = self.ask_to_save_changes(form_values)
        if isinstance(result, WorkfileActionResult):
            return result

        host = self.host
        with host.open_workfile_options(loadReferenceDepth="none"):
            host.open_workfile_with_context(
                selection.filepath,
                selection.get_folder_entity(),
                selection.get_task_entity(),
                prepared_data=OpenWorkfileOptionalData(
                    project_entity=selection.get_project_entity(),
                    anatomy=selection.get_project_anatomy(),
                    project_settings=selection.get_project_settings(),
                ),
            )
        # Workfile was opened, the tool is not needed anymore
        return WorkfileActionResult(close_tool=True)
