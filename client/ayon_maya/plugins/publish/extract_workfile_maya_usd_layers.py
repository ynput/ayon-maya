from __future__ import annotations

import os
import shutil

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


def normalize_path(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


class ExtractWorkfileMayaUsdLayers(plugin.MayaExtractorPlugin):
    """Publish the USD files of Maya USD stages saved next to the workfile.

    With the Maya USD save option "Save the Maya scene file and USD files"
    the layers of a shared stage are saved to USD files next to the Maya
    scene, which refers to them by absolute path.

    These USD files, and the USD files inside the workfile folder they
    sublayer, reference or payload, are published next to the published
    workfile with relative paths between them. The workfile is saved with
    relative paths to them for publishing, so the published workfile uses
    the published copies. The open scene keeps the original paths.
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
        from pxr import Sdf

        context = instance.context
        folder = os.path.dirname(context.data["currentFile"])
        file_paths: dict[str, str] = {}
        layers = {}
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

            stage_layers = {
                normalize_path(layer.realPath): layer
                for layer in stage.GetUsedLayers()
                if not layer.anonymous
            }
            proxy_layers = {}
            self._collect_layers(
                root_layer, folder, stage_layers, proxy_layers)
            unsaved = [
                path for path, (layer, _) in proxy_layers.items()
                if layer.dirty
            ]
            if unsaved:
                # The Maya USD save option saved these edits in the Maya
                # scene or not at all
                self.log.warning(
                    f"Not publishing the USD files of {proxy}, because they"
                    f" have USD edits that are not saved to them: {unsaved}"
                )
                continue

            file_paths[proxy] = file_path
            layers.update(proxy_layers)

        if not file_paths:
            return

        publish_dir = instance.data["publishDir"]
        transfers = instance.data.setdefault("transfers", [])
        for path, (_, asset_paths) in layers.items():
            relative_path = get_path_in_folder(path, folder)
            source = path
            if asset_paths:
                # Update the asset paths in a copy, the work file stays as is
                source = os.path.join(
                    self.staging_dir(instance), relative_path)
                os.makedirs(os.path.dirname(source), exist_ok=True)
                shutil.copyfile(path, source)
                staged_layer = Sdf.Layer.FindOrOpen(source)
                for old_path, new_path in asset_paths.items():
                    staged_layer.UpdateCompositionAssetDependency(
                        old_path, new_path)
                staged_layer.Save()

            destination = os.path.join(publish_dir, relative_path)
            self.log.debug(f"Transfer: {source} > {destination}")
            transfers.append((source, destination))

        original_file_paths = {}
        for proxy, file_path in file_paths.items():
            original_file_paths[proxy] = (
                cmds.getAttr(f"{proxy}.filePath"),
                cmds.getAttr(f"{proxy}.filePathRelative"),
            )
            cmds.setAttr(f"{proxy}.filePathRelative", True)
            cmds.setAttr(f"{proxy}.filePath", file_path, type="string")
        try:
            self._save_workfile(context)
        finally:
            for proxy, (file_path, relative) in original_file_paths.items():
                cmds.setAttr(f"{proxy}.filePath", file_path, type="string")
                cmds.setAttr(f"{proxy}.filePathRelative", relative)

    def _collect_layers(self, layer, folder, stage_layers, layers):
        """Collect `layer` and the USD files inside `folder` it depends on.

        Args:
            layer (Sdf.Layer): Layer inside `folder`.
            folder (str): The folder of the workfile.
            stage_layers (dict[str, Sdf.Layer]): The stage's file layers by
                their normalized path.
            layers (dict[str, tuple[Sdf.Layer, dict[str, str]]]): The
                collected layers by their path, with the asset paths to
                change in their published copy: paths to collected layers
                become relative and relative paths to other files absolute.

        """
        from pxr import Sdf

        asset_paths = {}
        layers[layer.realPath] = (layer, asset_paths)
        layer_folder = os.path.dirname(layer.realPath)
        for asset_path in layer.GetCompositionAssetDependencies():
            path = layer.ComputeAbsolutePath(asset_path)
            if get_path_in_folder(path, folder) is None:
                # Keep resolving to the same file from the published copy
                if asset_path.startswith(("./", "../")):
                    asset_paths[asset_path] = path
                continue

            dependency = (
                stage_layers.get(normalize_path(path))
                or Sdf.Layer.FindOrOpen(path)
            )
            if dependency is None:
                continue

            relative_path = os.path.relpath(
                dependency.realPath, layer_folder).replace("\\", "/")
            if not relative_path.startswith("../"):
                relative_path = f"./{relative_path}"
            if relative_path != asset_path:
                asset_paths[asset_path] = relative_path
            if dependency.realPath not in layers:
                self._collect_layers(
                    dependency, folder, stage_layers, layers)

    def _save_workfile(self, context):
        current_file = context.data["currentFile"]
        project_name = context.data["projectName"]
        project_settings = context.data["project_settings"]
        if is_workfile_lock_enabled("maya", project_name, project_settings):
            remove_workfile_lock(current_file)
        self.log.info(
            f"Saving current file with relative USD file paths: {current_file}"
        )
        registered_host().save_workfile(current_file)
