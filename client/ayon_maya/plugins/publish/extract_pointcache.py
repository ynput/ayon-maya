"""Extract Alembic pointcache from Maya."""

from __future__ import annotations

import contextlib
import hashlib
import os
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import pyblish.api
from ayon_core.lib import (
    BoolDef,
    EnumDef,
    NumberDef,
    TextDef,
    UILabelDef,
    UISeparatorDef,
)
from ayon_core.pipeline import KnownPublishError
from ayon_core.pipeline.publish import OptionalPyblishPluginMixin
from ayon_core.pipeline.traits import (
    FileLocation,
    FrameRanged,
    Geometry,
    IntendedUse,
    MimeType,
    Persistent,
    Representation,
    Spatial,
    TraitBase,
)
from maya import cmds

from ayon_maya.api import plugin
from ayon_maya.api.alembic import extract_alembic
from ayon_maya.api.lib import (
    force_shader_assignments_to_faces,
    get_all_children,
    get_highest_in_hierarchy,
    iter_visible_nodes_in_range,
    maintained_selection,
    suspended_refresh,
)

if TYPE_CHECKING:
    from logging import Logger


def get_file_hash(file_path: Path) -> str:
    """Get file hash.

    Args:
            file_path (Path): File path.

    Returns:
        str: File hash.

    """
    hasher = hashlib.sha256()  # noqa: HL101
    with open(file_path, "rb") as file:
        while chunk := file.read(4096):
            hasher.update(chunk)
    return hasher.hexdigest()


def maya_units_to_meters_per_unit(unit: str) -> float:
    """Convert Maya units to meters per unit.

    Args:
        unit (str): Maya unit.

    Returns:
        float: Meters per unit.

    Raises:
        ValueError: If unit is unknown.

    """
    if unit == "mm":
        return 0.001
    if unit == "cm":
        return 0.01
    if unit == "m":
        return 1.0
    if unit == "km":
        return 1000.0
    msg = f"Unknown unit: {unit}"
    raise ValueError(msg)


