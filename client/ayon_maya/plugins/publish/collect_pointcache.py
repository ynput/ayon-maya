import pyblish.api
from ayon_maya.api import plugin
from maya import cmds


class CollectPointcache(plugin.MayaInstancePlugin):
    """Collect pointcache data for instance."""

    order = pyblish.api.CollectorOrder + 0.224
    families = ["pointcache"]
    label = "Collect Pointcache"

    def process(self, instance):
        if instance.data.get("farm"):
            instance.data["families"].append("workfile_publish_on_farm")

        proxy_set = None
        for node in cmds.ls(instance.data["setMembers"],
                            exactType="objectSet"):
            # Find proxy_SET objectSet in the instance for proxy meshes
            if node.endswith("proxy_SET"):
                members = cmds.sets(node, query=True)
                if members is None:
                    self.log.debug("Skipped empty proxy_SET: \"%s\" " % node)
                    continue
                self.log.debug("Found proxy set: {}".format(node))

                proxy_set = node
                instance.data["proxy"] = []
                instance.data["proxyRoots"] = []
                for member in members:
                    instance.data["proxy"].extend(cmds.ls(member, long=True))
                    instance.data["proxyRoots"].extend(
                        cmds.ls(member, long=True)
                    )
                    instance.data["proxy"].extend(
                        cmds.listRelatives(member, shapes=True, fullPath=True)
                    )
                self.log.debug(
                    "Found proxy members: {}".format(instance.data["proxy"])
                )
                break

        if proxy_set:
            instance.remove(proxy_set)
            instance.data["setMembers"].remove(proxy_set)
