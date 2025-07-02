from ayon_core.pipeline import get_representation_path
from ayon_maya.api.lib import (
    get_container_members,
    namespaced,
    pairwise,
    unique_namespace,
)
from ayon_maya.api.pipeline import containerise
from ayon_maya.api import plugin
from maya import cmds
from qtpy import QtCore, QtWidgets


def disconnect_inputs(plug):
    overrides = cmds.listConnections(plug,
                                     source=True,
                                     destination=False,
                                     plugs=True,
                                     connections=True) or []
    for dest, src in pairwise(overrides):
        cmds.disconnectAttr(src, dest)


class CameraWindow(QtWidgets.QDialog):

    def __init__(self, cameras):
        super(CameraWindow, self).__init__()
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.FramelessWindowHint)

        self.camera = None

        self.widgets = {
            "label": QtWidgets.QLabel("Select camera for image plane."),
            "list": QtWidgets.QListWidget(),
            "staticImagePlane": QtWidgets.QCheckBox(),
            "showInAllViews": QtWidgets.QCheckBox(),
            "warning": QtWidgets.QLabel("No cameras selected!"),
            "buttons": QtWidgets.QWidget(),
            "okButton": QtWidgets.QPushButton("Ok"),
            "cancelButton": QtWidgets.QPushButton("Cancel")
        }

        # Build warning.
        self.widgets["warning"].setVisible(False)
        self.widgets["warning"].setStyleSheet("color: red")

        # Build list.
        for camera in cameras:
            self.widgets["list"].addItem(camera)


        # Build buttons.
        layout = QtWidgets.QHBoxLayout(self.widgets["buttons"])
        layout.addWidget(self.widgets["okButton"])
        layout.addWidget(self.widgets["cancelButton"])

        # Build layout.
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.widgets["label"])
        layout.addWidget(self.widgets["list"])
        layout.addWidget(self.widgets["buttons"])
        layout.addWidget(self.widgets["warning"])

        self.widgets["okButton"].pressed.connect(self.on_ok_pressed)
        self.widgets["cancelButton"].pressed.connect(self.on_cancel_pressed)
        self.widgets["list"].itemPressed.connect(self.on_list_itemPressed)

    def on_list_itemPressed(self, item):
        self.camera = item.text()

    def on_ok_pressed(self):
        if self.camera is None:
            self.widgets["warning"].setVisible(True)
            return

        self.close()

    def on_cancel_pressed(self):
        self.camera = None
        self.close()


