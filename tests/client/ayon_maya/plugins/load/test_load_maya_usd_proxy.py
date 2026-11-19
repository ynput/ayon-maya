"""Tests for loading into Maya USD proxy shape stages.

Tests the `USD Add Reference` and `USD Add Maya Reference` loaders and the
listing of their containers by the Maya host (`ayon_maya.api.pipeline.ls`).

WARNING: Each test creates a new scene (forcefully), discarding the current
scene. When run in an interactive Maya session with unsaved changes the tests
refuse to run.

These tests require `ayon_core` and `ayon_maya` (and their dependencies) to
be importable, e.g. by running from Maya's Script Editor (Python) in a Maya
launched via AYON:

    import runpy
    runpy.run_path(
        r"path/to/ayon-maya/tests/client/ayon_maya/plugins/load/test_load_maya_usd_proxy.py",
        run_name="__main__"
    )

Or with `mayapy` with `PYTHONPATH` set up to include `ayon_core`, `ayon_maya`
and their dependencies. If those are not importable the tests are skipped.

"""
import os
import sys
import shutil
import tempfile
import unittest

import maya.standalone
from maya import cmds

IS_STANDALONE = not hasattr(cmds, "about")
if IS_STANDALONE:
    maya.standalone.initialize()

PROJECT_NAME = "test_project"
FOLDER_NAME = "hero"


def _import_modules():
    """Return the modules to test, or raise `unittest.SkipTest`."""
    cmds.loadPlugin("mayaUsdPlugin", quiet=True)
    try:
        from ayon_maya.api import pipeline, usdlib
        from ayon_maya.plugins.load import (
            load_maya_usd_add_reference,
            load_maya_usd_add_maya_reference,
        )
        from ayon_maya.plugins.inventory import lock_version
    except ImportError as exc:
        raise unittest.SkipTest(
            f"ayon_core and ayon_maya must be importable: {exc}")
    return (
        pipeline,
        usdlib,
        load_maya_usd_add_reference,
        load_maya_usd_add_maya_reference,
        lock_version,
    )


def make_context(path, representation_id):
    return {
        "project": {"name": PROJECT_NAME},
        "folder": {"name": FOLDER_NAME, "path": f"/{FOLDER_NAME}"},
        "product": {"name": "modelMain", "productType": "model"},
        "version": {"version": 1},
        # Test only: the path the patched `filepath_from_context` returns
        "representation": {"id": representation_id, "_path": path},
    }


class BaseMayaUsdProxyTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not IS_STANDALONE and cmds.file(query=True, modified=True):
            raise RuntimeError(
                "Current scene has unsaved changes. Save or discard them "
                "before running these tests, as they create new scenes.")
        (
            cls.pipeline,
            cls.usdlib,
            cls.add_reference_module,
            cls.add_maya_reference_module,
            cls.lock_version,
        ) = _import_modules()

        # Avoid resolving paths with the AYON server
        cls._patched_loaders = [
            cls.add_reference_module.MayaUsdProxyReferenceUsd,
            cls.add_maya_reference_module.MayaUsdProxyAddMayaReferenceLoader,
        ]
        for loader in cls._patched_loaders:
            loader.filepath_from_context = classmethod(
                lambda _cls, context: context["representation"]["_path"]
            )

        cls.tmpdir = tempfile.mkdtemp(prefix="ayon_maya_usd_test_")

    @classmethod
    def tearDownClass(cls):
        for loader in cls._patched_loaders:
            del loader.filepath_from_context
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        cmds.file(new=True, force=True)

    def tearDown(self):
        cmds.file(new=True, force=True)

    # region Helpers
    def make_usd_file(self, name):
        from pxr import Usd, UsdGeom

        path = os.path.join(self.tmpdir, f"{name}.usda").replace("\\", "/")
        stage = Usd.Stage.CreateNew(path)
        UsdGeom.Cube.Define(stage, f"/{name}/geo")
        stage.SetDefaultPrim(stage.GetPrimAtPath(f"/{name}"))
        stage.GetRootLayer().Save()
        return path

    def make_maya_file(self, name, node_name=None):
        path = os.path.join(self.tmpdir, f"{name}.ma").replace("\\", "/")
        if not os.path.exists(path):
            cmds.file(new=True, force=True)
            cmds.polyCube(name=node_name or name)
            cmds.file(rename=path)
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
        return path

    def get_usd_containers(self):
        return [
            container for container in self.pipeline.ls()
            if self.usdlib.is_usd_container(container)
        ]

    def get_container(self, container):
        """Return the latest container data from `ls()`"""
        for other in self.get_usd_containers():
            if (
                other["prim_spec_path"] == container["prim_spec_path"]
                and other["proxy"] == container["proxy"]
                and other.get("identifier") == container.get("identifier")
            ):
                return other
        self.fail(f"Container not found: {container['objectName']}")

    def get_stage(self, container):
        return self.usdlib.get_proxy_stage(container["proxy"])

    def get_prim_references(self, prim):
        """Return composed references of prim as (assetPath, data) tuples"""
        result = []
        for prim_spec in prim.GetPrimStack():
            for reference in prim_spec.referenceList.prependedItems:
                data = dict(reference.customData.get("ayon", {}))
                result.append((reference.assetPath, data))
        return result
    # endregion


