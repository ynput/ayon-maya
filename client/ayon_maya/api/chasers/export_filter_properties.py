import re
import fnmatch
import logging
from typing import List

import mayaUsd.lib as mayaUsdLib
from pxr import Sdf


def log_errors(fn):
    """Decorator to log errors on error"""

    def wrap(*args, **kwargs):

        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            logging.error(exc, exc_info=True)
            raise

    return wrap


def remove_spec(spec: Sdf.Spec):
    """Remove Sdf.Spec authored opinion."""
    if spec.expired:
        return

    if isinstance(spec, Sdf.PrimSpec):
        # PrimSpec
        parent = spec.nameParent
        if parent:
            view = parent.nameChildren
        else:
            # Assume PrimSpec is root prim
            view = spec.layer.rootPrims
        del view[spec.name]

    elif isinstance(spec, Sdf.PropertySpec):
        # Relationship and Attribute specs
        del spec.owner.properties[spec.name]

    elif isinstance(spec, Sdf.VariantSetSpec):
        # Owner is Sdf.PrimSpec (or can also be Sdf.VariantSpec)
        del spec.owner.variantSets[spec.name]

    elif isinstance(spec, Sdf.VariantSpec):
        # Owner is Sdf.VariantSetSpec
        spec.owner.RemoveVariant(spec)

    else:
        raise TypeError(f"Unsupported spec type: {spec}")


def remove_layer_specs(layer: Sdf.Layer, spec_paths: List[Sdf.Path]):
    # Iterate in reverse so we iterate the highest paths
    # first, so when removing a spec the children specs
    # are already removed
    for spec_path in reversed(spec_paths):
        spec = layer.GetObjectAtPath(spec_path)
        if not spec or spec.expired:
            continue
        remove_spec(spec)


def match_pattern(name: str, text_pattern: str) -> bool:
    """SideFX Houdini like pattern matching"""
    patterns = text_pattern.split(" ")
    is_match = False
    for pattern in patterns:
        # * means any character
        # ? means any single character
        # [abc] means a, b, or c
        pattern = pattern.strip(" ")
        if not pattern:
            continue

        excludes = pattern[0] == "^"

        # If name is already matched against earlier pattern in the text
        # pattern, then we can skip the pattern if it is not an exclude pattern
        if is_match and not excludes:
            continue

        if excludes:
            pattern = pattern[1:]

        regex = fnmatch.translate(pattern)
        match = re.match(regex, name)
        if match:
            is_match = not excludes
    return is_match



class FilterPropertiesExportChaser(mayaUsdLib.ExportChaser):
    """Remove property specs based on pattern"""

    name = "AYON_filterProperties"

    def __init__(self, factoryContext, *args, **kwargs):
        super().__init__(factoryContext, *args, **kwargs)
        self.log = logging.getLogger(self.__class__.__name__)
        self.stage = factoryContext.GetStage()
        self.job_args = factoryContext.GetJobArgs()

    @log_errors
    def PostExport(self):

        chaser_args = self.job_args.allChaserArgs[self.name]
        # strip all or use user-specified pattern
        pattern = chaser_args.get("pattern", "*")
        for layer in self.stage.GetLayerStack():

            specs_to_remove = []

            def find_attribute_specs_to_remove(path: Sdf.Path):
                if not path.IsPropertyPath():
                    return

                spec = layer.GetObjectAtPath(path)
                if not spec:
                    return

                if not isinstance(spec, Sdf.PropertySpec):
                    return

                if not match_pattern(spec.name, pattern):
                    self.log.debug(f"Removing spec: %s", path)
                    specs_to_remove.append(path)
                else:
                    self.log.debug(f"Keeping spec: %s", path)

            layer.Traverse("/", find_attribute_specs_to_remove)

            remove_layer_specs(layer, specs_to_remove)

        return True