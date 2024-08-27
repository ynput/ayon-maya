import inspect

import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin


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

        def _is_plugin_active(plugin: str, default: bool = False) -> bool:
            """Return whether plugin is active for instance"""
            publish_attributes = instance.data["publish_attributes"]
            return publish_attributes.get(plugin, {}).get("active", default)

        if (
            "animation.fbx" in instance.data["families"]
            or _is_plugin_active("ExtractAnimation", default=True)
            or _is_plugin_active("ExtractMayaUsdAnim")
            or _is_plugin_active("ExtractMultiverseUsdAnim")
        ):
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
