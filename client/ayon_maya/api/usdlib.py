"""Library functions for AYON containers inside Maya USD proxy shape stages.

AYON containers loaded into a USD stage store their container data as
`customData` under the `ayon` key. Where that data lives depends on what was
loaded:

- **USD reference containers** store the data on the `Sdf.Reference` itself
  (the reference's own `customData`). As such, the container data is tied
  to that specific composition arc and multiple loaded references on the
  same prim are each their own container. Removing the reference removes
  the container data with it.
- **Prim containers** (e.g. `MayaReference` prims) store the data in the
  prim's `customData`.

Only the stage's local layer stack (the root layer, its sublayers and the
session layer) is searched for containers. Containers authored inside
referenced or payloaded files are not containers of the current scene.

"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Iterator, Optional

from maya import cmds
from pxr import Sdf, Usd

from ayon_core.pipeline.constants import (
    AVALON_CONTAINER_ID,
    AYON_CONTAINER_ID,
)
from ayon_core.pipeline.load import LoadError

log = logging.getLogger(__name__)

# The `customData` key the AYON container data is stored under
CONTAINER_KEY = "ayon"
CONTAINER_IDS = {AYON_CONTAINER_ID, AVALON_CONTAINER_ID}

# Base node type of Maya USD proxy shapes (incl. derived types)
PROXY_SHAPE_BASE_TYPE = "mayaUsdProxyShapeBase"

CONTAINER_TYPE_PRIM = "prim"
CONTAINER_TYPE_REFERENCE = "reference"


def is_maya_usd_plugin_loaded() -> bool:
    return bool(
        cmds.pluginInfo("mayaUsdPlugin", query=True, loaded=True)
    )


def is_usd_container(container: dict) -> bool:
    """Return whether the container dict is a container in a USD stage."""
    return container.get("usd_container_type") in {
        CONTAINER_TYPE_PRIM,
        CONTAINER_TYPE_REFERENCE,
    }


def is_proxy_shape(node: str) -> bool:
    return PROXY_SHAPE_BASE_TYPE in (
        cmds.nodeType(node, inherited=True) or []
    )


def get_proxy_stage(proxy: str) -> Optional[Usd.Stage]:
    """Return the USD stage of a Maya USD proxy shape node.

    Args:
        proxy (str): The `mayaUsdProxyShape` node name.

    Returns:
        Optional[Usd.Stage]: The stage, if it can be found.

    """
    import mayaUsd.ufe

    # Get the full DAG path, without a `|world` prefix. With a `|world`
    # prefix `getStage` fails to find the stage on new proxy shapes.
    path = cmds.ls(proxy, long=True)[0]
    stage = mayaUsd.ufe.getStage(path)
    if stage:
        return stage

    # Fall back to the stage cache, via the proxy's stage cache id
    from pxr import UsdUtils

    cache_id = cmds.getAttr(f"{path}.outStageCacheId")
    if cache_id < 0:
        return None
    stage = UsdUtils.StageCache.Get().Find(
        Usd.StageCache.Id.FromLongInt(cache_id)
    )
    return stage or None


def get_ufe_path(proxy: str, prim_path: Any) -> str:
    """Return the UFE path string for a prim path in a proxy's stage."""
    return f"{proxy},{prim_path}"


def iter_ufe_usd_selection() -> Iterator[str]:
    """Yield Maya USD Proxy Shape related UFE paths in selection.

    The returned paths are the Maya proxy shape node joined by a comma to
    the USD prim path, e.g. `|stage1|stageShape1,/root`.

    Yields:
        str: UFE path of a selected USD prim in a Maya USD proxy stage.

    """
    for path in cmds.ls(selection=True, ufeObjects=True, long=True) or []:
        if "," not in path:
            continue

        node, _prim_path = path.split(",", 1)
        if not cmds.objExists(node) or not is_proxy_shape(node):
            continue

        yield path


