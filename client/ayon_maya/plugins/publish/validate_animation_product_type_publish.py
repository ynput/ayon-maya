import inspect

import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin

import pyblish.api


class ValidateAnimationProductTypePublish(plugin.MayaInstancePlugin):
    """Validate at least a single product type is exported for the instance.
    
    Validate either fbx animation collector or collect animation output 
    geometry(Alembic) enabled for publishing otherwise no products
    would be generated for the instance - publishing nothing valid.
    """

    order = ValidateContentsOrder
    families = ["animation"]
    label = "Animation Product Type Publish"
    actions = [ayon_maya.api.action.SelectInvalidAction]

    @classmethod
    def get_invalid(cls, instance):

        plugins = instance.context.data["create_context"].publish_plugins
        plugins_by_name = {plugin.__name__: plugin for plugin in plugins}

        def _is_plugin_active(plugin_name: str) -> bool:
            """Return whether plugin is active for instance"""
            # Check if Plug-in is found
            plugin = plugins_by_name.get(plugin_name)
            if not plugin:
                cls.log.debug(f"Plugin {plugin_name} not found. "
                              f"It may be disabled in settings")
                return False

            # Check if plug-in is globally enabled
            if not getattr(plugin, "enabled", True):
                cls.log.debug(f"Plugin {plugin_name} is disabled. "
                              f"It is disabled in settings")
                return False

            # Check if optional state has active state set to False
            publish_attributes = instance.data["publish_attributes"]
            default_active = getattr(plugin, "active", True)
            active_for_instance = publish_attributes.get(
                plugin_name, {}).get("active", default_active)
            if not active_for_instance:
                cls.log.debug(
                    f"Plugin {plugin_name} is disabled for this instance.")
                return False

            # Check if the instance, according to pyblish is a match for the
            # plug-in. This may e.g. be excluded due to different families
            # or matching algorithm (e.g. ExtractMultiverseUsdAnim uses
            # `pyblish.api.Subset`
            if not pyblish.api.instances_by_plugin([instance], plugin):
                cls.log.debug(
                    f"Plugin {plugin_name} does not match for this instance.")
                return False

            return True

        active_check = {
            "fbx": "animation.fbx" in instance.data["families"],
            "ExtractAnimation": _is_plugin_active("ExtractAnimation"),
            "ExtractMayaUsdAnim": _is_plugin_active("ExtractMayaUsdAnim"),
            "ExtractMultiverseUsdAnim": _is_plugin_active(
                "ExtractMultiverseUsdAnim"),
        }
        active = [key for key, state in active_check.items() if state]

        if active:
            active_str = ", ".join(active)
            cls.log.debug(f"Found active animation extractions: {active_str}")
            return []

        return [instance.data["instance_node"]]

    def process(self, instance):
        invalid = self.get_invalid(instance)
        if invalid:
            name = invalid[0]
            raise PublishValidationError(
                f"Animation instance generates no products: {name}\n"
                "Make sure to enable at least one of the export(s) "
                "product types: FBX, Alembic and/or USD.",
                description=self.get_description()
            )

    @staticmethod
    def get_description():
        return inspect.cleandoc("""
            ## Instance generates no products

            The animation instance generates no products. As a result of that
            there is nothing to publish.
            
            Please make sure to enable at least one of the product types to 
            export: FBX, Alembic and/or USD.
        """)
