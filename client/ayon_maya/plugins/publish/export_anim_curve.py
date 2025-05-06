import os
import json
import logging
import pymel.core as pm

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

from ayon_maya.api import plugin
from pyblish.api import ExtractorOrder


class ExtractAnimCrv(plugin.MayaExtractorPlugin):
    order = ExtractorOrder
    label = "Extract Animation curves"
    families = ["animation"]
    hosts = ["maya"]

    def process(self, instance):
        instance_data = instance.data
        # Define output path
        staging_dir = self.staging_dir(instance)
        filename = "{0}.anim".format(instance_data['variant'])
        out_path = os.path.join(staging_dir, filename)
        controls = [x for x in instance_data['setMembers'] if x.endswith(":rigMain_controls_SET")]
        if not controls:
            self.log.warning("No controls found in instance data")
            return
        ctrls = pm.listConnections(controls[0], source=1, type='transform')
        name_space = instance_data['variant']
        reference_node = [x for x in pm.listReferences() if x.namespace == name_space][0]
        self.log.info(f"controls: {controls}")
        self.write_anim(objects=ctrls, filepath=os.path.realpath(out_path), namespace=name_space)
        if "representations" not in instance.data:
            instance.data["representations"] = []
        representation = {
            'name': 'anim', 'ext': 'anim',
            'files': os.path.basename(out_path),
            'stagingDir': staging_dir.replace("\\", "/")
        }
        version_data = instance.data.get("versionData", {})
        assets = version_data.get("assets", [])
        if not assets:
            version_data["assets"] = []
        asset_data = {
            "namespace": name_space,
            "path": reference_node.path.__str__(),
            "asset_name": name_space.split("_rigMain_")[0],
        }
        version_data["assets"].append(asset_data)
        instance_data["data"] = [name_space + ':' + reference_node.path.__str__()]
        instance.data["assets"] = [name_space + ':' + reference_node.path.__str__()]
        instance.data["versionData"] = version_data
        self.log.info(f"representation: {representation}")
        instance.data["representations"].append(representation)

    def write_anim(self, objects=pm.selected(), filepath='C:/temp/anim.anim', namespace=None):
        self.log.info(f"objects: {objects}")
        self.log.info(f"Writing animation curves to {filepath}")
        self.log.info(f"namespace: {namespace}")
        anim_data = {}
        for j, obj in enumerate(objects):
            obj_shot_name = obj.name()
            obj_longname = obj.longName()
            if namespace:
                obj_longname = obj_longname.replace(namespace, '{namespace}')
            anim_data[obj_longname] = {}

            channels = obj.listConnections(type='animCurve', connections=True, s=1, d=0)
            channel_dict = {}
            for i, channel in enumerate(channels):
                channel = channel[1]
                split_name = obj_shot_name
                channel_name = (channels[i][0].name().split(split_name + '.')[1])
                if channel_name not in channel_dict:
                    channel_dict[channel_name] = {}
                channel_dict[channel_name]['type'] = 'keyed'

                keys = pm.animation.keyframe(channel, q=True)
                values = pm.animation.keyframe(channel, q=True, valueChange=True)
                breakdown = pm.animation.keyframe(channel, q=True, breakdown=True)
                in_tangent_type = pm.animation.keyTangent(channel, q=True, inTangentType=True)
                out_tangent_type = pm.animation.keyTangent(channel, q=True, outTangentType=True)
                lock = pm.animation.keyTangent(channel, q=True, lock=True)
                weight_lock = pm.animation.keyTangent(channel, q=True, weightLock=True)
                in_angle = pm.animation.keyTangent(channel, q=True, inAngle=True)
                out_angle = pm.animation.keyTangent(channel, q=True, outAngle=True)
                in_weight = pm.animation.keyTangent(channel, q=True, inWeight=True)
                out_weight = pm.animation.keyTangent(channel, q=True, outWeight=True)
                weighted_tangents = pm.animation.keyTangent(channel, q=True, weightedTangents=True)[0]

                pre_infinity = channel.preInfinity.get()
                post_infinity = channel.postInfinity.get()
                channel_dict[channel_name]['infinity'] = {
                    'preInfinity': json.dumps(pre_infinity),
                    'postInfinity': json.dumps(post_infinity),
                    'weightedTangents': json.dumps(weighted_tangents),
                }

                channel_dict[channel_name]['keys'] = []
                for y, key in enumerate(keys):
                    bd = 0
                    for bd_item in breakdown:
                        if bd_item == key:
                            bd = 1
                    channel_dict[channel_name]['keys'].append({
                        'key': json.dumps(keys[y]),
                        'value': json.dumps(values[y]),
                        'breakdown': json.dumps(bd),
                        'inTangentType': json.dumps(in_tangent_type[y]),
                        'outTangentType': json.dumps(out_tangent_type[y]),
                        'lock': json.dumps(lock[y]),
                        'weightLock': json.dumps(weight_lock[y]),
                        'inAngle': json.dumps(in_angle[y]),
                        'outAngle': json.dumps(out_angle[y]),
                        'inWeight': json.dumps(in_weight[y]),
                        'outWeight': json.dumps(out_weight[y])
                    })
            static_chans = pm.listAnimatable(obj)
            for static_chan in static_chans:
                test_it = pm.keyframe(static_chan, q=True)
                connected = pm.listConnections(static_chan, destination=False, source=True)
                if test_it or connected:
                    logger.warning('skipping for {0} as attribute {1} is connected'.format(obj_shot_name, static_chan))
                    continue
                if pm.nodeType(static_chan.name().split(".")[0]) == "camera":
                    static_name = static_chan.name().split('.')[1]
                else:
                    static_name = static_chan.name().split(obj_shot_name + '.')
                    if not len(static_name) > 1:
                        continue
                    static_name = static_name[1]
                # static_name = static_chan.name().split(obj_shot_name + '.')[1]
                if static_name not in channel_dict:
                    channel_dict[static_name] = {'type': 'static'}
                channel_dict[static_name]['value'] = static_chan.get()
            anim_data[obj_longname] = channel_dict
        if not os.path.exists(os.path.dirname(filepath)):
            os.makedirs(os.path.dirname(filepath))
        with open(filepath, 'w') as json_file:
            json.dump(anim_data, json_file, indent=4)
        return filepath
