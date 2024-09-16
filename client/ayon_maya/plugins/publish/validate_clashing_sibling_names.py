from collections import defaultdict
import inspect

import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin, lib
import pyblish.api


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
    """Validate siblings have unique names when namespaces are stripped."""

    order = ValidateContentsOrder
    families = ["pointcache", "animation", "usd"]
    label = "Validate clashing sibling names"
    actions = [ayon_maya.api.action.SelectInvalidAction]

    @staticmethod
    def get_invalid(instance):
        """Return all nodes that have non-unique names with siblings when
        namespaces are stripped.

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

        if not self.is_strip_namespaces_enabled(instance):
            return

        invalid = self.get_invalid(instance)
        if invalid:

            report_list = "\n".join(f"- {node}" for node in sorted(invalid))

            raise PublishValidationError(
                "With stripped namespaces there are conflicting sibling names "
                "that are not unique:\n"
                f"{report_list}",
                description=self.get_description())

    def is_strip_namespaces_enabled(self, instance) -> bool:
        """Return whether any extractor is enabled for instance that has
        `stripNamespaces` enabled."""
        # TODO: Preferably there would be a better way to detect whether the
        #   flag was enabled or not.

        plugins = instance.context.data["create_context"].publish_plugins
        plugins_by_name = {plugin.__name__: plugin for plugin in plugins}

        def _is_plugin_active(plugin_name: str) -> bool:
            """Return whether plugin is active for instance"""
            # Check if Plug-in is found
            plugin = plugins_by_name.get(plugin_name)
            if not plugin:
                self.log.debug(f"Plugin {plugin_name} not found. "
                               "It may be disabled in settings")
                return False

            # Check if plug-in is globally enabled
            if not getattr(plugin, "enabled", True):
                self.log.debug(f"Plugin {plugin_name} is disabled. "
                               "It is disabled in settings")
                return False

            # Check if optional state has active state set to False
            publish_attributes = instance.data["publish_attributes"]
            default_active = getattr(plugin, "active", True)
            active_for_instance = publish_attributes.get(
                plugin_name, {}).get("active", default_active)
            if not active_for_instance:
                self.log.debug(
                  f"Plugin {plugin_name} is disabled for this instance.")
                return False

            # Check if the instance, according to pyblish is a match for the
            # plug-in. This may e.g. be excluded due to different families
            # or matching algorithm (e.g. ExtractMultiverseUsdAnim uses
            # `pyblish.api.Subset`
            if not pyblish.api.instances_by_plugin([instance], plugin):
                self.log.debug(
                    f"Plugin {plugin_name} does not match for this instance.")
                return False

            return True

        for plugin_name in [
            "ExtractAlembic",               # pointcache
            "ExtractAnimation",             # animation
            "ExtractMayaUsd",               # usd
            "ExtractMayaUsdPointcache",     # pointcache
            "ExtractMayaUsdAnim",           # animation
        ]:
            if _is_plugin_active(plugin_name):
                plugin = plugins_by_name[plugin_name]

                # Use the value from the instance publish attributes
                publish_attributes = instance.data["publish_attributes"]
                strip_namespaces = publish_attributes.get(
                    plugin_name, {}).get("stripNamespaces")
                if strip_namespaces:
                    return True

                # Find some default on the plugin class, if any
                default = getattr(plugin, "stripNamespaces", False)
                if default:
                    self.log.debug(
                        f"{plugin_name} has strip namespaces enabled as "
                        "default value.")
                    return True
        return False

    def get_description(self):
        return inspect.cleandoc("""
            ### Clashing sibling names with stripped namespaces
            
            The export has **strip namespaces** enabled but a conflict on 
            sibling names are found where, without namespaces, they do not have
            unique names and can not be exported.
            
            To resolve this, either export with 'strip namespaces' disabled or
            reorder the hierarchy so that nodes sharing the parent do not have
            the same name.
        """)
