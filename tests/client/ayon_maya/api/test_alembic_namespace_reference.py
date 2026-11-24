"""Characterize Maya's behaviour for namespaces stored in Alembic caches.

Maya's AbcImport file translator discards the namespaces stored inside an
Alembic cache when the cache is *referenced* and renumbers clashing sibling
names (`_GRP`, `_GRP1`, `_GRP2`) in load order. Nodes inside the reference
are read only, so the names can not be corrected after loading.

`validate_clashing_sibling_names` relies on this behaviour: it requires
unique sibling names because the loaded names are the namespace-stripped
names regardless of the export's `stripNamespaces` setting.

These tests pin that behaviour for Maya 2025 and 2027. If Autodesk ever
fixes the translator, they will fail - which is the signal to reconsider
the validation and the loader workaround.

WARNING: Each test creates a new scene (forcefully), discarding the current
scene. Do not run this in an interactive session with unsaved changes.

Run with `mayapy` of the Maya version you want to test, via the test
runner (`python tests/run_maya_tests.py`) or directly, e.g.:

    mayapy tests/client/ayon_maya/api/test_alembic_namespace_reference.py  # noqa: E501

See: https://github.com/ynput/ayon-maya/issues/47
"""
import os
import shutil
import tempfile
import unittest

import maya.standalone
from maya import cmds

IS_STANDALONE = not hasattr(cmds, "about")
if IS_STANDALONE:
    maya.standalone.initialize()

NAMESPACES = ["hero_01_", "hero_02_", "hero_03_"]


class TestAlembicNamespaceReference(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cmds.loadPlugin("AbcExport", quiet=True)
        cmds.loadPlugin("AbcImport", quiet=True)

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="ayon_maya_abc_")
        self.abc = os.path.join(self.folder, "namespaced.abc")
        self.export_abc(self.abc)

    def tearDown(self):
        cmds.file(new=True, force=True)
        shutil.rmtree(self.folder, ignore_errors=True)

    @staticmethod
    def export_abc(path, strip_namespaces=False):
        """Export three namespaced `_GRP` siblings to an Alembic file."""
        cmds.file(new=True, force=True)
        roots = []
        for namespace in NAMESPACES:
            if not cmds.namespace(exists=namespace):
                cmds.namespace(add=namespace)
            root = cmds.createNode("transform", name=namespace + ":_GRP")
            cube = cmds.polyCube(name=namespace + ":cube_GEO")[0]
            cmds.parent(cube, root, relative=True)
            roots.append(root)

        group = cmds.group(empty=True, name="group")
        cmds.parent(roots, group)
        cmds.select(group, replace=True, hierarchy=True)

        job = "-frameRange 1 1 -selection -file {}".format(path)
        if strip_namespaces:
            job = "-stripNamespaces " + job
        try:
            cmds.AbcExport(j=job)
        except TypeError:
            # Older/newer mayapy bindings may expose the long flag name
            cmds.AbcExport(jobArg=job)
        cmds.select(clear=True)

    def reference(self, namespace="shot010"):
        """Reference the exported cache and return its top level transforms."""
        cmds.file(new=True, force=True)
        cmds.file(self.abc, namespace=namespace, sharedReferenceFile=False,
                  reference=True, type="Alembic")
        return sorted(cmds.ls(namespace + ":_GRP*", long=True))

    def test_reference_discards_namespaces(self):
        nodes = self.reference()
        self.assertEqual(
            sorted(node.rsplit("|", 1)[-1] for node in nodes),
            ["shot010:_GRP", "shot010:_GRP1", "shot010:_GRP2"])

        # The namespaces stored inside the cache are not recreated
        self.assertFalse(cmds.namespace(exists="shot010:hero_01_"))

    def test_referenced_nodes_cannot_be_renamed(self):
        # A loader can therefore not restore the namespaces after loading
        nodes = self.reference()
        with self.assertRaises(RuntimeError):
            cmds.rename(nodes[0], "shot010:renamed")

    def test_strip_namespaces_export_fails_on_clashing_siblings(self):
        # This is why the extractor fails with an Alembic exception when
        # sibling names clash and `stripNamespaces` is enabled; the
        # validator reports it before the export is attempted.
        with self.assertRaises(Exception):
            self.export_abc(os.path.join(self.folder, "stripped.abc"),
                            strip_namespaces=True)


if __name__ == "__main__":
    unittest.main()
