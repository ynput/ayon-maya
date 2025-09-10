import contextlib
import difflib

import qargparse
from ayon_core.settings import get_project_settings
from ayon_core.pipeline import get_current_project_name
from ayon_core.pipeline.load import get_representation_context
from ayon_maya.api import plugin
from ayon_maya.api.lib import (
    RigSetsNotExistError,
    create_rig_animation_instance,
    get_container_members,
    is_animation_instance,
    maintained_selection,
    parent_nodes,
)
from maya import cmds


@contextlib.contextmanager
def preserve_time_units():
    """Preserve current frame, frame range and fps"""
    frame = cmds.currentTime(query=True)
    fps = cmds.currentUnit(query=True, time=True)
    start = cmds.playbackOptions(query=True, minTime=True)
    end = cmds.playbackOptions(query=True, maxTime=True)
    anim_start = cmds.playbackOptions(query=True, animationStartTime=True)
    anim_end = cmds.playbackOptions(query=True, animationEndTime=True)
    try:
        yield
    finally:
        cmds.currentUnit(time=fps, updateAnimation=False)
        cmds.currentTime(frame)
        cmds.playbackOptions(minTime=start,
                             maxTime=end,
                             animationStartTime=anim_start,
                             animationEndTime=anim_end)


@contextlib.contextmanager
def preserve_modelpanel_cameras(container, log=None):
    """Preserve camera members of container in the modelPanels.

    This is used to ensure a camera remains in the modelPanels after updating
    to a new version.

    """

    # Get the modelPanels that used the old camera
    members = get_container_members(container)
    old_cameras = set(cmds.ls(members, type="camera", long=True))
    if not old_cameras:
        # No need to manage anything
        yield
        return

    panel_cameras = {}
    for panel in cmds.getPanel(type="modelPanel"):
        cam = cmds.ls(cmds.modelPanel(panel, query=True, camera=True),
                      long=True)[0]

        # Often but not always maya returns the transform from the
        # modelPanel as opposed to the camera shape, so we convert it
        # to explicitly be the camera shape
        if cmds.nodeType(cam) != "camera":
            cam = cmds.listRelatives(cam,
                                     children=True,
                                     fullPath=True,
                                     type="camera")[0]
        if cam in old_cameras:
            panel_cameras[panel] = cam

    if not panel_cameras:
        # No need to manage anything
        yield
        return

    try:
        yield
    finally:
        new_members = get_container_members(container)
        new_cameras = set(cmds.ls(new_members, type="camera", long=True))
        if not new_cameras:
            return

        for panel, cam_name in panel_cameras.items():
            new_camera = None
            if cam_name in new_cameras:
                new_camera = cam_name
            elif len(new_cameras) == 1:
                new_camera = next(iter(new_cameras))
            else:
                # Multiple cameras in the updated container but not an exact
                # match detected by name. Find the closest match
                matches = difflib.get_close_matches(word=cam_name,
                                                    possibilities=new_cameras,
                                                    n=1)
                if matches:
                    new_camera = matches[0]  # best match
                    if log:
                        log.info("Camera in '{}' restored with "
                                 "closest match camera: {} (before: {})"
                                 .format(panel, new_camera, cam_name))

            if not new_camera:
                # Unable to find the camera to re-apply in the modelpanel
                continue

            cmds.modelPanel(panel, edit=True, camera=new_camera)


