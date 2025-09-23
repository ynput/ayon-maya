from ayon_maya.api.lib import get_container_members, unique_namespace
from ayon_maya.api.pipeline import containerise
from ayon_maya.api import plugin
from maya import cmds, mel


class AudioLoader(plugin.Loader):
    """Specific loader of audio."""

    product_types = {"audio"}
    label = "Load audio"
    representations = {"wav"}
    icon = "volume-up"
    color = "orange"

    def load(self, context, name, namespace, data):

        start_frame = cmds.playbackOptions(query=True, min=True)
        sound_node = cmds.sound(
            file=self.filepath_from_context(context), offset=start_frame
        )
        cmds.timeControl(
            mel.eval("$gPlayBackSlider=$gPlayBackSlider"),
            edit=True,
            sound=sound_node,
            displaySound=True
        )

        folder_name = context["folder"]["name"]
        namespace = namespace or unique_namespace(
            folder_name + "_",
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="_",
        )

        return containerise(
            name=name,
            namespace=namespace,
            nodes=[sound_node],
            context=context,
            loader=self.__class__.__name__
        )

    def update(self, container, context):
        repre_entity = context["representation"]

        members = get_container_members(container)
        audio_nodes = cmds.ls(members, type="audio")

        assert audio_nodes is not None, "Audio node not found."
        audio_node = audio_nodes[0]

        current_sound = cmds.timeControl(
            mel.eval("$gPlayBackSlider=$gPlayBackSlider"),
            query=True,
            sound=True
        )
        activate_sound = current_sound == audio_node

        path = self.filepath_from_context(context)

        cmds.sound(
            audio_node,
            edit=True,
            file=path
        )

        # The source start + end does not automatically update itself to the
        # length of thew new audio file, even though maya does do that when
        # creating a new audio node. So to update we compute it manually.
        # This would however override any source start and source end a user
        # might have done on the original audio node after load.
        audio_frame_count = cmds.getAttr("{}.frameCount".format(audio_node))
        audio_sample_rate = cmds.getAttr("{}.sampleRate".format(audio_node))
        duration_in_seconds = audio_frame_count / audio_sample_rate
        fps = mel.eval('currentTimeUnitToFPS()')  # workfile FPS
        source_start = 0
        source_end = (duration_in_seconds * fps)
        cmds.setAttr("{}.sourceStart".format(audio_node), source_start)
        cmds.setAttr("{}.sourceEnd".format(audio_node), source_end)

        if activate_sound:
            # maya by default deactivates it from timeline on file change
            cmds.timeControl(
                mel.eval("$gPlayBackSlider=$gPlayBackSlider"),
                edit=True,
                sound=audio_node,
                displaySound=True
            )

        cmds.setAttr(
            container["objectName"] + ".representation",
            repre_entity["id"],
            type="string"
        )

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