class ExtractAlembic(plugin.MayaExtractorPlugin, OptionalPyblishPluginMixin):
    """Produce an alembic of just point positions and normals.

    With `farm` it will be skipped in local processing, but processed on farm.

    Positions and normals, uvs, creases are preserved, but nothing more,
    for plain and predictable point caches.

    Plugin can run locally or remotely (on a farm - if instance is marked with
    """
    label = "Extract Pointcache (Alembic)"
    hosts: ClassVar[list[str]] = ["maya"]
    families: ClassVar[list[str]] = [
        "pointcache",
        "model",
        "vrayproxy.alembic",
    ]
    targets: ClassVar[list[str]] = ["local", "remote"]
    optional = False
    # From settings
    attr: str = ""
    attrPrefix: str = ""
    bake_attributes: ClassVar[list[str]] = []
    bake_attribute_prefixes: ClassVar[list[str]] = []
    dataFormat: str = "ogawa"
    eulerFilter: bool = False
    melPerFrameCallback: str = ""
    melPostJobCallback: str = ""
    overrides: ClassVar[str] = []
    preRoll: bool = False
    preRollStartFrame: int = 0
    pythonPerFrameCallback: str = ""
    pythonPostJobCallback: str = ""
    renderableOnly: bool = False
    stripNamespaces: bool = True
    uvsOnly: bool = False
    uvWrite: bool = False
    userAttr: str = ""
    userAttrPrefix: str = ""
    verbose: bool = False
    visibleOnly: bool = False
    wholeFrameGeo: bool = False
    worldSpace: bool = True
    writeColorSets: bool = False
    writeCreases: bool = False
    writeFaceSets: bool = False
    writeNormals: bool = True
    writeUVSets = False
    writeVisibility = False

    log: Logger

    def process(self, instance: pyblish.api.Instance) -> None:
        """Process the plugin."""
        if not self.is_active(instance.data):
            return

        if instance.data.get("farm"):
            self.log.debug("Should be processed on farm, skipping.")
            return

        nodes, roots = self.get_members_and_roots(instance)

        # Collect the start and end including handles
        start = float(instance.data.get("frameStartHandle", 1))
        end = float(instance.data.get("frameEndHandle", 1))

        attribute_values = self.get_attr_values_from_data(instance.data)

        attrs = [
            attr.strip()
            for attr in attribute_values.get("attr", "").split(";")
            if attr.strip()
        ]
        attrs += instance.data.get("userDefinedAttributes", [])
        attrs += self.bake_attributes
        attrs += ["cbId"]

        attr_prefixes = [
            attr.strip()
            for attr in attribute_values.get("attrPrefix", "").split(";")
            if attr.strip()
        ]
        attr_prefixes += self.bake_attribute_prefixes

        user_attrs = [
            attr.strip()
            for attr in attribute_values.get("userAttr", "").split(";")
            if attr.strip()
        ]

        user_attr_prefixes = [
            attr.strip()
            for attr in attribute_values.get("userAttrPrefix", "").split(";")
            if attr.strip()
        ]

        self.log.debug("Extracting pointcache..")
        dirname = self.staging_dir(instance)

        parent_dir = self.staging_dir(instance)
        filename = "{name}.abc".format(**instance.data)
        path = os.path.join(parent_dir, filename)

        root = None
        if not instance.data.get("includeParentHierarchy", True):
            # Set the root nodes if we don't want to include parents
            # The roots are to be considered the ones that are the actual
            # direct members of the set
            # We ignore members that are children of other members to avoid
            # the parenting / ancestor relationship error on export and assume
            # the user intended to export starting at the top of the two.
            root = get_highest_in_hierarchy(roots)

        kwargs = {
            "file": path,
            "attr": attrs,
            "attrPrefix": attr_prefixes,
            "userAttr": user_attrs,
            "userAttrPrefix": user_attr_prefixes,
            "dataFormat": attribute_values.get("dataFormat", self.dataFormat),
            "endFrame": end,
            "eulerFilter": attribute_values.get(
                "eulerFilter", self.eulerFilter
            ),
            "preRoll": attribute_values.get("preRoll", self.preRoll),
            "preRollStartFrame": attribute_values.get(
                "preRollStartFrame", self.preRollStartFrame
            ),
            "renderableOnly": attribute_values.get(
                "renderableOnly", self.renderableOnly
            ),
            "root": root,
            "selection": True,
            "startFrame": start,
            "step": instance.data.get("creator_attributes", {}).get(
                "step", 1.0
            ),
            "stripNamespaces": attribute_values.get(
                "stripNamespaces", self.stripNamespaces
            ),
            "uvWrite": attribute_values.get("uvWrite", self.uvWrite),
            "verbose": attribute_values.get("verbose", self.verbose),
            "wholeFrameGeo": attribute_values.get(
                "wholeFrameGeo", self.wholeFrameGeo
            ),
            "worldSpace": attribute_values.get("worldSpace", self.worldSpace),
            "writeColorSets": attribute_values.get(
                "writeColorSets", self.writeColorSets
            ),
            "writeCreases": attribute_values.get(
                "writeCreases", self.writeCreases
            ),
            "writeFaceSets": attribute_values.get(
                "writeFaceSets", self.writeFaceSets
            ),
            "writeUVSets": attribute_values.get(
                "writeUVSets", self.writeUVSets
            ),
            "writeVisibility": attribute_values.get(
                "writeVisibility", self.writeVisibility
            ),
            "uvsOnly": attribute_values.get("uvsOnly", self.uvsOnly),
            "melPerFrameCallback": attribute_values.get(
                "melPerFrameCallback", self.melPerFrameCallback
            ),
            "melPostJobCallback": attribute_values.get(
                "melPostJobCallback", self.melPostJobCallback
            ),
            "pythonPerFrameCallback": attribute_values.get(
                "pythonPerFrameCallback", self.pythonPostJobCallback
            ),
            "pythonPostJobCallback": attribute_values.get(
                "pythonPostJobCallback", self.pythonPostJobCallback
            ),
            # Note that this converts `writeNormals` to `noNormals` for the
            # `AbcExport` equivalent in `extract_alembic`
            "noNormals": not attribute_values.get(
                "writeNormals", self.writeNormals
            ),
        }

        if attribute_values.get("visibleOnly", False):
            # If we only want to include nodes that are visible in the frame
            # range then we need to do our own check. Alembic's `visibleOnly`
            # flag does not filter out those that are only hidden on some
            # frames as it counts "animated" or "connected" visibilities as
            # if it's always visible.
            nodes = list(
                iter_visible_nodes_in_range(nodes, start=start, end=end)
            )

        # Our logic is that `preroll` means:
        # - True: include a preroll from `preRollStartFrame` to the start
        #  frame that is not included in the exported file. Just 'roll up'
        #  the export from there.
        # - False: do not roll up from `preRollStartFrame`.
        # `AbcExport` however approaches this very differently.
        # A call to `AbcExport` allows to export multiple "jobs" of frame
        # ranges in one go. Using `-preroll` argument there means: this one
        # job in the full list of jobs SKIP writing these frames into the
        # Alembic. In short, marking that job as just preroll.
        # Then additionally, separate from `-preroll` the `AbcExport` command
        # allows to supply `preRollStartFrame` which, when not None, means
        # always RUN UP from that start frame. Since our `preRollStartFrame`
        # is always an integer attribute we will convert the attributes so
        # they behave like how we intended them initially
        if kwargs["preRoll"]:
            # Never mark `preRoll` as True because it would basically end up
            # writing no samples at all. We just use this to leave
            # `preRollStartFrame` as a number value.
            kwargs["preRoll"] = False
        else:
            kwargs["preRollStartFrame"] = None

        suspend = not instance.data.get("refresh", False)
        with contextlib.ExitStack() as stack:
            stack.enter_context(suspended_refresh(suspend=suspend))
            stack.enter_context(maintained_selection())
            if instance.data.get("writeFaceSets", True):
                meshes = cmds.ls(nodes, type="mesh", long=True)
                stack.enter_context(force_shader_assignments_to_faces(meshes))
            cmds.select(nodes, noExpand=True)
            self.log.debug(
                "Running `extract_alembic` with the keyword arguments: %s",
                kwargs,
            )
            extract_alembic(**kwargs)

        traits: list[TraitBase] = [
            Geometry(),
            MimeType(mime_type="application/abc"),
            Persistent(),
            Spatial(
                up_axis=cmds.upAxis(q=True, axis=True),
                meters_per_unit=maya_units_to_meters_per_unit(
                    instance.context.data["linearUnits"]),
                handedness="right",
            ),
        ]

        if instance.data.get("frameStart"):
            traits.append(
                FrameRanged(
                    frame_start=instance.data["frameStart"],
                    frame_end=instance.data["frameEnd"],
                    frames_per_second=instance.context.data["fps"],
                )
            )

        representation = Representation(
            name="alembic",
            traits=[
                FileLocation(
                    file_path=Path(path),
                    file_size=os.path.getsize(path),
                    file_hash=get_file_hash(Path(path))
                ),
                *traits],
        )

        if not instance.data.get("representations_with_traits"):
            instance.data["representations_with_traits"] = []

        instance.data["representations_with_traits"].append(representation)

        if not instance.data.get("stagingDir_persistent", False):
            instance.context.data["cleanupFullPaths"].append(path)

        self.log.debug("Extracted %s to %s", instance, dirname)

        # Extract proxy.
        if not instance.data.get("proxy"):
            self.log.debug("No proxy nodes found. Skipping proxy extraction.")
            return

        path = path.replace(".abc", "_proxy.abc")
        kwargs["file"] = path
        if not instance.data.get("includeParentHierarchy", True):
            # Set the root nodes if we don't want to include parents
            # The roots are to be considered the ones that are the actual
            # direct members of the set
            kwargs["root"] = instance.data["proxyRoots"]

        with suspended_refresh(suspend=suspend), maintained_selection():
            cmds.select(instance.data["proxy"])
            extract_alembic(**kwargs)

        representation = Representation(
            name="proxy",
            traits=[
                FileLocation(
                    file_path=Path(path),
                    file_size=os.path.getsize(path),
                    file_hash=get_file_hash(Path(path))
                ),
                IntendedUse(use="proxy"),
                *traits],
        )

        instance.data["representations_with_traits"].append(representation)

    @staticmethod
    def get_members_and_roots(
            instance: pyblish.api.Instance) -> tuple[list[str], list[str]]:
        """Get members and roots from the instance.

        Returns:
            tuple[list[str], list[str]]: Members and roots.

        """
        return instance[:], instance.data.get("setMembers")

    @classmethod
    def get_attribute_defs(cls) -> list:
        """Get attribute definitions.

        Returns:
            list: Attribute definitions.

        """
        defs = super().get_attribute_defs()
        if not cls.overrides:
            return defs

        override_defs = OrderedDict(
            {
                "eulerFilter": BoolDef(
                    "eulerFilter",
                    label="Euler Filter",
                    default=cls.eulerFilter,
                    tooltip="Apply Euler filter while sampling rotations.",
                ),
                "renderableOnly": BoolDef(
                    "renderableOnly",
                    label="Renderable Only",
                    default=cls.renderableOnly,
                    tooltip="Only export renderable visible shapes.",
                ),
                "stripNamespaces": BoolDef(
                    "stripNamespaces",
                    label="Strip Namespaces",
                    default=cls.stripNamespaces,
                    tooltip=(
                        "Namespaces will be stripped off of the node before "
                        "being written to Alembic."
                    ),
                ),
                "uvsOnly": BoolDef(
                    "uvsOnly",
                    label="UVs Only",
                    default=cls.uvsOnly,
                    tooltip=(
                        "If this flag is present, only uv data for PolyMesh "
                        "and SubD shapes will be written to the Alembic file."
                    ),
                ),
                "uvWrite": BoolDef(
                    "uvWrite",
                    label="UV Write",
                    default=cls.uvWrite,
                    tooltip=(
                        "Uv data for PolyMesh and SubD shapes will be "
                        "written to the Alembic file."
                    ),
                ),
                "verbose": BoolDef(
                    "verbose",
                    label="Verbose",
                    default=cls.verbose,
                    tooltip=(
                        "Prints the current frame that is being "
                        "evaluated."
                    ),
                ),
                "visibleOnly": BoolDef(
                    "visibleOnly",
                    label="Visible Only",
                    default=cls.visibleOnly,
                    tooltip=(
                        "Only export dag objects visible during "
                        "frame range."
                    ),
                ),
                "wholeFrameGeo": BoolDef(
                    "wholeFrameGeo",
                    label="Whole Frame Geo",
                    default=cls.wholeFrameGeo,
                    tooltip=(
                        "Data for geometry will only be written out on whole "
                        "frames."
                    ),
                ),
                "worldSpace": BoolDef(
                    "worldSpace",
                    label="World Space",
                    default=cls.worldSpace,
                    tooltip="Any root nodes will be stored in world space.",
                ),
                "writeColorSets": BoolDef(
                    "writeColorSets",
                    label="Write Color Sets",
                    default=cls.writeColorSets,
                    tooltip="Write vertex colors with the geometry.",
                ),
                "writeCreases": BoolDef(
                    "writeCreases",
                    label="Write Creases",
                    default=cls.writeCreases,
                    tooltip="Write the geometry's edge and vertex crease "
                    "information.",
                ),
                "writeFaceSets": BoolDef(
                    "writeFaceSets",
                    label="Write Face Sets",
                    default=cls.writeFaceSets,
                    tooltip="Write face sets with the geometry.",
                ),
                "writeNormals": BoolDef(
                    "writeNormals",
                    label="Write Normals",
                    default=cls.writeNormals,
                    tooltip="Write normals with the deforming geometry.",
                ),
                "writeUVSets": BoolDef(
                    "writeUVSets",
                    label="Write UV Sets",
                    default=cls.writeUVSets,
                    tooltip=(
                        "Write all uv sets on MFnMeshes as vector 2 indexed "
                        "geometry parameters with face varying scope."
                    ),
                ),
                "writeVisibility": BoolDef(
                    "writeVisibility",
                    label="Write Visibility",
                    default=cls.writeVisibility,
                    tooltip=(
                        "Visibility state will be stored in the Alembic "
                        "file. Otherwise everything written out is treated "
                        "as visible."
                    ),
                ),
                "preRoll": BoolDef(
                    "preRoll",
                    label="Pre Roll",
                    default=cls.preRoll,
                    tooltip="This frame range will not be sampled.",
                ),
                "preRollStartFrame": NumberDef(
                    "preRollStartFrame",
                    label="Pre Roll Start Frame",
                    tooltip=(
                        "The frame to start scene evaluation at. This is used"
                        " to set the starting frame for time dependent "
                        "translations and can be used to evaluate run-up that"
                        " isn't actually translated."
                    ),
                    default=cls.preRollStartFrame,
                ),
                "dataFormat": EnumDef(
                    "dataFormat",
                    label="Data Format",
                    items=["ogawa", "HDF"],
                    default=cls.dataFormat,
                    tooltip="The data format to use to write the file.",
                ),
                "attr": TextDef(
                    "attr",
                    label="Custom Attributes",
                    placeholder="attr1; attr2; ...",
                    default=cls.attr,
                    tooltip=(
                        "Attributes matching by name will be included in the "
                        "Alembic export. Attributes should be separated by "
                        "semi-colon `;`"
                    ),
                ),
                "attrPrefix": TextDef(
                    "attrPrefix",
                    label="Custom Attributes Prefix",
                    placeholder="prefix1; prefix2; ...",
                    default=cls.attrPrefix,
                    tooltip=(
                        "Attributes starting with these prefixes will be "
                        "included in the Alembic export. Attributes should "
                        "be separated by semi-colon `;`"
                    ),
                ),
                "userAttr": TextDef(
                    "userAttr",
                    label="User Attr",
                    placeholder="attr1; attr2; ...",
                    default=cls.userAttr,
                    tooltip=(
                        "Attributes matching by name will be included in the "
                        "Alembic export. Attributes should be separated by "
                        "semi-colon `;`"
                    ),
                ),
                "userAttrPrefix": TextDef(
                    "userAttrPrefix",
                    label="User Attr Prefix",
                    placeholder="prefix1; prefix2; ...",
                    default=cls.userAttrPrefix,
                    tooltip=(
                        "Attributes starting with these prefixes will be "
                        "included in the Alembic export. Attributes should "
                        "be separated by semi-colon `;`"
                    ),
                ),
                "melPerFrameCallback": TextDef(
                    "melPerFrameCallback",
                    label="Mel Per Frame Callback",
                    default=cls.melPerFrameCallback,
                    tooltip=(
                        "When each frame (and the static frame) is evaluated "
                        "the string specified is evaluated as a Mel command."
                    ),
                ),
                "melPostJobCallback": TextDef(
                    "melPostJobCallback",
                    label="Mel Post Job Callback",
                    default=cls.melPostJobCallback,
                    tooltip=(
                        "When the translation has finished the string "
                        "specified is evaluated as a Mel command."
                    ),
                ),
                "pythonPerFrameCallback": TextDef(
                    "pythonPerFrameCallback",
                    label="Python Per Frame Callback",
                    default=cls.pythonPerFrameCallback,
                    tooltip=(
                        "When each frame (and the static frame) is "
                        "evaluated the string specified is evaluated as "
                        "a python command."
                    ),
                ),
                "pythonPostJobCallback": TextDef(
                    "pythonPostJobCallback",
                    label="Python Post Frame Callback",
                    default=cls.pythonPostJobCallback,
                    tooltip=(
                        "When the translation has finished the "
                        "string specified is evaluated as a python command."
                    ),
                ),
            }
        )

        defs.extend(
            [
                UISeparatorDef("sep_alembic_options"),
                UILabelDef("Alembic Options"),
            ]
        )

        # The Arguments that can be modified by the Publisher
        overrides = set(cls.overrides)
        for key, value in override_defs.items():
            if key not in overrides:
                continue

            defs.append(value)

        defs.append(UISeparatorDef("sep_alembic_options_end"))

        return defs


class ExtractAnimation(ExtractAlembic, OptionalPyblishPluginMixin):
    """Produce an alembic of just point positions and normals."""
    label = "Extract Animation (Alembic)"
    families: ClassVar[list[str]] = ["animation"]
    optional = False

    @staticmethod
    def get_members_and_roots(instance: pyblish.api.Instance) -> tuple:
        """Get members and roots from the instance.

        Args:
            instance (pyblish.api.Instance): Instance.

        Returns:
            tuple: Members and roots.

        Raises:
            KnownPublishError: If couldn't find exactly one out_SET.

        """
        # Collect the out set nodes
        out_sets = [node for node in instance if node.endswith("out_SET")]
        if len(out_sets) != 1:
            msg = f"Couldn't find exactly one out_SET: {out_sets}"
            raise KnownPublishError(msg)
        out_set = out_sets[0]
        roots = cmds.sets(out_set, query=True) or []

        # Include all descendants
        nodes = roots.copy()
        nodes.extend(
            get_all_children(roots, ignore_intermediate_objects=True))

        return nodes, roots