class TestUsdAddReferenceLoader(BaseMayaUsdProxyTest):

    def load(self, path, representation_id, name="modelMain"):
        loader = self.add_reference_module.MayaUsdProxyReferenceUsd()
        return loader.load(make_context(path, representation_id), name=name)

    def test_load_without_selection_creates_stage(self):
        path = self.make_usd_file("asset")
        cmds.select(clear=True)
        container = self.load(path, "repre1")

        # Returns the container data
        self.assertIsInstance(container, dict)
        for key in ("schema", "id", "name", "namespace", "loader",
                    "representation", "objectName", "project_name"):
            self.assertIn(key, container)
        self.assertEqual(container["representation"], "repre1")
        self.assertEqual(container["project_name"], PROJECT_NAME)
        self.assertEqual(container["loader"], "MayaUsdProxyReferenceUsd")
        self.assertEqual(container["prim_path"], "/root")

        # A new stage was created with the reference on its root prim
        proxies = cmds.ls(type="mayaUsdProxyShape", long=True)
        self.assertEqual(len(proxies), 1)
        self.assertEqual(container["objectName"], f"{proxies[0]},/root")
        stage = self.get_stage(container)
        self.assertEqual(stage.GetDefaultPrim().GetPath().pathString,
                         "/root")
        prim = stage.GetPrimAtPath("/root/geo")
        self.assertTrue(prim.IsValid(), "Referenced prim not composed")

        # The container data is stored on the reference, not the prim
        root = stage.GetPrimAtPath("/root")
        self.assertFalse(root.GetCustomDataByKey("ayon"))
        references = self.get_prim_references(root)
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0][0], path)
        self.assertEqual(references[0][1]["representation"], "repre1")

        # It is listed by the host
        containers = self.get_usd_containers()
        self.assertEqual(len(containers), 1)
        self.assertEqual(containers[0]["objectName"],
                         container["objectName"])
        self.assertEqual(containers[0]["identifier"],
                         container["identifier"])

    def test_load_into_selected_prim(self):
        path = self.make_usd_file("asset")
        ufe_path = self.usdlib.create_stage_with_root_prim("/world")
        cmds.select(ufe_path, replace=True)
        container = self.load(path, "repre1")
        self.assertEqual(container["objectName"], ufe_path)
        self.assertEqual(container["prim_path"], "/world")
        stage = self.get_stage(container)
        self.assertTrue(stage.GetPrimAtPath("/world/geo").IsValid())

    def test_load_with_multiple_prims_selected_raises(self):
        from ayon_core.pipeline.load import LoadError

        path = self.make_usd_file("asset")
        ufe_path = self.usdlib.create_stage_with_root_prim("/a")
        proxy = ufe_path.split(",", 1)[0]
        stage = self.usdlib.get_proxy_stage(proxy)
        stage.DefinePrim("/b", "Xform")
        cmds.select(f"{proxy},/a", f"{proxy},/b", replace=True)
        with self.assertRaises(LoadError):
            self.load(path, "repre1")

    def test_multiple_references_on_same_prim(self):
        path_a = self.make_usd_file("assetA")
        path_b = self.make_usd_file("assetB")
        path_c = self.make_usd_file("assetC")

        cmds.select(clear=True)
        container_a = self.load(path_a, "repreA")
        cmds.select(container_a["objectName"], replace=True)
        container_b = self.load(path_b, "repreB")
        self.assertEqual(container_a["objectName"],
                         container_b["objectName"])
        self.assertNotEqual(container_a["identifier"],
                            container_b["identifier"])

        containers = self.get_usd_containers()
        self.assertEqual(
            sorted(c["representation"] for c in containers),
            ["repreA", "repreB"]
        )

        # Update only affects the updated container
        loader = self.add_reference_module.MayaUsdProxyReferenceUsd()
        loader.update(self.get_container(container_a),
                      make_context(path_c, "repreC"))
        stage = self.get_stage(container_a)
        root = stage.GetPrimAtPath("/root")
        references = dict(
            (data["identifier"], (asset_path, data))
            for asset_path, data in self.get_prim_references(root)
        )
        self.assertEqual(len(references), 2)
        asset_path, data = references[container_a["identifier"]]
        self.assertEqual(asset_path, path_c)
        self.assertEqual(data["representation"], "repreC")
        asset_path, data = references[container_b["identifier"]]
        self.assertEqual(asset_path, path_b)
        self.assertEqual(data["representation"], "repreB")
        self.assertTrue(stage.GetPrimAtPath("/root/geo").IsValid())

        # Remove only removes the removed container
        loader.remove(self.get_container(container_b))
        references = self.get_prim_references(root)
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0][0], path_c)
        containers = self.get_usd_containers()
        self.assertEqual(len(containers), 1)
        self.assertEqual(containers[0]["representation"], "repreC")

        loader.remove(self.get_container(container_a))
        self.assertEqual(self.get_usd_containers(), [])
        self.assertEqual(self.get_prim_references(root), [])

    def test_reference_in_sublayer_and_variant(self):
        from pxr import Sdf, Usd

        path = self.make_usd_file("asset")
        path_v2 = self.make_usd_file("asset_v2")
        ufe_path = self.usdlib.create_stage_with_root_prim("/root")
        proxy = ufe_path.split(",", 1)[0]
        stage = self.usdlib.get_proxy_stage(proxy)

        # Author the reference into a sublayer, inside a variant
        sublayer = Sdf.Layer.CreateAnonymous("sublayer")
        stage.GetRootLayer().subLayerPaths.append(sublayer.identifier)
        root = stage.GetPrimAtPath("/root")
        variant_set = root.GetVariantSets().AddVariantSet("model")
        variant_set.AddVariant("main")
        variant_set.SetVariantSelection("main")
        stage.SetEditTarget(Usd.EditTarget(sublayer))
        with variant_set.GetVariantEditContext():
            cmds.select(ufe_path, replace=True)
            container = self.load(path, "repre1")
        stage.SetEditTarget(Usd.EditTarget(stage.GetRootLayer()))

        self.assertTrue(stage.GetPrimAtPath("/root/geo").IsValid())
        prim_spec = sublayer.GetPrimAtPath("/root{model=main}")
        self.assertEqual(len(prim_spec.referenceList.prependedItems), 1)

        containers = self.get_usd_containers()
        self.assertEqual(len(containers), 1)
        self.assertEqual(containers[0]["prim_path"], "/root")

        # Update in the layer and variant where it is authored
        loader = self.add_reference_module.MayaUsdProxyReferenceUsd()
        loader.update(self.get_container(container),
                      make_context(path_v2, "repre2"))
        reference = prim_spec.referenceList.prependedItems[0]
        self.assertEqual(reference.assetPath, path_v2)
        self.assertEqual(reference.customData["ayon"]["representation"],
                         "repre2")
        self.assertFalse(
            stage.GetRootLayer().GetPrimAtPath("/root").hasReferences)

        # Containers in unselected variants can still be managed
        variant_set.AddVariant("other")
        variant_set.SetVariantSelection("other")
        self.assertFalse(stage.GetPrimAtPath("/root/geo").IsValid())
        loader.update(self.get_container(container),
                      make_context(path, "repre3"))
        reference = prim_spec.referenceList.prependedItems[0]
        self.assertEqual(reference.assetPath, path)
        self.assertEqual(reference.customData["ayon"]["representation"],
                         "repre3")

        loader.remove(self.get_container(container))
        self.assertEqual(len(prim_spec.referenceList.prependedItems), 0)
        self.assertEqual(self.get_usd_containers(), [])

    def test_containers_in_referenced_files_are_not_listed(self):
        # Create a USD file which itself has a loaded container in it
        path = self.make_usd_file("asset")
        cmds.select(clear=True)
        container = self.load(path, "repre1")
        stage = self.get_stage(container)
        layout_path = os.path.join(
            self.tmpdir, "layout.usda").replace("\\", "/")
        stage.GetRootLayer().Export(layout_path)
        cmds.file(new=True, force=True)

        # Reference that file into a new stage
        cmds.select(clear=True)
        self.load(layout_path, "repreLayout")
        containers = self.get_usd_containers()
        self.assertEqual(
            [c["representation"] for c in containers], ["repreLayout"]
        )

    def test_lock_and_unlock_version(self):
        path = self.make_usd_file("asset")
        cmds.select(clear=True)
        container = self.load(path, "repre1")
        self.assertFalse(container.get("version_locked", False))

        self.lock_version.set_version_locked(container, True)
        self.assertIs(self.get_container(container)["version_locked"], True)

        self.lock_version.set_version_locked(
            self.get_container(container), False)
        self.assertFalse(self.get_container(container)["version_locked"])


