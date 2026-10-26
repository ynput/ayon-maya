from __future__ import annotations
import contextlib
import os
from typing import Optional

from ayon_core.pipeline import PublishError
from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds, mel


# Render Sequence stores its settings in Maya optionVars. These are global,
# persistent values, so force the values required for a deterministic local
# render and restore the user's values afterwards.
RENDER_SEQUENCE_OPTION_VARS = {
    # Render the current render layer only. The extractor switches to the
    # layer of the instance before invoking Render Sequence.
    "renderSequenceAllLayers": 0,
    # Render all renderable cameras, matching Batch Render behavior.
    "renderSequenceAllCameras": 1,
    # Do not keep rendered images in the Render View.
    "renderSequenceAddToRenderView": 0,
    "renderSequenceAddAllLayers": 0,
    "renderSequenceAddAllCameras": 0,
    # Never use an interactive Render View region.
    "renderSequenceRegion": 0,
    # Respect Render Setup local overrides.
    "renderSequenceIgnoreLocalOverrides": 0,
    # Render at the Render Settings resolution instead of a Render View
    # "Test Resolution" (for example 50%).
    "renderViewTestResolution": 1,
}


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


@contextlib.contextmanager
def render_sequence_optionvars(output_directory: str):
    """Temporarily force the Render Sequence optionVars.

    Args:
        output_directory (str): Directory to render into. This overrides the
            user's optional Render Sequence "Alternate Output File Location".
    """
    previous = {}
    for key, value in RENDER_SEQUENCE_OPTION_VARS.items():
        existed = cmds.optionVar(exists=key)
        previous[key] = cmds.optionVar(query=key) if existed else None
        cmds.optionVar(intValue=(key, value))

    alternate_key = "RenderSequenceAlternateOutputFileLocation"
    alternate_existed = cmds.optionVar(exists=alternate_key)
    previous_alternate = (
        cmds.optionVar(query=alternate_key) if alternate_existed else None
    )
    cmds.optionVar(stringValue=(alternate_key, output_directory))
    try:
        yield
    finally:
        if previous_alternate is None:
            cmds.optionVar(remove=alternate_key)
        else:
            cmds.optionVar(
                stringValue=(alternate_key, previous_alternate)
            )

        for key, value in previous.items():
            if value is None:
                cmds.optionVar(remove=key)
            else:
                cmds.optionVar(intValue=(key, value))


def render_sequence_supported() -> bool:
    """Return whether Render Sequence can be used and why not.

    This must be called with the target render layer current, because the
    renderer can be overridden per render layer.

    Returns:
        bool: True if Render Sequence is supported, False otherwise.
    """
    if cmds.about(batch=True):
        return False
    if not mel.eval("exists renderSequence"):
        return False
    renderer = cmds.getAttr("defaultRenderGlobals.currentRenderer")
    mtoa_arv_sequence = os.environ.get("MTOA_ARV_SEQUENCE")
    if renderer.lower() == "arnold" and mtoa_arv_sequence not in (None, "0"):
        return False

    try:
        sequence_proc = cmds.renderer(
            renderer, query=True, renderSequenceProcedure=True
        )
    except (RuntimeError, ValueError):
        # Renderer query unavailable. Let `renderSequence` try; the
        # expected-file check catches an unsupported renderer.
        return True

    if not sequence_proc:
        return False

    return True


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
        creator_attributes = instance.data.get("creator_attributes", {})

        # Skip if explicitly marked for farm
        if instance.data.get("farm"):
            self.log.debug("Instance marked for farm, skipping local render.")
            return

        if creator_attributes.get("render_target") != "local":
            self.log.debug(
                "Instance render target is not local, skipping local render."
            )
            return

        local_render_method: str = creator_attributes.get(
            "local_render_method"
        ) or "batch_render"
        if local_render_method not in {"batch_render", "render_sequence"}:
            raise PublishError(
                "Unsupported local render method: "
                f"{local_render_method!r}"
            )

        # Get the render layer from the instance data using the legacy layer
        # node name, switch to it and render a sequence locally.
        layer: str = instance.data["setMembers"]

        image_directory: str = os.path.join(
            cmds.workspace(query=True, rootDirectory=True),
            cmds.workspace(fileRuleEntry="images"),
        )

        with contextlib.ExitStack() as stack:
            stack.enter_context(lib.maintained_time())
            stack.enter_context(only_renderable(layer))
            stack.enter_context(revert_to_layer())

            if local_render_method == "render_sequence" and render_sequence_supported():
                self.log.info(
                    "Rendering '%s' using Render Sequence", layer
                )
                render_sequence_optionvars(image_directory)
                mel.eval('renderSequence')
            else:
                self.log.info(
                    "Rendering '%s' usin" \
                    "g Batch Render", layer
                )
                # Render scene
                mel.eval('mayaBatchRenderProcedure(0, "", "", "", "")')

        # Because we're in an interactive session with user interface Maya some
        # renderers will render into a `tmp` subfolder under the 'images' file
        # rule directory. We need to move the files up a folder.
        expected_files: list[dict[str, list[str]]] = (
            instance.data["expectedFiles"]
        )
        for filepaths in expected_files[0].values():
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
                os.replace(tmp_filepath, filepath)
