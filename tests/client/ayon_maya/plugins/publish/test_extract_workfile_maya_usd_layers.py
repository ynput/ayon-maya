"""Tests for publishing the Maya USD files saved next to a workfile.

Tests the `Workfile Maya USD Layers` publish plugin: the USD files Maya USD
saves next to the Maya scene for a shared stage are transferred next to the
published workfile, and the workfile refers to them by relative path so the
published workfile uses the published copies.

WARNING: Each test creates a new scene (forcefully), discarding the current
scene. When run in an interactive Maya session with unsaved changes the tests
refuse to run.

These tests require `ayon_core` and `ayon_maya` (and their dependencies) to
be importable, e.g. by running from Maya's Script Editor (Python) in a Maya
launched via AYON:

    import runpy
    runpy.run_path(
        r"path/to/ayon-maya/tests/client/ayon_maya/plugins/publish/test_extract_workfile_maya_usd_layers.py",
        run_name="__main__"
    )

Or with `mayapy` with `PYTHONPATH` set up to include `ayon_core`, `ayon_maya`
and their dependencies. If those are not importable the tests are skipped.

"""
import contextlib
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

import maya.standalone
from maya import cmds

IS_STANDALONE = not hasattr(cmds, "about")
if IS_STANDALONE:
    maya.standalone.initialize()


def _import_modules():
    """Return the modules to test, or raise `unittest.SkipTest`."""
    cmds.loadPlugin("mayaUsdPlugin", quiet=True)
    try:
        import pyblish.api
        from ayon_maya.api import workio
        from ayon_maya.plugins.publish import (
            extract_workfile_maya_usd_layers,
        )
    except ImportError as exc:
        raise unittest.SkipTest(
            f"ayon_core and ayon_maya must be importable: {exc}")
    return pyblish.api, workio, extract_workfile_maya_usd_layers


@contextlib.contextmanager
def maya_usd_save_option(option):
    """Set the Maya USD save option (1: USD files, 2: Maya scene, 3: none)

    Also disables Maya USD's save prompt, so saving does not block.
    """
    values = {
        "mayaUsd_SerializedUsdEditsLocation": option,
        "mayaUsd_SerializedUsdEditsLocationPrompt": 0,
    }
    original = {
        name: cmds.optionVar(query=name)
        for name in values if cmds.optionVar(exists=name)
    }
    for name, value in values.items():
        cmds.optionVar(intValue=(name, value))
    try:
        yield
    finally:
        for name in values:
            if name in original:
                cmds.optionVar(intValue=(name, original[name]))
            else:
                cmds.optionVar(remove=name)


