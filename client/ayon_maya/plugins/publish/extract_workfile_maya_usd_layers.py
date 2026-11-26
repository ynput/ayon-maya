from __future__ import annotations

import os

import pyblish.api
from ayon_core.pipeline import registered_host
from ayon_core.pipeline.workfile.lock_workfile import (
    is_workfile_lock_enabled,
    remove_workfile_lock,
)
from ayon_maya.api import plugin
from maya import cmds


def get_path_in_folder(path: str, folder: str) -> str | None:
    """Return `path` relative to `folder`, or None if it is not inside it."""
    try:
        relative_path = os.path.relpath(path, folder)
    except ValueError:
        # On another drive
        return None
    if relative_path == os.pardir or relative_path.startswith(
            os.pardir + os.sep):
        return None
    return relative_path.replace("\\", "/")


class ExtractWorkfileMayaUsdLayers(plugin.MayaInstancePlugin):
    """Publish the USD files of Maya USD stages saved next to the workfile.

    With the Maya USD save option "Save the Maya scene file and USD files"
    the layers of a shared stage are saved to USD files next to the Maya
    scene, which refers to them by absolute path.

    These USD files are published next to the published workfile and their
    paths are made relative, so the published workfile uses its own copies.
    The paths resolve to the same files for the workfile itself.
    """

    label = "Workfile Maya USD Layers"
    # Run after `SaveCurrentScene`, which may save the USD files
    order = pyblish.api.ExtractorOrder - 0.48
    families = ["workfile"]
    targets = ["local"]

    def process(self, instance):
        if not cmds.pluginInfo("mayaUsdPlugin", query=True, loaded=True):
            return

        import mayaUsd.ufe

        context = instance.context
        current_file = context.data["currentFile"]
        folder = os.path.dirname(current_file)
        layer_paths: set[str] = set()
        scene_changed = False
        for proxy in cmds.ls(type="mayaUsdProxyShapeBase", long=True):
            # Their paths are stored in the referenced file
            if cmds.referenceQuery(proxy, isNodeReferenced=True):
                continue

            stage = mayaUsd.ufe.getStage(proxy)
            if not stage:
                continue

            # Unshared stages save their USD edits in the Maya scene
            root_layer = stage.GetRootLayer()
            if root_layer.anonymous:
                continue

            file_path = get_path_in_folder(root_layer.realPath, folder)
            if file_path is None:
                continue

            if cmds.getAttr(f"{proxy}.filePath") != file_path:
                self.log.debug(f"Setting relative path on {proxy}: {file_path}")
                cmds.setAttr(f"{proxy}.filePathRelative", True)
                cmds.setAttr(f"{proxy}.filePath", file_path, type="string")
                scene_changed = True

            stage_layers = {
                os.path.normcase(os.path.normpath(layer.realPath)): layer
                for layer in stage.GetLayerStack(includeSessionLayers=False)
                if not layer.anonymous
            }
            self._collect_layers(root_layer, folder, stage_layers, layer_paths)

        if scene_changed:
            project_name = context.data["projectName"]
            project_settings = context.data["project_settings"]
            if is_workfile_lock_enabled("maya", project_name, project_settings):
                remove_workfile_lock(current_file)
            self.log.info(f"Saving current file: {current_file}")
            registered_host().save_workfile(current_file)

        publish_dir = instance.data["publishDir"]
        transfers = instance.data.setdefault("transfers", [])
        for path in sorted(layer_paths):
            destination = os.path.join(
                publish_dir, get_path_in_folder(path, folder))
            self.log.debug(f"Transfer: {path} > {destination}")
            transfers.append((path, destination))

    def _collect_layers(self, layer, folder, stage_layers, layer_paths):
        """Collect the paths of `layer` and its sublayers inside `folder`.

        The paths to these sublayers are made relative to their parent layer.

        Args:
            layer (Sdf.Layer): Layer inside `folder`.
            folder (str): The folder of the workfile.
            stage_layers (dict[str, Sdf.Layer]): The stage's file layers by
                their normalized path.
            layer_paths (set[str]): The collected layer paths.

        """
        layer_paths.add(layer.realPath)
        layer_folder = os.path.dirname(layer.realPath)
        sublayer_paths = list(layer.subLayerPaths)
        for index, path in enumerate(sublayer_paths):
            sublayer = stage_layers.get(os.path.normcase(
                os.path.normpath(layer.ComputeAbsolutePath(path))))
            if (
                sublayer is None
                or get_path_in_folder(sublayer.realPath, folder) is None
            ):
                continue

            relative_path = os.path.relpath(
                sublayer.realPath, layer_folder).replace("\\", "/")
            if not relative_path.startswith("../"):
                relative_path = f"./{relative_path}"
            sublayer_paths[index] = relative_path
            if sublayer.realPath not in layer_paths:
                self._collect_layers(
                    sublayer, folder, stage_layers, layer_paths)

        if sublayer_paths != list(layer.subLayerPaths):
            self.log.debug(
                f"Setting relative sublayer paths in {layer.realPath}")
            layer.subLayerPaths = sublayer_paths
            layer.Save()