class ImagePlaneLoader(plugin.Loader):
    """Specific loader of plate for image planes on selected camera."""

    product_types = {"image", "plate", "render"}
    label = "Load imagePlane"
    representations = {"*"}
    extensions = {"mov", "mp4", "exr", "png", "jpg", "jpeg"}
    icon = "image"
    color = "orange"

    def load(self, context, name, namespace, data, options=None):

        image_plane_depth = 1000
        folder_name = context["folder"]["name"]
        namespace = namespace or unique_namespace(
            folder_name + "_",
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="_",
        )

        # Get camera from user selection.
        # is_static_image_plane = None
        # is_in_all_views = None
        camera = data.get("camera") if data else None

        if not camera:
            cameras = cmds.ls(type="camera")

            # Cameras by names
            camera_names = {}
            for camera in cameras:
                parent = cmds.listRelatives(camera, parent=True, path=True)[0]
                camera_names[parent] = camera

            camera_names["Create new camera."] = "create-camera"
            window = CameraWindow(camera_names.keys())
            window.exec_()
            # Skip if no camera was selected (Dialog was closed)
            if window.camera not in camera_names:
                return
            camera = camera_names[window.camera]

        if camera == "create-camera":
            camera = cmds.createNode("camera")

        if camera is None:
            return

        try:
            cmds.setAttr("{}.displayResolution".format(camera), True)
            cmds.setAttr("{}.farClipPlane".format(camera),
                         image_plane_depth * 10)
        except RuntimeError:
            pass

        # Create image plane
        with namespaced(namespace):
            # Create inside the namespace
            image_plane_transform, image_plane_shape = cmds.imagePlane(
                fileName=self.filepath_from_context(context),
                camera=camera
            )

        # Set colorspace
        colorspace = self.get_colorspace(context["representation"])
        if colorspace:
            cmds.setAttr(
                "{}.ignoreColorSpaceFileRules".format(image_plane_shape),
                True
            )
            cmds.setAttr("{}.colorSpace".format(image_plane_shape),
                         colorspace, type="string")

        # Set offset frame range
        start_frame = cmds.playbackOptions(query=True, min=True)
        end_frame = cmds.playbackOptions(query=True, max=True)

        for attr, value in {
            "depth": image_plane_depth,
            "frameOffset": 0,
            "frameIn": start_frame,
            "frameOut": end_frame,
            "frameCache": end_frame,
            "useFrameExtension": True
        }.items():
            plug = "{}.{}".format(image_plane_shape, attr)
            cmds.setAttr(plug, value)

        movie_representations = {"mov", "preview"}
        if context["representation"]["name"] in movie_representations:
            cmds.setAttr(image_plane_shape + ".type", 2)

        # Ask user whether to use sequence or still image.
        if context["representation"]["name"] == "exr":
            # Ensure OpenEXRLoader plugin is loaded.
            cmds.loadPlugin("OpenEXRLoader", quiet=True)

            message = (
                "Hold image sequence on first frame?"
                "\n{} files available.".format(
                    len(context["representation"]["files"])
                )
            )
            reply = QtWidgets.QMessageBox.information(
                None,
                "Frame Hold.",
                message,
                QtWidgets.QMessageBox.Yes,
                QtWidgets.QMessageBox.No
            )
            if reply == QtWidgets.QMessageBox.Yes:
                frame_extension_plug = "{}.frameExtension".format(image_plane_shape)  # noqa

                # Remove current frame expression
                disconnect_inputs(frame_extension_plug)

                cmds.setAttr(frame_extension_plug, start_frame)

        new_nodes = [image_plane_transform, image_plane_shape]

        return containerise(
            name=name,
            namespace=namespace,
            nodes=new_nodes,
            context=context,
            loader=self.__class__.__name__
        )

    def update(self, container, context):
        folder_entity = context["folder"]
        repre_entity = context["representation"]

        members = get_container_members(container)
        image_planes = cmds.ls(members, type="imagePlane")
        assert image_planes, "Image plane not found."
        image_plane_shape = image_planes[0]

        path = get_representation_path(repre_entity)
        cmds.setAttr("{}.imageName".format(image_plane_shape),
                     path,
                     type="string")
        cmds.setAttr("{}.representation".format(container["objectName"]),
                     repre_entity["id"],
                     type="string")

        colorspace = self.get_colorspace(repre_entity)
        if colorspace:
            cmds.setAttr(
                "{}.ignoreColorSpaceFileRules".format(image_plane_shape),
                True
            )
            cmds.setAttr("{}.colorSpace".format(image_plane_shape),
                         colorspace, type="string")

        # Set frame range.
        start_frame = folder_entity["attrib"]["frameStart"]
        end_frame = folder_entity["attrib"]["frameEnd"]

        for attr, value in {
            "frameOffset": 0,
            "frameIn": start_frame,
            "frameOut": end_frame,
            "frameCache": end_frame
        }:
            plug = "{}.{}".format(image_plane_shape, attr)
            cmds.setAttr(plug, value)

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        members = cmds.sets(container['objectName'], query=True)
        cmds.lockNode(members, lock=False)
        cmds.delete([container['objectName']] + members)

        # Clean up the namespace
        try:
            cmds.namespace(removeNamespace=container['namespace'],
                           deleteNamespaceContent=True)
        except RuntimeError:
            pass

    def get_colorspace(self, representation):

        data = representation.get("data", {}).get("colorspaceData", {})
        if not data:
            return

        colorspace = data.get("colorspace")
        return colorspace