class TestExtractWorkfileMayaUsdLayers(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not IS_STANDALONE and cmds.file(query=True, modified=True):
            raise RuntimeError(
                "Current scene has unsaved changes. Save or discard them "
                "before running these tests, as they create new scenes.")
        cls.pyblish_api, cls.workio, cls.module = _import_modules()

    def setUp(self):
        cmds.file(new=True, force=True)
        self.tmpdir = tempfile.mkdtemp(prefix="test_workfile_usd_layers_")
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.work_dir = os.path.join(self.tmpdir, "work")
        self.publish_dir = os.path.join(self.tmpdir, "publish", "v001")
        os.makedirs(self.work_dir)
        self.scene = os.path.join(self.work_dir, "scene_v001.ma").replace(
            "\\", "/")

        save_option = maya_usd_save_option(1)
        save_option.__enter__()
        self.addCleanup(save_option.__exit__, None, None, None)

        # The Maya host and workfile lock settings are not available here
        host = types.SimpleNamespace(save_workfile=self.workio.save_file)
        for name, value in (
            ("registered_host", lambda: host),
            ("is_workfile_lock_enabled", lambda *args: False),
        ):
            patcher = mock.patch.object(self.module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        cmds.file(new=True, force=True)

    def create_stage(self, share_stage=True, file_path=None):
        """Create a stage with a /root prim and an anonymous sublayer.

        Returns:
            str: The full path of the proxy shape.

        """
        import mayaUsd.ufe
        from pxr import Sdf

        transform = cmds.createNode(
            "transform", name="stage1", skipSelect=True)
        shape = cmds.createNode(
            "mayaUsdProxyShape",
            name="stageShape1",
            parent=transform,
            skipSelect=True,
        )
        cmds.connectAttr("time1.outTime", f"{shape}.time")
        cmds.setAttr(f"{shape}.shareStage", share_stage)
        if file_path:
            cmds.setAttr(f"{shape}.filePath", file_path, type="string")
        shape = cmds.ls(shape, long=True)[0]
        stage = mayaUsd.ufe.getStage(shape)
        stage.DefinePrim("/root", "Xform")
        sublayer = Sdf.Layer.CreateAnonymous()
        stage.GetRootLayer().subLayerPaths.append(sublayer.identifier)
        stage.SetEditTarget(sublayer)
        stage.DefinePrim("/root/in_sublayer", "Xform")
        stage.SetEditTarget(stage.GetRootLayer())
        return shape

    def save_scene(self):
        cmds.file(rename=self.scene)
        cmds.file(save=True, type="mayaAscii", force=True)

    def publish(self):
        """Run the plugin and copy the workfile and transfers like a publish.

        Returns:
            tuple[str, list[tuple[str, str]]]: The published workfile and
                the transfers.

        """
        context = self.pyblish_api.Context()
        context.data.update({
            "currentFile": self.scene,
            "projectName": "test_project",
            "project_settings": {},
        })
        instance = context.create_instance("workfileMain")
        instance.data["publishDir"] = self.publish_dir
        instance.data["stagingDir"] = os.path.join(self.tmpdir, "staging")
        self.module.ExtractWorkfileMayaUsdLayers().process(instance)

        transfers = instance.data.get("transfers", [])
        published_scene = os.path.join(
            self.publish_dir, "workfileMain_v001.ma")
        os.makedirs(self.publish_dir)
        shutil.copy(self.scene, published_scene)
        for source, destination in transfers:
            shutil.copy(source, destination)
        return published_scene, transfers

    def get_proxy(self):
        return cmds.ls(type="mayaUsdProxyShape", long=True)[0]

    def get_stage(self):
        import mayaUsd.ufe

        return mayaUsd.ufe.getStage(self.get_proxy())

    def get_work_usd_files(self):
        return sorted(
            name for name in os.listdir(self.work_dir) if name.endswith(".usd")
        )

    def assert_published_scene_uses_published_files(self, published_scene):
        """Open the published scene with the work USD files changed."""
        from pxr import Sdf

        root_name = os.path.basename(self.get_stage().GetRootLayer().realPath)
        cmds.file(new=True, force=True)
        work_root_layer = Sdf.Layer.FindOrOpen(
            os.path.join(self.work_dir, root_name))
        work_root_layer.Reload()
        Sdf.CreatePrimInLayer(work_root_layer, "/root/after_publish")
        work_root_layer.Save()

        cmds.file(published_scene, open=True, force=True)
        stage = self.get_stage()
        for layer in stage.GetLayerStack(includeSessionLayers=False):
            self.assertEqual(
                os.path.normcase(os.path.dirname(layer.realPath)),
                os.path.normcase(os.path.normpath(self.publish_dir)),
            )
        self.assertTrue(stage.GetPrimAtPath("/root/in_sublayer"))
        self.assertFalse(stage.GetPrimAtPath("/root/after_publish"))

        cmds.file(self.scene, open=True, force=True)
        stage = self.get_stage()
        self.assertTrue(stage.GetPrimAtPath("/root/in_sublayer"))
        self.assertTrue(stage.GetPrimAtPath("/root/after_publish"))

    def test_publish_uses_published_usd_files(self):
        shape = self.create_stage()
        self.save_scene()
        work_files = self.get_work_usd_files()
        self.assertEqual(len(work_files), 2, "Maya USD saved no USD files")
        file_path = cmds.getAttr(f"{shape}.filePath")
        sublayer_paths = list(self.get_stage().GetRootLayer().subLayerPaths)

        published_scene, transfers = self.publish()

        self.assertEqual(
            sorted(
                (os.path.basename(source), destination)
                for source, destination in transfers
            ),
            [
                (name, os.path.join(self.publish_dir, name))
                for name in work_files
            ],
        )
        # Only the root layer is staged to change its sublayer path
        root_name = os.path.basename(file_path)
        for source, _ in transfers:
            self.assertEqual(
                os.path.normcase(os.path.dirname(source))
                == os.path.normcase(os.path.normpath(self.work_dir)),
                os.path.basename(source) != root_name,
                source,
            )
        # The open scene and the work USD files keep their paths
        self.assertEqual(cmds.getAttr(f"{shape}.filePath"), file_path)
        self.assertFalse(cmds.getAttr(f"{shape}.filePathRelative"))
        self.assertEqual(
            list(self.get_stage().GetRootLayer().subLayerPaths),
            sublayer_paths,
        )
        self.assert_published_scene_uses_published_files(published_scene)

    def test_references(self):
        from pxr import Sdf

        def create_layer(path, prim_name):
            layer = Sdf.Layer.CreateNew(path)
            Sdf.CreatePrimInLayer(layer, f"/{prim_name}").specifier = (
                Sdf.SpecifierDef)
            layer.defaultPrim = prim_name
            layer.Save()

        other_dir = os.path.join(self.tmpdir, "other")
        os.makedirs(other_dir)
        create_layer(os.path.join(self.work_dir, "in_folder.usda"), "a")
        create_layer(os.path.join(other_dir, "outside.usda"), "b")
        self.create_stage()
        self.save_scene()
        stage = self.get_stage()
        for prim_path, asset_path in (
            ("/root/in_folder", "./in_folder.usda"),
            ("/root/outside", "../other/outside.usda"),
        ):
            stage.DefinePrim(prim_path).GetReferences().AddReference(
                asset_path)
        self.save_scene()

        published_scene, transfers = self.publish()

        self.assertIn(
            os.path.join(self.publish_dir, "in_folder.usda"),
            [destination for _, destination in transfers],
        )
        cmds.file(published_scene, open=True, force=True)
        stage = self.get_stage()
        for prim_path, folder in (
            ("/root/in_folder", self.publish_dir),
            ("/root/outside", other_dir),
        ):
            layer = stage.GetPrimAtPath(prim_path).GetPrimStack()[-1].layer
            self.assertEqual(
                os.path.normcase(os.path.dirname(layer.realPath)),
                os.path.normcase(os.path.normpath(folder)),
                prim_path,
            )

    def test_session_layer_edits(self):
        self.create_stage()
        self.save_scene()
        stage = self.get_stage()
        stage.SetEditTarget(stage.GetSessionLayer())
        stage.DefinePrim("/root/in_session_layer", "Xform")
        stage.SetEditTarget(stage.GetRootLayer())
        self.save_scene()

        published_scene, transfers = self.publish()

        self.assertEqual(len(transfers), 2)
        self.assertTrue(
            self.get_stage().GetPrimAtPath("/root/in_session_layer"))
        self.assert_published_scene_uses_published_files(published_scene)

    def test_locked_layer(self):
        self.create_stage()
        self.save_scene()
        self.get_stage().GetRootLayer().SetPermissionToEdit(False)

        published_scene, transfers = self.publish()

        self.assertEqual(len(transfers), 2)
        self.assert_published_scene_uses_published_files(published_scene)

    def test_unsaved_usd_edits_are_skipped(self):
        shape = self.create_stage()
        self.save_scene()
        file_path = cmds.getAttr(f"{shape}.filePath")
        self.get_stage().DefinePrim("/root/in_maya_scene", "Xform")
        with maya_usd_save_option(2):
            self.save_scene()

        _, transfers = self.publish()

        self.assertEqual(transfers, [])
        self.assertEqual(cmds.getAttr(f"{shape}.filePath"), file_path)
        self.assertFalse(cmds.file(query=True, modified=True))

    def test_unshared_stage_is_ignored(self):
        shape = self.create_stage(share_stage=False)
        self.save_scene()

        published_scene, transfers = self.publish()

        self.assertEqual(transfers, [])
        self.assertFalse(cmds.getAttr(f"{shape}.filePath"))
        cmds.file(published_scene, open=True, force=True)
        self.assertTrue(self.get_stage().GetPrimAtPath("/root/in_sublayer"))

    def test_usd_file_outside_workfile_folder_is_ignored(self):
        from pxr import Sdf

        other_dir = os.path.join(self.tmpdir, "other")
        os.makedirs(other_dir)
        file_path = os.path.join(other_dir, "asset.usda").replace("\\", "/")
        layer = Sdf.Layer.CreateNew(file_path)
        Sdf.CreatePrimInLayer(layer, "/root")
        layer.Save()

        shape = self.create_stage(file_path=file_path)
        self.save_scene()

        _, transfers = self.publish()

        self.assertEqual(transfers, [])
        self.assertEqual(cmds.getAttr(f"{shape}.filePath"), file_path)


def run():
    suite = unittest.TestLoader().loadTestsFromTestCase(
        TestExtractWorkfileMayaUsdLayers)
    return unittest.TextTestRunner(verbosity=2).run(suite)


if __name__ == "__main__":
    result = run()
    if IS_STANDALONE:
        maya.standalone.uninitialize()
        sys.exit(0 if result.wasSuccessful() else 1)
