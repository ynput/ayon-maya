"""Tests for `ayon_maya.api.lib_rendersetup` override lookups.

These tests validate that `get_attr_in_layer` returns the same value for an
attribute as Maya does when actually switching to the render setup layer,
including overrides inside (nested) groups and mixed group/collection
priority orders. See: https://github.com/ynput/ayon-maya/issues/195

WARNING: Each test creates a new scene (forcefully), discarding the current
scene. When run in an interactive Maya session with unsaved changes the tests
refuse to run.

Run with `mayapy` of the Maya version you want to test (no AYON needed):

    mayapy tests/client/ayon_maya/api/test_lib_rendersetup.py

Or from Maya's Script Editor (Python), e.g. launched via AYON so the
`ayon_maya` of that session is tested:

    import runpy
    runpy.run_path(
        r"path/to/ayon-maya/tests/client/ayon_maya/api/test_lib_rendersetup.py",
        run_name="__main__"
    )

"""
import os
import sys
import types
import unittest
import importlib.util

import maya.standalone
from maya import cmds

IS_STANDALONE = not hasattr(cmds, "about")
if IS_STANDALONE:
    maya.standalone.initialize()

from maya.app.renderSetup.model import renderSetup  # noqa: E402


REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
LIB_RENDERSETUP_PATH = os.path.join(
    REPO_ROOT, "client", "ayon_maya", "api", "lib_rendersetup.py")

NODE = "pCube1"
ATTR = "scaleX"
NODE_ATTR = "{}.{}".format(NODE, ATTR)
DEFAULT_VALUE = 1.0
LAYER = "rs_testLayer"


