import contextlib
import shutil
import os

from ayon_core.pipeline import KnownPublishError
from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds


@contextlib.contextmanager
def hidden_render_view():
    """Context manager to hide the render view window temporarily."""
    # Ensure `renderViewWindow` exists so we can set its visibility
    was_existing = cmds.window("renderViewWindow", exists=True)
    if not was_existing:
        cmds.RenderViewWindow()

    # Hide the window
    cmds.window("renderViewWindow", edit=True, visible=False)
    try:
        yield
    finally:
        # Restore state
        if was_existing:
            cmds.window("renderViewWindow", edit=True, visible=True)
        else:
            cmds.deleteUI("renderViewWindow", window=True)


class ExtractLocalRender(plugin.MayaExtractorPlugin):
    """Extract local render

    Note that we do not target the 'render.local' instances here. That's
    because a single layer may have multiple AOV file outputs but we never
    want to trigger multiple renders for the same layer. Instead, we only
    target the 'renderlayer' instances here which represent a single layer
    to be rendered. But we still need to respect the local render flag in that
    case.
    """
    label = "Extract Local Render"
    families = ["renderlayer"]

    # When enabled try to hide the render view during rendering to avoid
    # it popping up in front of the user.
    offscreen: bool = True

    def process(self, instance):
        # Skip if explicitly marked for farm
        if instance.data.get("farm"):
            self.log.debug("Instance marked for farm, skipping local render.")
            return

        if instance.data.get("creator_attributes", {}).get(
            "render_target"
        ) != "local":
            self.log.debug(
                "Instance render target is not local, skipping local render."
            )
            return

        if cmds.about(batch=True):
            raise KnownPublishError(
                "Cannot perform local render in batch mode because "
                "`RenderSequence` command only works within an "
                "interactive Maya session."
            )

        frame_start: int = instance.data["frameStartHandle"]
        frame_end: int = instance.data["frameEndHandle"]
        step: int = int(instance.data.get("step", 1))

        # Get the render layer from the instance data using the legacy layer
        # node name, switch to it and render a sequence locally.
        layer: str = instance.data["setMembers"]
        with contextlib.ExitStack() as stack:
            stack.enter_context(lib.maintained_time())
            stack.enter_context(lib.renderlayer(layer))
            if self.offscreen:
                stack.enter_context(hidden_render_view())

            for t in range(frame_start, frame_end + 1, step):
                cmds.currentTime(t)
                cmds.RenderIntoNewWindow()

        # Because we're in an interactive session with user interface Maya will
        # render into a `tmp` subfolder under the 'images' file rule directory.
        # We need to move the files up a folder.
        image_directory: str = os.path.join(
            cmds.workspace(query=True, rootDirectory=True),
            cmds.workspace(fileRuleEntry="images"),
        )
        expected_files: list[dict[str, list[str]]] = (
            instance.data["expectedFiles"]
        )
        for _aov, filepaths in expected_files[0].items():
            for filepath in filepaths:
                relative_path = os.path.relpath(filepath, image_directory)
                source_filepath = os.path.join(
                    image_directory,
                    "tmp",
                    relative_path,
                )
                if not os.path.exists(source_filepath):
                    raise RuntimeError(
                        "Render did not produce expected file at: "
                        f"{source_filepath}"
                    )

                dest_dir = os.path.dirname(filepath)
                os.makedirs(dest_dir, exist_ok=True)
                self.log.debug(
                    f"Moving rendered file: {source_filepath} -> {filepath}"
                )
                shutil.move(source_filepath, filepath)