class TestUsdAddMayaReferenceLoader(BaseMayaUsdProxyTest):

    def load(self, path, representation_id, name="modelMain"):
        loader_module = self.add_maya_reference_module
        loader = loader_module.MayaUsdProxyAddMayaReferenceLoader()
        return loader.load(make_context(path, representation_id), name=name)

    def test_load_update_remove(self):
        path = self.make_maya_file("cubeA")
        path_v2 = self.make_maya_file("cubeB")
        ufe_path = self.usdlib.create_stage_with_root_prim("/root")
        cmds.select(ufe_path, replace=True)
        container = self.load(path, "repre1")

        self.assertIsInstance(container, dict)
        self.assertEqual(container["representation"], "repre1")
        self.assertEqual(container["project_name"], PROJECT_NAME)
        self.assertEqual(container["loader"],
                         "MayaUsdProxyAddMayaReferenceLoader")
        self.assertEqual(container["prim_path"], "/root/hero_modelMain")

        stage = self.get_stage(container)
        prim = stage.GetPrimAtPath(container["prim_path"])
        self.assertEqual(prim.GetTypeName(), "MayaReference")
        self.assertEqual(prim.GetAttribute("mayaReference").Get().path,
                         path)
        namespace = prim.GetAttribute("mayaNamespace").Get()
        self.assertTrue(namespace.startswith(f"{FOLDER_NAME}_"))
        self.assertNotEqual(namespace, "test")
        self.assertEqual(prim.GetCustomDataByKey("ayon")["representation"],
                         "repre1")

        containers = self.get_usd_containers()
        self.assertEqual(len(containers), 1)
        self.assertEqual(containers[0]["objectName"],
                         container["objectName"])

        # Loading again into the same prim gets a unique prim name
        cmds.select(ufe_path, replace=True)
        container2 = self.load(path, "repre1")
        self.assertNotEqual(container2["prim_path"], container["prim_path"])
        self.assertEqual(len(self.get_usd_containers()), 2)

        loader_module = self.add_maya_reference_module
        loader = loader_module.MayaUsdProxyAddMayaReferenceLoader()
        loader.update(self.get_container(container),
                      make_context(path_v2, "repre2"))
        self.assertEqual(prim.GetAttribute("mayaReference").Get().path,
                         path_v2)
        updated = self.get_container(container)
        self.assertEqual(updated["representation"], "repre2")
        # The other container is unaffected
        self.assertEqual(self.get_container(container2)["representation"],
                         "repre1")

        loader.remove(updated)
        self.assertFalse(
            stage.GetPrimAtPath(container["prim_path"]).IsValid())
        self.assertEqual(len(self.get_usd_containers()), 1)

    def test_load_without_selection_creates_stage(self):
        path = self.make_maya_file("cubeA")
        cmds.select(clear=True)
        container = self.load(path, "repre1")
        self.assertEqual(container["prim_path"], "/root/hero_modelMain")
        self.assertEqual(len(cmds.ls(type="mayaUsdProxyShape")), 1)

    def get_maya_namespace(self, container):
        prim = self.get_stage(container).GetPrimAtPath(
            container["prim_path"])
        return prim.GetAttribute("mayaNamespace").Get()

    def test_unique_namespaces(self):
        """Namespaces are unique, even though none exists in Maya yet"""
        path = self.make_maya_file("cubeA")
        ufe_path = self.usdlib.create_stage_with_root_prim("/root")
        cmds.select(ufe_path, replace=True)
        container_a = self.load(path, "repre1")
        cmds.select(ufe_path, replace=True)
        container_b = self.load(path, "repre1")
        # Also unique across stages
        cmds.select(clear=True)
        container_c = self.load(path, "repre1")
        self.assertNotEqual(container_a["proxy"], container_c["proxy"])

        namespaces = [
            self.get_maya_namespace(container)
            for container in (container_a, container_b, container_c)
        ]
        self.assertEqual(len(set(namespaces)), 3, namespaces)

    def test_update_and_remove_while_edited_as_maya(self):
        """Updating keeps Maya edits, removing discards them"""
        import mayaUsd.lib

        path = self.make_maya_file("v1", node_name="cube")
        path_v2 = self.make_maya_file("v2", node_name="cube")
        cmds.select(clear=True)
        container = self.load(path, "repre1")
        namespace = self.get_maya_namespace(container)
        prim = self.get_stage(container).GetPrimAtPath(
            container["prim_path"])

        cmds.mayaUsdEditAsMaya(container["objectName"])
        pulled_node = mayaUsd.lib.PrimUpdaterManager.readPullInformation(
            prim)
        self.assertTrue(pulled_node)
        cube = f"{namespace}:cube"
        cmds.setAttr(f"{cube}.translateX", 5)

        loader_module = self.add_maya_reference_module
        loader = loader_module.MayaUsdProxyAddMayaReferenceLoader()
        loader.update(self.get_container(container),
                      make_context(path_v2, "repre2"))

        # Still edited as Maya data, with the edit kept
        self.assertEqual(
            mayaUsd.lib.PrimUpdaterManager.readPullInformation(prim),
            pulled_node
        )
        self.assertEqual(cmds.getAttr(f"{cube}.translateX"), 5)
        self.assertEqual(
            cmds.referenceQuery(cube, filename=True, withoutCopyNumber=True),
            path_v2
        )
        self.assertEqual(prim.GetAttribute("mayaReference").Get().path,
                         path_v2)
        self.assertEqual(self.get_container(container)["representation"],
                         "repre2")

        loader.remove(self.get_container(container))
        self.assertFalse(
            self.get_stage(container).GetPrimAtPath(
                container["prim_path"]).IsValid()
        )
        self.assertFalse(cmds.ls(cube))
        self.assertEqual(self.get_usd_containers(), [])

    def test_containers_in_variants(self):
        """Containers at the same prim path in different variants"""
        path = self.make_maya_file("cubeA")
        path_v2 = self.make_maya_file("cubeB")
        ufe_path = self.usdlib.create_stage_with_root_prim("/root")
        stage = self.usdlib.get_proxy_stage(ufe_path.split(",", 1)[0])
        variant_set = stage.GetPrimAtPath("/root").GetVariantSets(
            ).AddVariantSet("model")
        containers = {}
        for variant in ("a", "b"):
            variant_set.AddVariant(variant)
            variant_set.SetVariantSelection(variant)
            with variant_set.GetVariantEditContext():
                cmds.select(ufe_path, replace=True)
                containers[variant] = self.load(path, f"repre_{variant}")

        self.assertEqual(containers["a"]["prim_path"],
                         containers["b"]["prim_path"])
        self.assertEqual(
            sorted(c["representation"] for c in self.get_usd_containers()),
            ["repre_a", "repre_b"]
        )

        # Update and remove the container in the unselected variant
        loader_module = self.add_maya_reference_module
        loader = loader_module.MayaUsdProxyAddMayaReferenceLoader()
        loader.update(self.get_container(containers["a"]),
                      make_context(path_v2, "repre_a2"))
        layer = stage.GetRootLayer()
        spec_a = layer.GetPrimAtPath("/root{model=a}hero_modelMain")
        spec_b = layer.GetPrimAtPath("/root{model=b}hero_modelMain")
        self.assertEqual(spec_a.attributes["mayaReference"].default.path,
                         path_v2)
        self.assertEqual(spec_b.attributes["mayaReference"].default.path,
                         path)

        loader.remove(self.get_container(containers["a"]))
        self.assertFalse(layer.GetPrimAtPath("/root{model=a}hero_modelMain"))
        self.assertTrue(layer.GetPrimAtPath("/root{model=b}hero_modelMain"))
        self.assertTrue(
            stage.GetPrimAtPath(containers["b"]["prim_path"]).IsValid())
        self.assertEqual(
            [c["representation"] for c in self.get_usd_containers()],
            ["repre_b"]
        )

    def test_lock_and_unlock_version(self):
        path = self.make_maya_file("cubeA")
        cmds.select(clear=True)
        container = self.load(path, "repre1")

        self.lock_version.set_version_locked(container, True)
        self.assertIs(self.get_container(container)["version_locked"], True)
        self.lock_version.set_version_locked(
            self.get_container(container), False)
        self.assertFalse(self.get_container(container)["version_locked"])


