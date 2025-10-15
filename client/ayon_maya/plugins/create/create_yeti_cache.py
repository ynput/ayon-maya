from ayon_maya.api import (
    lib,
    plugin
)
from ayon_core.lib import NumberDef, BoolDef


class CreateYetiCache(plugin.MayaCreator):
    """Output for procedural plugin nodes of Yeti """

    identifier = "io.openpype.creators.maya.yeticache"
    label = "Yeti Cache"
    # product_type to be defined in the project settings
    # use product_base_type instead
    # see https://github.com/ynput/ayon-core/issues/1297
    product_base_type = product_type = "yeticache"
    icon = "pagelines"

    def get_instance_attr_defs(self):

        defs = [
            BoolDef("farm",
                    label="Submit to Farm",
                    default=False),
            NumberDef("preroll",
                      label="Preroll",
                      minimum=0,
                      default=0,
                      decimals=0)
        ]

        # Add animation data without step and handles
        defs.extend(lib.collect_animation_defs(
            create_context=self.create_context))
        remove = {"step", "handleStart", "handleEnd"}
        defs = [attr_def for attr_def in defs if attr_def.key not in remove]

        # Add samples after frame range
        defs.append(
            NumberDef("samples",
                      label="Samples",
                      default=3,
                      decimals=0)
        )

        return defs
