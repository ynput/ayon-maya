"""Tests for `validate_clashing_sibling_names`.

The validator imports `ayon_core`, `pyblish` and the Maya plug-in API. To
keep the tests runnable with a plain `mayapy` (no AYON installation needed)
the minimal dependencies are stubbed before loading the validator by path.
For that reason the tests must run in a plain `mayapy` process, not inside
a Maya session that already has AYON loaded.

Run with `mayapy` of the Maya version you want to test, via the test
runner (`python tests/run_maya_tests.py`) or directly, e.g.:

    mayapy tests/client/ayon_maya/plugins/publish/test_validate_clashing_sibling_names.py  # noqa: E501

See: https://github.com/ynput/ayon-maya/issues/47
"""
import importlib.util
import logging
import os
import sys
import types
import unittest

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
MODULE_PATH = os.path.join(
    REPO_ROOT, "client", "ayon_maya", "plugins", "publish",
    "validate_clashing_sibling_names.py")


class PublishValidationError(Exception):
    """Stand-in for `ayon_core.pipeline.publish.PublishValidationError`."""

    def __init__(self, message, description=None):
        super(PublishValidationError, self).__init__(message)
        self.description = description


class MayaInstancePlugin:
    """Stand-in for `ayon_maya.api.plugin.MayaInstancePlugin`."""

    log = logging.getLogger("test-validate-clashing-sibling-names")

    def is_active(self, data):
        return True


def _all_instances(instances, plugin):
    """Stand-in for `pyblish.api.instances_by_plugin`."""
    if getattr(plugin, "matches", True):
        return list(instances)
    return []


def _highest_in_hierarchy(nodes):
    """Stand-in for `ayon_maya.api.lib.get_highest_in_hierarchy`."""
    return list(nodes)


def _add_module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _install_stubs():
    if "ayon_core" in sys.modules:
        raise RuntimeError(
            "This test stubs the AYON modules and must be run in a plain "
            "`mayapy` process, without AYON loaded.")

    pyblish = _add_module("pyblish")
    pyblish.api = _add_module(
        "pyblish.api", instances_by_plugin=_all_instances)

    ayon_core = _add_module("ayon_core")
    ayon_core.pipeline = _add_module("ayon_core.pipeline")
    _add_module(
        "ayon_core.pipeline.publish",
        OptionalPyblishPluginMixin=type("OptionalPyblishPluginMixin", (), {}),
        PublishValidationError=PublishValidationError,
        ValidateContentsOrder=0,
    )

    ayon_maya = _add_module("ayon_maya")
    ayon_maya_api = _add_module("ayon_maya.api")
    ayon_maya_api.action = _add_module(
        "ayon_maya.api.action", SelectInvalidAction=object)
    ayon_maya_api.plugin = _add_module(
        "ayon_maya.api.plugin", MayaInstancePlugin=MayaInstancePlugin)
    ayon_maya_api.lib = _add_module(
        "ayon_maya.api.lib",
        get_highest_in_hierarchy=_highest_in_hierarchy)
    ayon_maya.api = ayon_maya_api