class TestHostListing(BaseMayaUsdProxyTest):

    def test_ls_with_maya_and_usd_containers(self):
        """`ls()` lists both Maya node and USD containers"""
        path = self.make_usd_file("asset")
        cmds.select(clear=True)
        loader = self.add_reference_module.MayaUsdProxyReferenceUsd()
        loader.load(make_context(path, "repreUsd"), name="modelMain")

        cube = cmds.polyCube()[0]
        self.pipeline.containerise(
            name="modelMain",
            namespace="hero_01_",
            nodes=[cube],
            context=make_context(path, "repreMaya"),
            loader="ReferenceLoader",
        )

        containers = list(self.pipeline.ls())
        self.assertEqual(
            sorted(c["representation"] for c in containers),
            ["repreMaya", "repreUsd"]
        )

        from ayon_maya.api.lib import get_container_members
        for container in containers:
            members = get_container_members(container)
            if self.usdlib.is_usd_container(container):
                self.assertEqual(members, [container["objectName"]])
            else:
                self.assertTrue(members)


def run():
    """Run the tests and return whether they all passed."""
    cmds.loadPlugin("mayaUsdPlugin", quiet=True)
    print("Maya {}, mayaUsd {}".format(
        cmds.about(version=True),
        cmds.pluginInfo("mayaUsdPlugin", query=True, version=True)
    ))
    suite = unittest.TestSuite()
    for test_case in (
        TestUsdAddReferenceLoader,
        TestUsdAddMayaReferenceLoader,
        TestHostListing,
    ):
        suite.addTests(
            unittest.defaultTestLoader.loadTestsFromTestCase(test_case))
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(
        suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run()
    if IS_STANDALONE:
        maya.standalone.uninitialize()
        sys.exit(0 if success else 1)
