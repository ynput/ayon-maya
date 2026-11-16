import inspect
from collections import defaultdict

import ayon_maya.api.action
from ayon_core.pipeline.publish import (
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_maya.api import plugin
from maya import cmds


class ValidateLookNoDefaultShaders(plugin.MayaInstancePlugin):
    """Validate if any node has a connection to a default shader.

    This checks whether the look has any members of:
    - lambert1
    - initialShadingGroup
    - initialParticleSE
    - particleCloud1

    If any of those is present it will raise an error. A look is not allowed
    to have any of the "default" shaders present in a scene as they can
    introduce problems when referenced (overriding local scene shaders).

    To fix this no shape nodes in the look must have any of default shaders
    applied.

    """

    order = ValidateContentsOrder - 0.01
    families = ['look']
    label = 'Look No Default Shaders'
    actions = [ayon_maya.api.action.SelectInvalidAction]

    DEFAULT_SHADERS = {"lambert1", "initialShadingGroup",
                      "initialParticleSE", "particleCloud1"}

    def process(self, instance):
        """Process all the nodes in the instance"""
        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                "Nodes found with default shader assigned. "
                "Please assign a different shader.",
                description=self.get_description()
            )

    @classmethod
    def get_invalid(cls, instance):

        invalid = set()
        invalid_by_shader = defaultdict(list)
        for node in instance:
            # Get shading engine connections
            shaders = cmds.listConnections(node, type="shadingEngine") or []
            for shader in cls.DEFAULT_SHADERS.intersection(shaders):
                invalid_by_shader[shader].append(node)
                invalid.add(node)

        # Log all the invalid connections
        for shader, nodes in invalid_by_shader.items():
            node_list = "\n".join(f"- {node}" for node in sorted(nodes))
            cls.log.error(
                f"Default shader '{shader}' found on:\n{node_list}"
            )

        return list(invalid)

    @staticmethod
    def get_description() -> str:
        return inspect.cleandoc("""
            ### Default shaders are assigned
            
            Some nodes in the look have default shaders assigned to them. 
            Default shaders are not allowed in the look as they can introduce
            problems when referenced (overriding local scene shaders). 
            
            Avoid using for example _lambert1_ or _standardSurface1_ in your 
            look.
            
            To fix this, please assign a different shader to the nodes.
        """)