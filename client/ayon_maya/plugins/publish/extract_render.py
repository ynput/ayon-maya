from __future__ import annotations
import contextlib
import os
from typing import Optional

from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds, mel


@contextlib.contextmanager
def only_renderable(active_layer: str):
    """Set `active_layer` as only active renderlayer during context"""
    layers = cmds.ls(type="renderLayer")
    original: dict[str, bool] = {}
    try:
        for layer in layers:
            current_state: bool = cmds.getAttr(f"{layer}.renderable")
            target_state: bool = layer == active_layer
            original[layer] = current_state
            if current_state != target_state:
                cmds.setAttr(f"{layer}.renderable", target_state)
        cmds.refresh(f=True)
        yield
    finally:
        # Revert states
        for layer, target_state in original.items():
            current_state: bool = cmds.getAttr(f"{layer}.renderable")
            if current_state != target_state:
                cmds.setAttr(f"{layer}.renderable", target_state)


@contextlib.contextmanager
def revert_to_layer(layer: Optional[str] = None):
    """Revert back to original layer at end of context"""
    original_layer = cmds.editRenderLayerGlobals(query=True,
                                                 currentRenderLayer=True)
    try:
        if layer is not None:
            cmds.editRenderLayerGlobals(currentRenderLayer=layer)
        yield
    finally:
        cmds.editRenderLayerGlobals(currentRenderLayer=original_layer)


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

        # Get the render layer from the instance data using the legacy layer
        # node name, switch to it and render a sequence locally.
        layer: str = instance.data["setMembers"]

        with contextlib.ExitStack() as stack:
            stack.enter_context(lib.maintained_time())
            stack.enter_context(revert_to_layer())
            stack.enter_context(only_renderable(layer))

            # Render scene
            mel.eval('mayaBatchRenderProcedure(0, "", "", "", "")')

        # Because we're in an interactive session with user interface Maya some
        # renderers will render into a `tmp` subfolder under the 'images' file
        # rule directory. We need to move the files up a folder.
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
                tmp_filepath = os.path.join(
                    image_directory,
                    "tmp",
                    relative_path,
                )

                # Find the newest of two files, allowing it to be in tmp/
                existing = [
                    path for path in (filepath, tmp_filepath)
                    if os.path.exists(path)
                ]
                if not existing:
                    raise RuntimeError(
                        f"Render did not produce expected file at: {filepath}"
                    )

                existing.sort(key=os.path.getmtime, reverse=True)
                latest = existing[0]
                if latest == filepath:
                    # Do nothing, file is already in place
                    continue

                dest_dir = os.path.dirname(filepath)
                os.makedirs(dest_dir, exist_ok=True)
                self.log.debug(
                    f"Moving rendered file: {tmp_filepath} -> {filepath}"
                )
                os.rename(tmp_filepath, filepath)