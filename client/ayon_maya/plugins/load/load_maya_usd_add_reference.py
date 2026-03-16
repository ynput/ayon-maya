# -*- coding: utf-8 -*-
import uuid

from ayon_core.pipeline import load
from ayon_core.pipeline.load import get_representation_path_from_context
from ayon_maya.api.usdlib import (
    containerise_prim,
    iter_ufe_usd_selection
)

from maya import cmds
import mayaUsd


def _get_stage_from_proxy_shape(shape_dag_path):
    """Get USD stage from a mayaUsdProxyShape node.

    Works across different mayaUsd plugin versions by using the
    OpenMaya API to access the stage directly from the node.

    Args:
        shape_dag_path (str): Full DAG path to the mayaUsdProxyShape node.

    Returns:
        pxr.Usd.Stage or None
    """
    # Try mayaUsd.lib.GetStage (available in newer versions)
    get_stage_fn = getattr(mayaUsd.lib, "GetStage", None)
    if get_stage_fn is not None:
        return get_stage_fn(shape_dag_path)

    # Fallback: use OpenMaya to call the getUsdStage command on the node
    import maya.OpenMaya as om
    sel = om.MSelectionList()
    sel.add(shape_dag_path)
    dag = om.MDagPath()
    sel.getDagPath(0, dag)
    fn = om.MFnDependencyNode(dag.node())
    stage_data_plug = fn.findPlug("outStageCacheId", False)
    # Use mayaUsd mel command as last resort
    shape_short = shape_dag_path.split("|")[-1]
    import maya.mel as mel
    stage = mel.eval(f'mayaUsdGetStage "{shape_short}"') if hasattr(
        mel, 'eval') else None
    if stage:
        return stage

    # Final fallback: use mayaUsd.ufe.getStage with UFE-style path
    ufe_path = "|world" + shape_dag_path
    return mayaUsd.ufe.getStage(ufe_path)


class MayaUsdProxyReferenceUsd(load.LoaderPlugin):
    """Add a USD Reference into mayaUsdProxyShape

    TODO: It'd be much easier if this loader would be capable of returning the
        available containers in the scene based on the AYON URLs inside a USD
        stage. That way we could potentially avoid the need the custom
        identifier, stay closer to USD native data and rely solely on the
        AYON:asset=blue,subset=modelMain,version=1 url

    """

    product_types = {"model", "usd", "pointcache", "animation"}
    representations = ["usd", "usda", "usdc", "usdz", "abc"]

    label = "USD Add Reference"
    order = 0
    icon = "code-fork"
    color = "orange"

    identifier_key = "ayon_identifier"

    def load(self, context, name=None, namespace=None, options=None):

        from pxr import Sdf

        selection = list(iter_ufe_usd_selection())
        if not selection:
            # No USD prim selected: create a new proxy stage and add reference
            # to its root prim.
            import mayaUsd_createStageWithNewLayer
            from pxr import UsdGeom

            cmds.loadPlugin("mayaUsdPlugin", quiet=True)

            shape = mayaUsd_createStageWithNewLayer.createStageWithNewLayer()

            shape_long = cmds.ls(shape, long=True)
            if not shape_long:
                raise RuntimeError(
                    f"Could not find created proxy shape: {shape}"
                )

            stage = _get_stage_from_proxy_shape(shape_long[0])
            if not stage:
                raise RuntimeError(
                    f"Could not get USD stage from proxy shape: {shape_long[0]}\n"
                    f"Available mayaUsd.lib attrs: "
                    f"{[x for x in dir(mayaUsd.lib) if 'tage' in x]}"
                )

            prim_path = "/root"
            UsdGeom.Xform.Define(stage, prim_path)
            root_layer = stage.GetRootLayer()
            root_layer.defaultPrim = prim_path
            prim = stage.GetPrimAtPath(prim_path)
        else:
            assert len(selection) == 1, "Select only one PRIM please"
            ufe_path = selection[0]
            prim = mayaUsd.ufe.ufePathToPrim(ufe_path)

        if not prim:
            raise RuntimeError("Invalid primitive")

        path = get_representation_path_from_context(context)
        references = prim.GetReferences()

        identifier = str(prim.GetPath()) + ":" + str(uuid.uuid4())
        identifier_data = {self.identifier_key: identifier}
        reference = Sdf.Reference(assetPath=path,
                                  customData=identifier_data)

        success = references.AddReference(reference)
        if not success:
            raise RuntimeError("Failed to add reference")

        container = containerise_prim(
            prim,
            name=name,
            namespace=namespace or "",
            context=context,
            loader=self.__class__.__name__
        )

        return container

    def update(self, container, context):
        # type: (dict, dict) -> None
        """Update container with specified representation."""

        from pxr import Sdf

        prim = container["prim"]
        path = self.filepath_from_context(context)
        for references, index in self._get_prim_references(prim):
            reference = references[index]
            new_reference = Sdf.Reference(
                assetPath=path,
                customData=reference.customData,
                layerOffset=reference.layerOffset,
                primPath=reference.primPath
            )
            references[index] = new_reference

        prim.SetCustomDataByKey(
            "ayon:representation", context["representation"]["id"]
        )

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        # type: (dict) -> None
        """Remove loaded container."""
        prim = container["prim"]

        related_references = reversed(list(self._get_prim_references(prim)))
        for references, index in related_references:
            references.remove(references[index])

        prim.ClearCustomDataByKey("ayon")

    def _get_prim_references(self, prim):

        for prim_spec in prim.GetPrimStack():
            if not prim_spec:
                continue

            if not prim_spec.hasReferences:
                continue

            prepended_items = prim_spec.referenceList.prependedItems
            for index, _reference in enumerate(prepended_items):
                yield prepended_items, index