def create_stage_with_root_prim(prim_path: str = "/root") -> str:
    """Create a new Maya USD proxy shape with a stage holding a single prim.

    The prim is set as the default prim of the stage's root layer.

    Args:
        prim_path (str): The prim path of the root prim to create.

    Returns:
        str: The UFE path to the created prim.

    """
    import mayaUsd_createStageWithNewLayer
    from pxr import UsdGeom

    shape = mayaUsd_createStageWithNewLayer.createStageWithNewLayer()
    shape = cmds.ls(shape, long=True)[0]
    stage = get_proxy_stage(shape)
    if not stage:
        raise RuntimeError(f"Unable to get USD stage from: {shape}")

    prim = UsdGeom.Xform.Define(stage, prim_path).GetPrim()
    stage.SetDefaultPrim(prim)
    return get_ufe_path(shape, prim_path)


def get_load_target_ufe_path() -> str:
    """Return the UFE path of the USD prim a loader should load into.

    This is the selected USD prim, or a newly created stage's root prim if
    no USD prim is selected.

    Raises:
        LoadError: When more than one USD prim is selected.

    Returns:
        str: UFE path to the selected (or created) prim.

    """
    selection = list(iter_ufe_usd_selection())
    if len(selection) > 1:
        raise LoadError(
            "Select a single USD prim in a Maya USD stage to load into, or "
            "clear the selection to load into a new stage.\n"
            f"Selected USD prims: {', '.join(selection)}"
        )
    if selection:
        return selection[0]

    return create_stage_with_root_prim()


def ufe_path_to_prim(ufe_path: str) -> Usd.Prim:
    import mayaUsd.ufe

    prim = mayaUsd.ufe.ufePathToPrim(ufe_path)
    if not prim or not prim.IsValid():
        raise LoadError(f"Invalid USD prim: {ufe_path}")
    return prim


def remove_spec(spec):
    """Delete Sdf.PrimSpec or Sdf.PropertySpec

    Also see:
        https://forum.aousd.org/t/api-basics-for-designing-a-manage-edits-editor-for-usd/676/1  # noqa
        https://gist.github.com/BigRoy/4d2bf2eef6c6a83f4fda3c58db1489a5

    """
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
    else:
        raise TypeError(f"Unsupported spec type: {spec}")


def get_local_layers(stage: Usd.Stage) -> list[Sdf.Layer]:
    """Return the layers of the stage's local layer stack.

    These are the session layer, the root layer and their sublayers, from
    strongest to weakest.
    """
    return list(stage.GetLayerStack(includeSessionLayers=True))


def iter_prim_specs(layer: Sdf.Layer) -> Iterator[Sdf.PrimSpec]:
    """Yield all prim specs in a layer, including those inside variants.

    Prim specs of variants (e.g. `/root{variantSet=variant}`) are yielded as
    well, because they may author opinions like references too.
    """
    # Collect the paths with `Sdf.Layer.Traverse` because traversing in C++
    # is much faster than recursively iterating the specs' children in Python
    paths = []

    def _collect(path):
        if path.IsPrimPath() or path.IsPrimVariantSelectionPath():
            paths.append(path)

    layer.Traverse(Sdf.Path.absoluteRootPath, _collect)
    for path in paths:
        prim_spec = layer.GetPrimAtPath(path)
        if prim_spec:
            yield prim_spec


def _iter_reference_list_items(prim_spec: Sdf.PrimSpec):
    reference_list = prim_spec.referenceList
    for items in (
        reference_list.explicitItems,
        reference_list.addedItems,
        reference_list.prependedItems,
        reference_list.appendedItems,
    ):
        yield from items


def _get_container_data(custom_data) -> Optional[dict]:
    data = custom_data.get(CONTAINER_KEY)
    if not data or data.get("id") not in CONTAINER_IDS:
        return None
    return dict(data)


def get_container_data(
    loader: str,
    name: str,
    namespace: str,
    context: dict,
) -> dict:
    """Return the AYON container data to store in USD `customData`."""
    return {
        "schema": "openpype:container-2.0",
        "id": AYON_CONTAINER_ID,
        "name": str(name),
        "namespace": str(namespace),
        "loader": str(loader),
        "representation": context["representation"]["id"],
        "project_name": context["project"]["name"],
    }


def _make_container(
    data: dict,
    proxy: str,
    prim_path: Sdf.Path,
    container_type: str,
) -> dict:
    container = dict(data)
    container.update({
        # Transient data
        "objectName": get_ufe_path(proxy, prim_path),
        # Show the prim path in the Scene Inventory
        "namespace": str(prim_path),
        "proxy": proxy,
        "prim_path": str(prim_path),
        "usd_container_type": container_type,
    })
    return container


