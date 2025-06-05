import os
import json
import logging

import maya.cmds as cmds
import pymel.core as pm

from ayon_maya.api import plugin
from ayon_core.pipeline.load.utils import get_representation_context
from ayon_core.pipeline.load import get_loaders_by_name
# from ayon_maya.plugins.load.load_reference import ReferenceLoader
from ayon_maya.api import lib

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class AnimLoader(plugin.Loader):
    """Load anim on character"""

    product_types = {"animation"}
    representations = {"anim"}

    label = "Load Anim"
    order = -5
    icon = "code-fork"
    color = "orange"

    def load(self, context, name, namespace, data):
        project_name = context['project']['name']
        folder_name = context["folder"]["name"]
        anim_file = self.filepath_from_context(context)
        assets = context['version']['data'].get("assets", [])
        current_asset = [asset for asset in assets if asset['namespace'] in anim_file]
        if not current_asset:
            self.log.warning(f"Asset not found in version data for animation file: {anim_file}")
            return
        current_asset = current_asset[0]
        # check if the asset is already loaded
        if not cmds.namespace(exists=current_asset['namespace']):
            self.log.info(f"Asset namespace {current_asset['namespace']} does not exist, loading asset.")
            asset_context = get_representation_context(project_name, current_asset['representation_id'])
            self.log.info(f"asset_context: {asset_context}")
            data['attach_to_root'] = True
            loader_classes = get_loaders_by_name()
            reference_loader = loader_classes.get('ReferenceLoader')()
            reference_loader.load(context=asset_context, name=asset_context['product']['name'],
                         namespace=current_asset['namespace'], options=data)

        ctrl_set = pm.ls(f"{current_asset['namespace']}:{current_asset['product_name']}_controls_SET")
        if not ctrl_set:
            self.log.warning("No control set found in instance data")
            return
        ctrls = pm.listConnections(ctrl_set[0], source=1, type='transform')
        if not ctrls:
            self.log.warning("No controls found in instance data")
            return
        read_anim(filepath=anim_file, objects=ctrls)


def read_anim(filepath, objects, namespace=None):
    if not os.path.exists(filepath):
        return [False, 'invalid filepath']
    with open(filepath, "r", encoding='utf-8') as reader:
        anim_data = json.loads(reader.read())
    for j, obj in enumerate(objects):
        obj_shot_name = obj.name()
        obj_longname = obj.longName()
        if namespace:
            obj_longname = obj_longname.replace(namespace, '{namespace}')
        ctrl_value = anim_data.get(obj_longname, [])
        if not ctrl_value:
            continue
        for attrs in ctrl_value:
            if not hasattr(obj, attrs):
                continue
            if attrs in ['lock']:
                continue
            try:
                cur_attr = getattr(obj, attrs)
            except AttributeError as e:
                logger.warning(e)
                logger.warning('skipping for {0} as attribute {1} was not found'.format(obj_shot_name, attrs))
                continue
            key_type = ctrl_value[attrs]['type']
            if key_type == 'static':
                key_value = ctrl_value[attrs]['value']
                connected = pm.listConnections(cur_attr, destination=False, source=True)
                if not connected and not cur_attr.isLocked():
                    cur_attr.set(key_value)
            if key_type == 'keyed':
                key_values = ctrl_value[attrs]['keys']
                infinity_data = ctrl_value[attrs]['infinity']
                pre_infinity = json.loads(infinity_data.get('preInfinity'))
                post_infinity = json.loads(infinity_data.get('postInfinity'))
                weighted_tangents = json.loads(infinity_data.get('weightedTangents'))
                for keys in key_values:
                    time = json.loads(keys.get('key'))
                    value = json.loads(keys.get('value'))
                    breakdown = json.loads(keys.get('breakdown'))
                    tan_lock = json.loads(keys.get('lock'))
                    weight_lock = json.loads(keys.get('weightLock'))
                    in_type = json.loads(keys.get('inTangentType'))
                    out_type = json.loads(keys.get('outTangentType'))
                    tan1 = json.loads(keys.get('inAngle'))
                    tan2 = json.loads(keys.get('outAngle'))
                    weight1 = json.loads(keys.get('inWeight'))
                    weight2 = json.loads(keys.get('outWeight'))
                    pm.setKeyframe(cur_attr, time=time, value=value, bd=breakdown)
                    if weighted_tangents:
                        pm.keyTangent(cur_attr, weightedTangents=True, edit=True)
                    try:
                        pm.keyTangent(cur_attr, lock=tan_lock, time=time)
                    except Exception as e:
                        logger.warning(e)

                    if weighted_tangents:
                        pm.keyTangent(cur_attr, time=time, weightLock=weight_lock)
                    if in_type != 'fixed' and out_type != 'fixed':
                        pm.keyTangent(cur_attr, e=1, a=1, time=time, itt=in_type, ott=out_type)
                    if in_type == 'fixed' and out_type != 'fixed':
                        pm.keyTangent(cur_attr, e=1, a=1, time=time, inAngle=tan1, inWeight=weight1, itt=in_type,
                                      ott=out_type)
                    if in_type == 'fixed' and out_type == 'fixed':
                        pm.keyTangent(cur_attr, e=1, a=1, time=time, inAngle=tan1, inWeight=weight1, outAngle=tan2,
                                      outWeight=weight2, itt=in_type, ott=out_type)

                    pm.setInfinity(cur_attr, poi=post_infinity, pri=pre_infinity)
    return None