def _load_lib_rendersetup():
    """Return the `lib_rendersetup` module to test.

    Use the `ayon_maya` of the current session when it is importable (e.g.
    Maya launched via AYON). Otherwise, load `lib_rendersetup.py` from this
    repository with a minimal stand-in for `ayon_maya.api.lib`, since that
    module requires a full AYON environment and `lib_rendersetup` only
    needs its `get_attribute` function.
    """
    try:
        from ayon_maya.api import lib_rendersetup
        return lib_rendersetup
    except ImportError:
        pass

    def get_attribute(plug, asString=False, **kwargs):
        if asString:
            kwargs["asString"] = True
        return cmds.getAttr(plug, **kwargs)

    stubs = {}
    for name in ("ayon_maya", "ayon_maya.api"):
        stub = types.ModuleType(name)
        stub.__path__ = []
        stubs[name] = stub
    lib_stub = types.ModuleType("ayon_maya.api.lib")
    lib_stub.get_attribute = get_attribute
    stubs["ayon_maya.api.lib"] = lib_stub

    originals = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location(
            "_test_lib_rendersetup", LIB_RENDERSETUP_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
    return module


lib_rendersetup = _load_lib_rendersetup()


def _supports_groups():
    from maya.app.renderSetup.model import renderLayer
    return hasattr(renderLayer.RenderLayer, "createGroup")


requires_groups = unittest.skipUnless(
    _supports_groups(), "Render Setup groups not supported in this Maya")


class TestGetAttrInLayer(unittest.TestCase):
    """Compare `get_attr_in_layer` against Maya's actual layer value.

    Children are created in priority order: children created later have
    higher priority (they are lower in the Render Setup UI).
    """

    @classmethod
    def setUpClass(cls):
        if not IS_STANDALONE and cmds.file(query=True, modified=True):
            raise RuntimeError(
                "Current scene has unsaved changes. Save or discard them "
                "before running these tests, as they create new scenes.")

    def setUp(self):
        cmds.file(new=True, force=True)
        cmds.polyCube(name=NODE)
        self.rs = renderSetup.instance()
        self.rs.clearAll()
        self.layer = self.rs.createRenderLayer(LAYER)

    def tearDown(self):
        self.rs.clearAll()
        cmds.file(new=True, force=True)

    # region Helpers
    def collection(self, parent, name):
        col = parent.createCollection(name)
        col.getSelector().setPattern(NODE)
        return col

    def abs_override(self, col, value):
        override = col.createAbsoluteOverride(NODE, ATTR)
        override.setAttrValue(value)
        return override

    def rel_override(self, col, multiply, offset):
        override = col.createRelativeOverride(NODE, ATTR)
        override.setMultiply(multiply)
        override.setOffset(offset)
        return override

    def assert_layer_value(self, expected):
        """Assert the value in the layer, queried without switching to it,
        matches both `expected` and the value Maya has in the layer."""
        default_layer = self.rs.getDefaultRenderLayer()

        # Get the actual value Maya evaluates in the layer
        self.rs.switchToLayer(self.layer)
        actual = cmds.getAttr(NODE_ATTR)
        self.rs.switchToLayer(default_layer)
        self.assertAlmostEqual(
            actual, expected,
            msg="Test scene is not set up as expected: Maya evaluates "
                "{} to {} in the layer.".format(NODE_ATTR, actual))

        # Query from the default layer, without switching
        value = lib_rendersetup.get_attr_in_layer(
            NODE_ATTR, layer=LAYER, as_string=False)
        self.assertAlmostEqual(value, expected)
        self.assertEqual(
            self.rs.getVisibleRenderLayer().name(), default_layer.name(),
            "get_attr_in_layer should not switch layers")
    # endregion

    # region Collections only
    def test_no_overrides(self):
        self.collection(self.layer, "col")
        self.assert_layer_value(DEFAULT_VALUE)

    def test_collection(self):
        self.abs_override(self.collection(self.layer, "col"), 10.0)
        self.assert_layer_value(10.0)

    def test_collection_disabled(self):
        col = self.collection(self.layer, "col")
        self.abs_override(col, 10.0)
        col.setSelfEnabled(False)
        self.assert_layer_value(DEFAULT_VALUE)

    def test_later_collection_wins(self):
        self.abs_override(self.collection(self.layer, "colA"), 10.0)
        self.abs_override(self.collection(self.layer, "colB"), 20.0)
        self.assert_layer_value(20.0)

    def test_relative_over_absolute(self):
        self.abs_override(self.collection(self.layer, "colA"), 10.0)
        self.rel_override(self.collection(self.layer, "colB"), 2.0, 1.0)
        self.assert_layer_value(21.0)

    def test_absolute_over_relative(self):
        self.rel_override(self.collection(self.layer, "colA"), 2.0, 1.0)
        self.abs_override(self.collection(self.layer, "colB"), 10.0)
        self.assert_layer_value(10.0)

    def test_override_then_subcollection(self):
        col = self.collection(self.layer, "col")
        self.abs_override(col, 10.0)
        self.abs_override(self.collection(col, "sub"), 20.0)
        self.assert_layer_value(20.0)

    def test_subcollection_then_override(self):
        col = self.collection(self.layer, "col")
        self.abs_override(self.collection(col, "sub"), 20.0)
        self.abs_override(col, 10.0)
        self.assert_layer_value(10.0)

    def test_subcollection_disabled(self):
        col = self.collection(self.layer, "col")
        self.abs_override(col, 10.0)
        sub = self.collection(col, "sub")
        self.abs_override(sub, 20.0)
        sub.setSelfEnabled(False)
        self.assert_layer_value(10.0)
    # endregion

    # region Groups
    @requires_groups
    def test_collection_in_group(self):
        group = self.layer.createGroup("grp")
        self.abs_override(self.collection(group, "col"), 10.0)
        self.assert_layer_value(10.0)

    @requires_groups
    def test_collection_in_nested_groups(self):
        group = self.layer.createGroup("grp")
        subgroup = group.createGroup("subGrp")
        self.abs_override(self.collection(subgroup, "col"), 10.0)
        self.assert_layer_value(10.0)

    @requires_groups
    def test_group_disabled(self):
        group = self.layer.createGroup("grp")
        self.abs_override(self.collection(group, "col"), 10.0)
        group.setSelfEnabled(False)
        self.assert_layer_value(DEFAULT_VALUE)

    @requires_groups
    def test_parent_group_disabled(self):
        group = self.layer.createGroup("grp")
        subgroup = group.createGroup("subGrp")
        self.abs_override(self.collection(subgroup, "col"), 10.0)
        group.setSelfEnabled(False)
        self.assert_layer_value(DEFAULT_VALUE)

    @requires_groups
    def test_group_then_collection(self):
        group = self.layer.createGroup("grp")
        self.abs_override(self.collection(group, "colInGroup"), 10.0)
        self.abs_override(self.collection(self.layer, "col"), 20.0)
        self.assert_layer_value(20.0)

    @requires_groups
    def test_collection_then_group(self):
        self.abs_override(self.collection(self.layer, "col"), 20.0)
        group = self.layer.createGroup("grp")
        self.abs_override(self.collection(group, "colInGroup"), 10.0)
        self.assert_layer_value(10.0)

    @requires_groups
    def test_absolute_then_relative_in_group(self):
        self.abs_override(self.collection(self.layer, "col"), 10.0)
        group = self.layer.createGroup("grp")
        self.rel_override(self.collection(group, "colInGroup"), 2.0, 1.0)
        self.assert_layer_value(21.0)

    @requires_groups
    def test_relative_in_group_then_absolute(self):
        group = self.layer.createGroup("grp")
        self.rel_override(self.collection(group, "colInGroup"), 2.0, 1.0)
        self.abs_override(self.collection(self.layer, "col"), 10.0)
        self.assert_layer_value(10.0)

    @requires_groups
    def test_mixed_children_in_group(self):
        group = self.layer.createGroup("grp")
        self.abs_override(
            self.collection(group.createGroup("subGrpA"), "colA"), 10.0)
        self.abs_override(self.collection(group, "colB"), 20.0)
        self.rel_override(
            self.collection(group.createGroup("subGrpC"), "colC"), 2.0, 1.0)
        self.assert_layer_value(41.0)

    @requires_groups
    def test_mixed_children_in_group_reversed(self):
        group = self.layer.createGroup("grp")
        self.rel_override(
            self.collection(group.createGroup("subGrpA"), "colA"), 2.0, 1.0)
        self.abs_override(self.collection(group, "colB"), 20.0)
        self.abs_override(
            self.collection(group.createGroup("subGrpC"), "colC"), 10.0)
        self.assert_layer_value(10.0)
    # endregion


def run():
    """Run the tests and return whether they all passed."""
    print("Maya {}, testing: {}".format(
        cmds.about(version=True), lib_rendersetup.__file__))
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        TestGetAttrInLayer)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(
        suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run()
    if IS_STANDALONE:
        maya.standalone.uninitialize()
        sys.exit(0 if success else 1)