def iter_stage_containers(stage: Usd.Stage, proxy: str) -> Iterator[dict]:
    """Yield AYON containers authored in the stage's local layer stack.

    Args:
        stage (Usd.Stage): The USD stage.
        proxy (str): The Maya USD proxy shape the stage belongs to.

    Yields:
        dict: Container data.

    """
    processed_prim_paths = set()
    processed_identifiers = set()
    for layer in get_local_layers(stage):
        for prim_spec in iter_prim_specs(layer):
            prim_path = prim_spec.path.StripAllVariantSelections()

            # Prim containers, e.g. MayaReference prims
            data = _get_container_data(prim_spec.customData)
            if data and prim_path not in processed_prim_paths:
                # Only consider the strongest opinion
                processed_prim_paths.add(prim_path)
                yield _make_container(
                    data, proxy, prim_path, CONTAINER_TYPE_PRIM
                )

            # USD reference containers
            if not prim_spec.hasReferences:
                continue
            for reference in _iter_reference_list_items(prim_spec):
                data = _get_container_data(reference.customData)
                if not data:
                    continue
                # A reference may be listed in multiple list ops, so we
                # only yield it once.
                key = (prim_path, data.get("identifier"))
                if key in processed_identifiers:
                    continue
                processed_identifiers.add(key)
                yield _make_container(
                    data, proxy, prim_path, CONTAINER_TYPE_REFERENCE
                )


def iter_containers() -> Iterator[dict]:
    """Yield AYON containers in all Maya USD proxy shape stages."""
    if not is_maya_usd_plugin_loaded():
        return

    for proxy in cmds.ls(type=PROXY_SHAPE_BASE_TYPE, long=True):
        stage = get_proxy_stage(proxy)
        if not stage:
            log.warning(f"Unable to get USD stage from: {proxy}")
            continue

        yield from iter_stage_containers(stage, proxy)


def _get_container_stage(container: dict) -> Usd.Stage:
    proxy = container["proxy"]
    if not cmds.objExists(proxy):
        raise LoadError(f"Maya USD proxy shape not found: {proxy}")
    stage = get_proxy_stage(proxy)
    if not stage:
        raise LoadError(f"Unable to get USD stage from: {proxy}")
    return stage


def ensure_layer_editable(layer: Sdf.Layer):
    if not layer.permissionToEdit:
        raise LoadError(
            f"USD layer is not editable: {layer.identifier}"
        )


def iter_container_prim_specs(
    container: dict,
    composed_only: bool = True,
) -> Iterator[Sdf.PrimSpec]:
    """Yield prim specs of a container's prim in the stage's local layers.

    Args:
        container (dict): The USD container.
        composed_only (bool): When enabled, only yield the prim specs that
            contribute to the composed prim, from strongest to weakest
            opinion. When disabled, yield all prim specs for the prim path
            in the local layers, including those in unselected variants.
            This requires traversing the local layers so is much slower.

    Yields:
        Sdf.PrimSpec: The prim specs.

    """
    stage = _get_container_stage(container)
    prim_path = Sdf.Path(container["prim_path"])
    local_layers = get_local_layers(stage)

    if not composed_only:
        for layer in local_layers:
            for prim_spec in iter_prim_specs(layer):
                if prim_spec.path.StripAllVariantSelections() == prim_path:
                    yield prim_spec
        return

    prim = stage.GetPrimAtPath(prim_path)
    if not prim:
        return
    local_identifiers = {layer.identifier for layer in local_layers}
    for prim_spec in prim.GetPrimStack():
        if prim_spec.layer.identifier in local_identifiers:
            yield prim_spec


def find_reference(
    container: dict
) -> tuple[Sdf.PrimSpec, Sdf.Reference]:
    """Find the prim spec and reference of a reference container.

    Raises:
        LoadError: When the reference can not be found.

    Returns:
        tuple[Sdf.PrimSpec, Sdf.Reference]: The prim spec authoring the
            reference and the reference itself.

    """
    identifier = container["identifier"]
    # Search the composed prim first, because that is fast. If not found,
    # the reference may be authored in e.g. an unselected variant.
    for composed_only in (True, False):
        for prim_spec in iter_container_prim_specs(container, composed_only):
            if not prim_spec.hasReferences:
                continue
            for reference in _iter_reference_list_items(prim_spec):
                data = _get_container_data(reference.customData)
                if data and data.get("identifier") == identifier:
                    return prim_spec, reference

    raise LoadError(
        f"Unable to find USD reference for container: "
        f"{container['objectName']} (identifier: {identifier})"
    )


