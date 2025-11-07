# -*- coding: utf-8 -*-

from ayon_maya.api.workfile_template_builder import (
    MayaPlaceholderPlugin
)
from ayon_maya.api.lib import set_context_settings
from ayon_core.lib import BoolDef
from ayon_core.lib.events import weakref_partial


class SetContextMayaPlaceholderPlugin(MayaPlaceholderPlugin):
    """Set context variables for the workfile build.
    This placeholder allows the workfile build process to
    set context variables dynamically.

    """

    identifier = "maya.set_context"
    label = "Set Context Settings"

    use_selection_as_parent = False

    def get_placeholder_options(self, options=None):
        options = options or {}
        return [
            BoolDef("fps",
                    label="Set FPS",
                    tooltip="Set FPS context variable "
                            "based on the scene settings",
                    default=options.get("fps", True),
            ),
            BoolDef(
                "resolution",
                label="Set Resolution",
                tooltip="Set Resolution context variable "
                        "based on the scene settings",
                default=options.get("resolution", True),
            ),
            BoolDef(
                "frame_range",
                label="Set Frame Range",
                tooltip="Set Frame Range context variable "
                        "based on the scene settings",
                default=options.get("frame_range", True),
            ),
            BoolDef(
                "colorspace",
                label="Set Colorspace",
                tooltip="Set Colorspace context variable "
                        "based on the scene settings",
                default=options.get("colorspace", True),
            ),
            BoolDef(
                "scene_units",
                label="Set Scene Units",
                tooltip="Set Scene Units context variable "
                        "based on the scene settings",
                default=options.get("scene_units", True),
            )
        ]


    def populate_placeholder(self, placeholder):
        callback = weakref_partial(self.set_context_settings, placeholder)
        self.builder.add_on_depth_processed_callback(
            callback, order=placeholder.order)

        # If placeholder should be deleted, delete it after finish
        if not placeholder.data.get("keep_placeholder", True):
            delete_callback = weakref_partial(self.delete_placeholder,
                                              placeholder)
            self.builder.add_on_finished_callback(
                delete_callback, order=placeholder.order)

    def set_context_settings(self, placeholder):
        """Set context settings for the placeholder.

        Args:
            placeholder (dict): placeholder data
        """
        placeholder_context_data = {
            "fps": placeholder.data.get("fps", True),
            "resolution": placeholder.data.get("resolution", True),
            "frame_range": placeholder.data.get("frame_range", True),
            "colorspace": placeholder.data.get("colorspace", True),
            "scene_units": placeholder.data.get("scene_units", True),
        }
        set_context_settings(**placeholder_context_data)