class ReferenceLoader(plugin.ReferenceLoader):
    """Reference file"""

    product_types = {
        "model",
        "pointcache",
        "proxyAbc",
        "animation",
        "mayaAscii",
        "mayaScene",
        "setdress",
        "layout",
        "camera",
        "rig",
        "camerarig",
        "staticMesh",
        "skeletalMesh",
        "mvLook",
        "matchmove",
    }

    representations = {"ma", "abc", "fbx", "mb"}

    label = "Reference"
    order = -10
    icon = "code-fork"
    color = "orange"

    def process_reference(self, context, name, namespace, options):
        import maya.cmds as cmds
        product_type = context["product"]["productType"]
        project_name = context["project"]["name"]
        # True by default to keep legacy behaviours
        attach_to_root = options.get("attach_to_root", True)
        group_name = options["group_name"]

        # no group shall be created
        if not attach_to_root:
            group_name = namespace

        kwargs = {}
        if "file_options" in options:
            kwargs["options"] = options["file_options"]
        if "file_type" in options:
            kwargs["type"] = options["file_type"]

        path = self.filepath_from_context(context)
        with maintained_selection():
            cmds.loadPlugin("AbcImport.mll", quiet=True)

            file_url = self.prepare_root_value(path, project_name)
            nodes = cmds.file(file_url,
                              namespace=namespace,
                              sharedReferenceFile=False,
                              reference=True,
                              returnNewNodes=True,
                              groupReference=attach_to_root,
                              groupName=group_name,
                              **kwargs)

            shapes = cmds.ls(nodes, shapes=True, long=True)

            new_nodes = (list(set(nodes) - set(shapes)))

            # if there are cameras, try to lock their transforms
            self._lock_camera_transforms(new_nodes)

            current_namespace = cmds.namespaceInfo(currentNamespace=True)

            if current_namespace != ":":
                group_name = current_namespace + ":" + group_name

            self[:] = new_nodes

            if attach_to_root:
                group_name = "|" + group_name
                roots = cmds.listRelatives(group_name,
                                           children=True,
                                           fullPath=True) or []

                if product_type not in {
                    "layout", "setdress", "mayaAscii", "mayaScene"
                }:
                    # QUESTION Why do we need to exclude these families?
                    with parent_nodes(roots, parent=None):
                        cmds.xform(group_name, zeroTransformPivots=True)

                settings = get_project_settings(project_name)
                color = plugin.get_load_color_for_product_type(
                    product_type, settings
                )
                if color is not None:
                    red, green, blue = color
                    cmds.setAttr("{}.useOutlinerColor".format(group_name), 1)
                    cmds.setAttr(
                        "{}.outlinerColor".format(group_name),
                        red,
                        green,
                        blue
                    )

                display_handle = settings['maya']['load'].get(
                    'reference_loader', {}
                ).get('display_handle', True)
                if display_handle:
                    self._set_display_handle(group_name)

            if product_type == "rig":
                options["lock_instance"] = (
                    settings
                    ["maya"]
                    ["load"]
                    ["reference_loader"]
                    ["lock_animation_instance_on_load"]
                )
                self._post_process_rig(namespace, context, options)
            else:
                if "translate" in options:
                    if not attach_to_root and new_nodes:
                        root_nodes = cmds.ls(new_nodes, assemblies=True,
                                             long=True)
                        # we assume only a single root is ever loaded
                        group_name = root_nodes[0]
                    cmds.setAttr("{}.translate".format(group_name),
                                 *options["translate"])
            return new_nodes

    def switch(self, container, context):
        self.update(container, context)

    def update(self, container, context):
        with preserve_modelpanel_cameras(container, log=self.log):
            super(ReferenceLoader, self).update(container, context)

        # We also want to lock camera transforms on any new cameras in the
        # reference or for a camera which might have changed names.
        members = get_container_members(container)
        self._lock_camera_transforms(members)

    def remove(self, container):
        representation_id: str = container["representation"]
        project_name: str = container.get(
            "project_name", get_current_project_name()
        )
        product_type = None
        if representation_id:
            context: dict = get_representation_context(
                project_name, representation_id
            )
            product_type: str = context["product"]["productType"]

        if product_type == "rig":
            # Special handling needed for rig containers
            self._remove_rig(container)
            return

        super().remove(container)

    def _remove_rig(self, container):
        """Remove linked animation instance no matter if it
        is locked or not.

        Args:
            container (dict): The container to remove.
        """
        members = get_container_members(container)
        object_sets = set()
        for member in members:
            object_sets.update(
                cmds.listSets(object=member,
                            extendToShape=False,
                            type=2) or []
            )

        super().remove(container)
        # After the deletion, we check which object sets are still existing
        # because maya may auto-delete empty object sets if they are not locked
        # This way we can clean up remaining animation instances that were
        # locked
        object_sets = cmds.ls(object_sets, type="objectSet")
        for object_set in object_sets:
            # Only consider empty object sets
            members = cmds.sets(object_set, query=True)
            if members:
                continue

            # Only consider locked object sets
            locked = cmds.lockNode(object_set, query=True)
            if not locked:
                continue

            # Ignore referenced object sets
            if cmds.referenceQuery(isNodeReferenced=object_set):
                continue

            # Then only here confirm whether this is an animation instance, if so
            # then we will want to auto-remove the instance
            if is_animation_instance(object_set):
                cmds.lockNode(object_set, lock=False)
                cmds.delete(object_set)

    def _post_process_rig(self, namespace, context, options):

        nodes = self[:]
        try:
            create_rig_animation_instance(
                nodes, context, namespace, options=options, log=self.log,
            )
        except RigSetsNotExistError as exc:
            self.log.warning(
                "Missing rig sets for animation instance creation: %s", exc)

    def _lock_camera_transforms(self, nodes):
        cameras = cmds.ls(nodes, type="camera")
        if not cameras:
            return

        # Check the Maya version, lockTransform has been introduced since
        # Maya 2016.5 Ext 2
        version = int(cmds.about(version=True))
        if version >= 2016:
            for camera in cameras:
                cmds.camera(camera, edit=True, lockTransform=True)
        else:
            self.log.warning("This version of Maya does not support locking of"
                             " transforms of cameras.")

    def _set_display_handle(self, group_name: str):
        """Enable display handle and move select handle to object center"""
        cmds.setAttr(f"{group_name}.displayHandle", True)
        # get bounding box
        # Bugfix: We force a refresh here because there is a reproducable case
        # with Advanced Skeleton rig where the call to `exactWorldBoundingBox`
        # directly after the reference without it breaks the behavior of the
        # rigs making it appear as if parts of the mesh are static.
        # TODO: Preferably we have a better fix than requiring refresh on loads
        cmds.refresh()
        bbox = cmds.exactWorldBoundingBox(group_name)
        # get pivot position on world space
        pivot = cmds.xform(group_name, q=True, sp=True, ws=True)
        # center of bounding box
        cx = (bbox[0] + bbox[3]) / 2
        cy = (bbox[1] + bbox[4]) / 2
        cz = (bbox[2] + bbox[5]) / 2
        # add pivot position to calculate offset
        cx += pivot[0]
        cy += pivot[1]
        cz += pivot[2]
        # set selection handle offset to center of bounding box
        cmds.setAttr(f"{group_name}.selectHandleX", cx)
        cmds.setAttr(f"{group_name}.selectHandleY", cy)
        cmds.setAttr(f"{group_name}.selectHandleZ", cz)


