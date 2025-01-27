import inspect

import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    RepairAction,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin
from maya import cmds


class ValidateShadingEngine(plugin.MayaInstancePlugin,
                            OptionalPyblishPluginMixin):
    """Validate all shading engines are named after the surface material.

    Shading engines should be named "{surface_shader}SG"
    """

    order = ValidateContentsOrder
    families = ["look"]
    label = "Look Shading Engine Naming"
    actions = [
        ayon_maya.api.action.SelectInvalidAction, RepairAction
    ]
    optional = True

    # The default connections to check
    def process(self, instance):
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:
            node_list = "\n".join(f"- {node}" for node in invalid)
            raise PublishValidationError(
                "Found assigned shaders with incorrect names:"
                "\n{}".format(node_list),
                description=self.get_description()
            )

    @classmethod
    def get_invalid(cls, instance):
        shapes = cmds.ls(instance, type=["nurbsSurface", "mesh"], long=True)
        if not shapes:
            return []

        ignored_default_nodes = set(cmds.ls(defaultNodes=True))
        shading_engines = set(cmds.listConnections(
            shapes, destination=True, type="shadingEngine"
        ) or [])
        invalid = []
        for shading_engine in sorted(shading_engines):
            materials = cmds.listConnections(
                shading_engine + ".surfaceShader",
                source=True, destination=False
            )
            if not materials:
                cls.log.warning(
                    "Shading engine '{}' has no material connected to its "
                    ".surfaceShader attribute.".format(shading_engine))
                continue

            material = materials[0]  # there should only ever be one input
            name = material + "SG"
            if shading_engine != name:
                # Ignore referenced or read-only shading engines

                if cmds.referenceQuery(shading_engine,
                                       isNodeReferenced=True):
                    cls.log.warning(
                        "Ignoring referenced shading engine "
                        f"with invalid name: {shading_engine}")

                if shading_engine in ignored_default_nodes:
                    cls.log.warning(
                        "Ignoring default shading engine "
                        f"with invalid name: {shading_engine}")
                    continue

                invalid.append(shading_engine)

        return list(set(invalid))

    @classmethod
    def repair(cls, instance):
        shading_engines = cls.get_invalid(instance)
        for shading_engine in shading_engines:
            name = (
                cmds.listConnections(shading_engine + ".surfaceShader")[0]
                + "SG"
            )
            cmds.rename(shading_engine, name)

    @staticmethod
    def get_description():
        return inspect.cleandoc("""
            ### Shaders found with incorrect names
            
            The shading engine of a shader should be named after the connected
            material to its `.surfaceShader` attribute. The name should be
            `"{material}SG"`.
            
            Use the repair action to rename the shading engine to the correct
            names automatically.
        """)
