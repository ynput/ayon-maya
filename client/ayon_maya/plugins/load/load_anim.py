import os
import json
import maya.cmds as cmds
import ayon_api
from ayon_maya.api import plugin
from ayon_core.pipeline.load.utils import get_representation_context
from ayon_maya.plugins.load.load_reference import ReferenceLoader
import logging
import pymel.core as pm

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
        anim_file = context['representation']['attrib']['path']
        self.log.info(f"anim_file: {anim_file}")
        name_space = context['representation']['data']['context']['product']['name'].replace(
            context['representation']['data']['context']['product']['type'], '')
        if not cmds.namespace(exists=name_space):
            assets = context['version']['data'].get("assets", [])
            self.log.info(f"assets: {assets}")
            current_asset = [asset for asset in assets if asset['asset_name'] in anim_file]
            if not current_asset:
                self.log.warning(f"Asset not found in version data.")
                return
            current_asset = current_asset[0]
            asset_data = ayon_api.get_folder_by_name(project_name=project_name, folder_name=current_asset['asset_name'])
            versions = ayon_api.get_last_version_by_product_name(project_name, "rigMain", asset_data['id'])
            representations = ayon_api.get_representations(
                project_name=project_name,
                version_ids={versions['id']},
                fields={"id", "name", "files.path"}
            )
            rep_id = None
            for rep in representations:
                if rep['name'] == 'ma':
                    rep_id = rep['id']
                    break
            context = get_representation_context(project_name, rep_id)
            options = {'attach_to_root': True, "group_name": f"{name_space}:_GRP"}
            _plugin = ReferenceLoader()
            _plugin.process_reference(context=context, name=context['product']['name'],
                                      namespace=name_space, options=options)
        ctrl_set = pm.ls(name_space + ":rigMain_controls_SET")
        if not ctrl_set:
            self.log.warning("No control set found in instance data")
            return
        ctrls = pm.listConnections(ctrl_set[0], source=1, type='transform')
        if not ctrls:
            self.log.warning("No controls found in instance data")
            return
        self.log.debug(f"ctrls: {ctrls}")
        self.log.debug(f"namespace: {namespace}")
        self.log.debug(f"anim_file: {anim_file}")
        read_anim(filepath=anim_file, objects=ctrls)


def read_anim(filepath='C:/temp/anim.anim', objects=pm.selected(), namespace=None):
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
