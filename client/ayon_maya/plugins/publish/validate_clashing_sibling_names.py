from collections import defaultdict
import inspect

import pyblish.api
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)

import ayon_maya.api.action
from ayon_maya.api import plugin, lib


def remove_namespace(path: str) -> str:
    """Remove namespace from full path.

    Example:
        >>> remove_namespace("|aa:bb:foo|aa:bb:bar|cc:hello|dd:world")
        '|foo|bar|hello|world'

    Arguments:
        path (str): Full node path.

    Returns:
        str: Node path with namespaces removed.
    """
    return "|".join(
        name.rsplit(":", 1)[-1] for name in path.split("|")
    )


class ValidateClashingSiblingNames(plugin.MayaInstancePlugin,
                                   OptionalPyblishPluginMixin):
    """Validate siblings have unique names without namespaces."""

    order = ValidateContentsOrder
    # Families that can be published as an Alembic cache which is loaded
    # through the reference loader. `model` and `vrayproxy.alembic` are
    # extracted by `ExtractAlembic`, `usd` by the Maya USD extractors.
    # Proxy `proxyAbc` caches are excluded because they are loaded through
    # the Redshift/V-Ray proxy plug-ins instead of a reference, and camera
    # Alembic (`ExtractCameraAlembic`) is not covered yet.
    families = [
        "pointcache",
        "animation",
        "model",
        "vrayproxy.alembic",
        "usd",
    ]
    label = "Validate clashing sibling names"
    actions = [ayon_maya.api.action.SelectInvalidAction]

    alembic_extractors = (
        "ExtractAlembic",
        "ExtractAnimation",
    )
    usd_extractors = (
        "ExtractMayaUsd",
        "ExtractMayaUsdPointcache",
        "ExtractMayaUsdAnim",
    )

    @staticmethod
    def get_invalid(instance):
        """Return all nodes that have non-unique names with siblings without
        their namespaces.

        Returns:
            list[str]: Non-unique siblings
        """
        stripped_name_to_full_path = defaultdict(set)
        for node in instance:
            stripped_name = remove_namespace(node)
            stripped_name_to_full_path[stripped_name].add(node)

        invalid: "list[str]" = []
        for _stripped_name, nodes in stripped_name_to_full_path.items():
            if len(nodes) > 1:
                invalid.extend(nodes)

        if invalid:
            # We only care about the highest conflicts since child conflicts
            # only occur due to the conflicts higher up anyway
            invalid = lib.get_highest_in_hierarchy(invalid)

        return invalid

    def process(self, instance):
        """Process all the nodes in the instance "objectSet"""
        if not self.is_active(instance.data):
            return

        if "publish_attributes" not in instance.data:
            # This is an instance generated at runtime, for example a USD
            # contribution workflow instance. We will ignore this validation
            self.log.debug("Skipping validation of clashing siblings for"
                           f" '{instance}', because it is a runtime instance"
                           " (has no publish attributes)")
            return

        if not self.requires_unique_sibling_names(instance):
            return

        invalid = self.get_invalid(instance)
        if invalid:

            report_list = "\n".join(f"- {node}" for node in sorted(invalid))

            raise PublishValidationError(
                "With namespaces removed there are conflicting sibling names "
                "that are not unique:\n"
                f"{report_list}",
                description=self.get_description())

    def requires_unique_sibling_names(self, instance) -> bool:
        """Return whether unique sibling names are required for instance.

        An Alembic cache always requires unique sibling names, a USD
        export only when it strips namespaces.

        Nodes inside a referenced Alembic cache are read-only, so names
        can not be corrected after loading. On top of that the Alembic
        importer discards the namespaces stored in the cache and Maya
        renumbers clashing sibling names in load order. Therefore the
        loaded names are the namespace-stripped names whether or not the
        export stripped namespaces, and a clash leads to unstable node
        names between updates (see ayon-maya#47).

        USD prim names never carry Maya namespaces, so a clash there can
        only occur when the export strips namespaces.

        Args:
            instance (Instance): The pyblish instance.

        Returns:
            bool: Whether unique sibling names are required.
        """
        extractors = self.alembic_extractors + self.usd_extractors
        for plugin_name, extractor in self._iter_active_extractors(
                instance, extractors):
            # Alembic caches lose their namespaces on reference regardless
            # of the `stripNamespaces` export setting.
            if plugin_name in self.alembic_extractors:
                return True
            if self._strips_namespaces(instance, plugin_name, extractor):
                return True
        return False

    def _iter_active_extractors(self, instance, plugin_names):
        """Yield the `(plugin_name, extractor)` of active extractors.

        Args:
            instance (Instance): The pyblish instance.
            plugin_names (Iterable[str]): Names of the extractors to check.

        Yields:
            tuple[str, type]: Name and plug-in class of an active extractor.
        """
        for plugin_name in plugin_names:
            extractor = self._get_active_extractor(instance, plugin_name)
            if extractor:
                yield plugin_name, extractor

    def _strips_namespaces(self, instance, plugin_name, extractor) -> bool:
        """Return whether the extractor strips namespaces on export.

        Args:
            instance (Instance): The pyblish instance.
            plugin_name (str): Name of the extractor plug-in.
            extractor (type): The extractor plug-in class.

        Returns:
            bool: Whether namespaces are stripped.
        """
        # TODO: Preferably there would be a better way to detect whether the
        #   flag was enabled or not.
        # Use the value from the instance publish attributes
        publish_attributes = instance.data.get("publish_attributes", {})
        if publish_attributes.get(plugin_name, {}).get("stripNamespaces"):
            return True

        # Find some default on the plugin class, if any
        if getattr(extractor, "stripNamespaces", False):
            self.log.debug(
                f"{plugin_name} has strip namespaces enabled as "
                "default value.")
            return True

        return False

    def _get_active_extractor(self, instance, plugin_name):
        """Return the plug-in if it is active for the instance, else None."""
        publish_plugins = (
            instance.context.data["create_context"].publish_plugins
        )
        plugins_by_name = {
            plugin.__name__: plugin for plugin in publish_plugins
        }

        plugin = plugins_by_name.get(plugin_name)
        if not plugin:
            self.log.debug(f"Plugin {plugin_name} not found. "
                           "It may be disabled in settings")
            return None

        # Check if plug-in is globally enabled
        if not getattr(plugin, "enabled", True):
            self.log.debug(f"Plugin {plugin_name} is disabled. "
                           "It is disabled in settings")
            return None

        # Check if optional state has active state set to False
        publish_attributes = instance.data.get("publish_attributes", {})
        default_active = getattr(plugin, "active", True)
        active_for_instance = publish_attributes.get(
            plugin_name, {}).get("active", default_active)
        if not active_for_instance:
            self.log.debug(
                f"Plugin {plugin_name} is disabled for this instance.")
            return None

        # Check if the instance, according to pyblish is a match for the
        # plug-in. This may e.g. be excluded due to different families
        # or matching algorithm (e.g. ExtractMultiverseUsdAnim uses
        # `pyblish.api.Subset`
        if not pyblish.api.instances_by_plugin([instance], plugin):
            self.log.debug(
                f"Plugin {plugin_name} does not match for this instance.")
            return None

        return plugin

    def get_description(self):
        return inspect.cleandoc("""
            ### Clashing sibling names

            Sibling nodes are found whose names are not unique once their
            namespaces are removed, e.g. `hero_01_:_GRP` and `hero_02_:_GRP`
            under the same parent.

            Maya's Alembic importer discards the namespaces stored in an
            Alembic cache when the cache is *referenced* and then renumbers
            clashing sibling names (`_GRP`, `_GRP1`, `_GRP2`) in load order.
            That makes the node names unstable between versions and can break
            existing reference edits, so the cache can not be loaded
            reliably.

            To resolve this, rename the conflicting nodes so that they are
            unique without their namespace (e.g. rename `hero_01_:_GRP` to
            `hero_01_GRP`), or restructure the hierarchy so that nodes
            sharing a parent do not have the same name.

            Note: disabling 'strip namespaces' on the export does not
            resolve this, because Maya discards the namespaces when
            referencing the cache regardless.
        """)