def _load_validator():
    _install_stubs()
    spec = importlib.util.spec_from_file_location(
        "validate_clashing_sibling_names", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load_validator()


class FakeInstance:
    """Minimal pyblish instance for the validator."""

    def __init__(self, nodes=(), publish_plugins=(), publish_attributes=None):
        self.nodes = list(nodes)
        self.data = {}
        if publish_attributes is not None:
            self.data["publish_attributes"] = publish_attributes
        self.context = types.SimpleNamespace(data={
            "create_context": types.SimpleNamespace(
                publish_plugins=list(publish_plugins))
        })

    def __iter__(self):
        return iter(self.nodes)


def extractor(name, strip_namespaces=None, enabled=True, active=True,
              matches=True):
    """Return a fake extractor plug-in class."""
    return type(name, (), {
        "enabled": enabled,
        "active": active,
        "matches": matches,
        "stripNamespaces": strip_namespaces,
    })


NODES = ["|group|hero_01_:_GRP", "|group|hero_02_:_GRP"]


class TestFamilies(unittest.TestCase):

    def test_covers_alembic_families(self):
        families = validator.ValidateClashingSiblingNames.families
        for family in ("pointcache", "animation", "model",
                       "vrayproxy.alembic"):
            self.assertIn(family, families)

    def test_covers_usd(self):
        self.assertIn("usd", validator.ValidateClashingSiblingNames.families)


class TestGetInvalid(unittest.TestCase):

    def setUp(self):
        self.plugin = validator.ValidateClashingSiblingNames()

    def test_flags_namespace_clash_between_siblings(self):
        nodes = ["|group|hero_01_:_GRP", "|group|hero_02_:_GRP"]
        self.assertEqual(
            sorted(self.plugin.get_invalid(FakeInstance(nodes))),
            sorted(nodes))

    def test_ignores_unique_names(self):
        nodes = ["|group|hero_01_:_GRP", "|group|hero_02_:_GRP2"]
        self.assertEqual(
            self.plugin.get_invalid(FakeInstance(nodes)), [])

    def test_ignores_same_name_under_different_parents(self):
        nodes = ["|a|hero_01_:_GRP", "|b|hero_02_:_GRP"]
        self.assertEqual(
            self.plugin.get_invalid(FakeInstance(nodes)), [])

    def test_remove_namespace(self):
        self.assertEqual(
            validator.remove_namespace("|aa:bb:foo|aa:bb:bar"),
            "|foo|bar")


class TestRequiresUniqueSiblingNames(unittest.TestCase):

    def setUp(self):
        self.plugin = validator.ValidateClashingSiblingNames()

    def requires(self, *plugins, **publish_attributes):
        return self.plugin.requires_unique_sibling_names(
            FakeInstance(NODES, plugins, publish_attributes or None))

    def test_alembic_requires_unique_names_when_stripping(self):
        self.assertTrue(
            self.requires(extractor("ExtractAlembic", strip_namespaces=True)))

    def test_alembic_requires_unique_names_without_stripping(self):
        # Maya discards the namespaces when referencing, so unique names
        # are required regardless of the export setting.
        self.assertTrue(
            self.requires(extractor("ExtractAlembic", strip_namespaces=False)))

    def test_animation_requires_unique_names_without_stripping(self):
        self.assertTrue(self.requires(
            extractor("ExtractAnimation", strip_namespaces=False)))

    def test_usd_only_requires_unique_names_when_stripping(self):
        self.assertFalse(self.requires(
            extractor("ExtractMayaUsdPointcache", strip_namespaces=False)))
        self.assertTrue(self.requires(
            extractor("ExtractMayaUsdPointcache", strip_namespaces=True)))

    def test_inactive_extractor_is_ignored(self):
        self.assertFalse(self.requires(
            extractor("ExtractAlembic", strip_namespaces=False),
            ExtractAlembic={"active": False}))

    def test_disabled_extractor_is_ignored(self):
        self.assertFalse(self.requires(
            extractor("ExtractAlembic", strip_namespaces=False,
                      enabled=False)))

    def test_does_not_match_extractor_is_ignored(self):
        self.assertFalse(self.requires(
            extractor("ExtractAlembic", strip_namespaces=False,
                      matches=False)))

    def test_no_extractor(self):
        self.assertFalse(self.requires())


class TestProcess(unittest.TestCase):

    def setUp(self):
        self.plugin = validator.ValidateClashingSiblingNames()

    def test_raises_on_clash(self):
        instance = FakeInstance(
            NODES,
            [extractor("ExtractAlembic", strip_namespaces=False)],
            {"ExtractAlembic": {}})
        with self.assertRaises(PublishValidationError) as context:
            self.plugin.process(instance)
        self.assertIn("discards the namespaces",
                      context.exception.description)

    def test_skips_runtime_instance(self):
        # Runtime instances have no publish attributes.
        self.plugin.process(FakeInstance(
            NODES, [extractor("ExtractAlembic", strip_namespaces=False)]))

    def test_skips_without_alembic_extractor(self):
        self.plugin.process(FakeInstance(NODES, [], {}))


if __name__ == "__main__":
    unittest.main()
