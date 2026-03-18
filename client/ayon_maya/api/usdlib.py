import logging

from ayon_core.pipeline.constants import AVALON_CONTAINER_ID
from maya import cmds
from pxr import Gf, Sdf, UsdGeom

log = logging.getLogger(__name__)


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


def iter_ufe_usd_selection():
    """Yield Maya USD Proxy Shape related UFE paths in selection.

    The returned path are the Maya node name joined by a command to the
    USD prim path.

    Yields:
        str: Path to UFE path in USD stage in selection.

    """
    for path in cmds.ls(selection=True, ufeObjects=True, long=True,
                        absoluteName=True):
        if "," not in path:
            continue

        node, ufe_path = path.split(",", 1)
        if cmds.nodeType(node) != "mayaUsdProxyShape":
            continue

        yield path


def containerise_prim(prim,
                      name,
                      namespace,
                      context,
                      loader):
    """Containerise a USD prim.

    Arguments:
        prim (pxr.Usd.Prim): The prim to containerise.
        name (str): Name to containerize.
        namespace (str): Namespace to containerize.
        context (dict): Load context (incl. representation).
        name (str): Name to containerize.
        loader (str): Loader name.

    """
    for key, value in {
        "ayon:schema": "openpype:container-2.0",
        "ayon:id": AVALON_CONTAINER_ID,
        "ayon:name": name,
        "ayon:namespace": namespace,
        "ayon:loader": loader,
        "ayon:representation": context["representation"]["id"],
    }.items():
        prim.SetCustomDataByKey(key, str(value))


def save_and_zero_layout_transform(stage, asset_prim_path):
    """Save layout transform to custom data and zero it on the session layer.

    When an animator activates "Edit as Maya Data" on a rigged asset,
    the rig inherits the layout transform from the parent Xform. This
    can break the rig or cause incorrect animation.

    This function:
    1. Reads the current local transform from the asset prim
    2. Stores it as ``ayon:layoutTransform`` custom data (for reference)
    3. Zeros the transform on the **session layer** so the rig starts
       at the origin — the session layer opinion is temporary and does
       not modify published data.

    The animator can then animate freely. On cache export, using
    ``worldspace=True`` + ``resetXformStack`` ensures the final
    positions are correct regardless of the zeroed transform.

    Args:
        stage (Usd.Stage): The USD stage containing the asset.
        asset_prim_path (str): Sdf path to the asset prim that carries
            the layout transform (e.g. "/shot/char/cone_character").

    Returns:
        bool: True if the transform was zeroed, False otherwise.
    """
    from pxr import Usd

    prim = stage.GetPrimAtPath(asset_prim_path)
    if not prim or not prim.IsValid():
        log.debug(
            "save_and_zero_layout_transform: prim not found at %s",
            asset_prim_path
        )
        return False

    xformable = UsdGeom.Xformable(prim)
    if not xformable:
        log.debug(
            "save_and_zero_layout_transform: prim is not Xformable: %s",
            asset_prim_path
        )
        return False

    # Read the current local transform
    local_xform = xformable.GetLocalTransformation()
    if local_xform == Gf.Matrix4d(1.0):
        log.debug(
            "save_and_zero_layout_transform: transform is already identity "
            "for %s, nothing to zero",
            asset_prim_path
        )
        return False

    # Store the original transform as custom data for reference
    # Convert matrix to a flat list of 16 floats for storage
    flat_values = []
    for row in range(4):
        for col in range(4):
            flat_values.append(local_xform[row][col])

    prim.SetCustomDataByKey(
        "ayon:layoutTransform",
        flat_values
    )
    log.info(
        "Saved layout transform for %s: %s",
        asset_prim_path, flat_values
    )

    # Zero the transform on the session layer (temporary, non-destructive)
    session_layer = stage.GetSessionLayer()
    original_edit_target = stage.GetEditTarget()
    try:
        stage.SetEditTarget(Usd.EditTarget(session_layer))
        xformable.ClearXformOpOrder()

        # Set identity transform via a single matrix op
        xform_op = xformable.MakeMatrixXform()
        xform_op.Set(Gf.Matrix4d(1.0))

        log.info(
            "Zeroed layout transform on session layer for %s",
            asset_prim_path
        )
    finally:
        stage.SetEditTarget(original_edit_target)

    return True


def restore_layout_transform(stage, asset_prim_path):
    """Restore a previously zeroed layout transform from the session layer.

    Removes the session layer override so the original layout transform
    from the composition takes effect again.

    Args:
        stage (Usd.Stage): The USD stage containing the asset.
        asset_prim_path (str): Sdf path to the asset prim.

    Returns:
        bool: True if restored, False otherwise.
    """
    session_layer = stage.GetSessionLayer()
    prim_spec = session_layer.GetPrimAtPath(asset_prim_path)
    if not prim_spec:
        return False

    # Clear all xform properties from the session layer
    props_to_remove = [
        name for name in prim_spec.properties
        if name.startswith("xformOp") or name == "xformOpOrder"
    ]
    for prop_name in props_to_remove:
        del prim_spec.properties[prop_name]

    log.info(
        "Restored layout transform (cleared session overrides) for %s",
        asset_prim_path
    )
    return True