def add_reference_container(
    proxy: str,
    prim: Usd.Prim,
    path: str,
    data: dict,
) -> dict:
    """Add a USD reference to a prim with AYON container data.

    The reference is added in the current edit target of the stage.

    Args:
        proxy (str): The Maya USD proxy shape the prim's stage belongs to.
        prim (Usd.Prim): The prim to add the reference to.
        path (str): The asset path to reference.
        data (dict): The AYON container data.

    Returns:
        dict: The container.

    """
    data = dict(data)
    # Unique identifier to find this reference again, because multiple
    # references may be loaded onto the same prim.
    data["identifier"] = uuid.uuid4().hex
    reference = Sdf.Reference(
        assetPath=path,
        customData={CONTAINER_KEY: data}
    )
    if not prim.GetReferences().AddReference(reference):
        raise LoadError(f"Failed to add reference to: {prim.GetPath()}")

    return _make_container(
        data, proxy, prim.GetPath(), CONTAINER_TYPE_REFERENCE
    )


def update_reference_container(
    container: dict,
    path: Optional[str] = None,
    data: Optional[dict] = None,
):
    """Update the asset path and/or AYON data of a reference container."""
    prim_spec, reference = find_reference(container)
    ensure_layer_editable(prim_spec.layer)

    custom_data = dict(reference.customData)
    container_data = dict(custom_data[CONTAINER_KEY])
    if data:
        container_data.update(data)
    custom_data[CONTAINER_KEY] = container_data

    # `Sdf.Reference` is immutable, so we replace it with an updated copy
    new_reference = Sdf.Reference(
        assetPath=reference.assetPath if path is None else path,
        primPath=reference.primPath,
        layerOffset=reference.layerOffset,
        customData=custom_data,
    )
    prim_spec.referenceList.ReplaceItemEdits(reference, new_reference)


def remove_reference_container(container: dict):
    prim_spec, reference = find_reference(container)
    ensure_layer_editable(prim_spec.layer)
    prim_spec.referenceList.RemoveItemEdits(reference)


def imprint_prim_container(proxy: str, prim: Usd.Prim, data: dict) -> dict:
    """Store AYON container data in the prim's `customData`.

    The data is stored in the current edit target of the stage.

    Args:
        proxy (str): The Maya USD proxy shape the prim's stage belongs to.
        prim (Usd.Prim): The prim to containerise.
        data (dict): The AYON container data.

    Returns:
        dict: The container.

    """
    prim.SetCustomDataByKey(CONTAINER_KEY, data)
    return _make_container(data, proxy, prim.GetPath(), CONTAINER_TYPE_PRIM)


def update_prim_container(container: dict, data: dict):
    """Update the AYON data of a prim container.

    The data is updated in the prim specs that hold the container data.
    """
    # Search the composed prim first, because that is fast. If not found,
    # the prim may be authored in e.g. an unselected variant.
    for composed_only in (True, False):
        prim_specs = [
            prim_spec
            for prim_spec in iter_container_prim_specs(
                container, composed_only)
            if _get_container_data(prim_spec.customData)
        ]
        if prim_specs:
            break
    else:
        raise LoadError(
            "Unable to find USD prim container data for: "
            f"{container['objectName']}"
        )

    for prim_spec in prim_specs:
        ensure_layer_editable(prim_spec.layer)
        container_data = _get_container_data(prim_spec.customData)
        container_data.update(data)
        prim_spec.customData[CONTAINER_KEY] = container_data


def update_container_data(container: dict, data: dict):
    """Update AYON data of a USD prim or USD reference container."""
    container_type = container.get("usd_container_type")
    if container_type == CONTAINER_TYPE_REFERENCE:
        update_reference_container(container, data=data)
    elif container_type == CONTAINER_TYPE_PRIM:
        update_prim_container(container, data)
    else:
        raise ValueError(f"Not a USD container: {container}")
