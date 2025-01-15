import pyblish.api
from ayon_maya.api import plugin


class CollectRemoveMarked(plugin.MayaContextPlugin):
    """Remove marked data

    Remove instances that have 'remove' in their instance.data

    """

    order = pyblish.api.CollectorOrder + 0.499
    label = 'Remove Marked Instances'

    def process(self, context):

        self.log.debug(context)
        instances_to_remove = []
        for instance in context:
            if instance.data.get('remove'):
                instances_to_remove.append(instance)

        for instance in instances_to_remove:
            context.remove(instance)