class MayaUSDReferenceLoader(ReferenceLoader):
    """Reference USD file to native Maya nodes using MayaUSDImport reference"""

    label = "Reference Maya USD"
    product_types = {"usd"}
    representations = {"usd"}
    extensions = {"usd", "usda", "usdc"}

    options = ReferenceLoader.options + [
        qargparse.Boolean(
            "readAnimData",
            label="Load anim data",
            default=True,
            help="Load animation data from USD file"
        ),
        qargparse.Boolean(
            "useAsAnimationCache",
            label="Use as animation cache",
            default=True,
            help=(
                "Imports geometry prims with time-sampled point data using a "
                "point-based deformer that references the imported "
                "USD file.\n"
                "This provides better import and playback performance when "
                "importing time-sampled geometry from USD, and should "
                "reduce the weight of the resulting Maya scene."
            )
        ),
        qargparse.Boolean(
            "importInstances",
            label="Import instances",
            default=True,
            help=(
                "Import USD instanced geometries as Maya instanced shapes. "
                "Will flatten the scene otherwise."
            )
        ),
        qargparse.String(
            "primPath",
            label="Prim Path",
            default="/",
            help=(
                "Name of the USD scope where traversing will begin.\n"
                "The prim at the specified primPath (including the prim) will "
                "be imported.\n"
                "Specifying the pseudo-root (/) means you want "
                "to import everything in the file.\n"
                "If the passed prim path is empty, it will first try to "
                "import the defaultPrim for the rootLayer if it exists.\n"
                "Otherwise, it will behave as if the pseudo-root was passed "
                "in."
            )
        )
    ]

    file_type = "USD Import"

    def process_reference(self, context, name, namespace, options):
        cmds.loadPlugin("mayaUsdPlugin", quiet=True)

        def bool_option(key, default):
            # Shorthand for getting optional boolean file option from options
            value = int(bool(options.get(key, default)))
            return "{}={}".format(key, value)

        def string_option(key, default):
            # Shorthand for getting optional string file option from options
            value = str(options.get(key, default))
            return "{}={}".format(key, value)

        options["file_options"] = ";".join([
            string_option("primPath", default="/"),
            bool_option("importInstances", default=True),
            bool_option("useAsAnimationCache", default=True),
            bool_option("readAnimData", default=True),
            # TODO: Expose more parameters
            # "preferredMaterial=none",
            # "importRelativeTextures=Automatic",
            # "useCustomFrameRange=0",
            # "startTime=0",
            # "endTime=0",
            # "importUSDZTextures=0"
            # Avoid any automatic up-axis and unit conversions
            # TODO: Expose as optional options
            "upAxis=0",
            "unit=0"
        ])
        options["file_type"] = self.file_type

        # Maya USD import reference has the tendency to change the time slider
        # range and current frame, so we force revert it after
        with preserve_time_units():
            return super(MayaUSDReferenceLoader, self).process_reference(
                context, name, namespace, options
            )

    def update(self, container, context):
        # Maya USD import reference has the tendency to change the time slider
        # range and current frame, so we force revert it after
        with preserve_time_units():
            super(MayaUSDReferenceLoader, self).update(container, context)
