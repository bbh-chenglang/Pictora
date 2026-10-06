import asyncio
import time
import httpx
from app.video.repository import VideoError

# Verified from the customer contract (2026-10-06); unknown != unsupported or unlimited.
RULES = {
 'grok-1.5': (7,None,None), 'minimax-h3': (9,3,3),
 'sd-2.0-900-J3': (9,None,None), 'sd-2.0-933-720-fast-原生真人': (9,3,3),
 'sd-2.0-J1': (9,0,3), 'sd-2.0-J2': (9,3,3), 'sd-2.5-J2': (30,10,10),
 'seedance-2.0-900': (9,None,None), 'seedance-2.5-101010': (10,0,10),
 'seedance-2.5-301010': (30,0,10), 'seedance-2.5-900': (9,None,None),
}

def bundled_models():
    result=[]
    for name,limits in RULES.items():
        low,high,default=4,30,5
        if name=='grok-1.5': low,high=3,15
        elif name=='minimax-h3': high,default=15,15
        elif name=='sd-2.0-J1': high,default=15,15
        elif name=='sd-2.0-J2': low,high=5,15
        elif name=='sd-2.5-J2': low,default=5,30
        elif name in ('seedance-2.0-900','sd-2.0-933-720-fast-原生真人'): high=15
        elif name=='sd-2.0-900-J3': default=10
        durations=[10,15] if name=='sd-2.0-900-J3' else list(range(low,high+1))
        resolutions=['2k'] if name=='minimax-h3' else (['480p','720p','1080p'] if name=='sd-2.5-J2' else ['720p'])
        result.append({'id':name,'default_duration':default,'default_resolution':'2k' if name=='minimax-h3' else '720p','default_ratio':'16:9','ratios':['9:16','1:1','3:4','4:3','16:9'] if name=='minimax-h3' else ['16:9','9:16','1:1'],'durations_by_resolution':{r:durations for r in resolutions},'reference_limits':dict(zip(('image','video','audio'),limits)),'max_total_materials':10 if name=='minimax-h3' else None,'max_video_duration_seconds':15 if name=='minimax-h3' else None})
    return result

class VideoCatalog:
    def __init__(self,base_url,transport=None):
        self.base_url=base_url.rstrip('/')
        self.transport=transport
        self.models=bundled_models()
        self.source='bundled_snapshot_2026-10-06'
        self.expires=0.0
        self.lock=asyncio.Lock()

    async def get(self):
        if time.monotonic()<self.expires:
            return self.models
        async with self.lock:
            if time.monotonic()<self.expires:
                return self.models
            try:
                async with httpx.AsyncClient(transport=self.transport,timeout=15,follow_redirects=False,trust_env=False) as client:
                    response=await client.get(self.base_url+'/api/pricing')
                    response.raise_for_status()
                    data=response.json()
                if not isinstance(data,dict) or not isinstance(data.get('data'),list) or data.get('success') is False:
                    raise ValueError('Invalid catalog')
                fresh=[]
                for row in data['data']:
                    name=row.get('model_name')
                    pricing=row.get('video_pricing')
                    if name not in RULES or not isinstance(pricing,dict): continue
                    tiers={}
                    for tier in pricing.get('tiers',[]):
                        duration,resolution=tier.get('duration'),tier.get('resolution')
                        if type(duration) is int and 0<duration<=300 and resolution in ('480p','720p','1080p','2k'):
                            tiers.setdefault(resolution,set()).add(duration)
                    ratios=pricing.get('ratios',[])
                    default_resolution=pricing.get('default_resolution')
                    default_duration=pricing.get('default_duration')
                    if not tiers or default_duration not in tiers.get(default_resolution,set()) or not ratios or not all(isinstance(r,str) for r in ratios): continue
                    model=next(m for m in bundled_models() if m['id']==name)
                    model.update(default_duration=default_duration,default_resolution=default_resolution,default_ratio=pricing.get('default_ratio','16:9'),ratios=ratios,durations_by_resolution={r:sorted(ds) for r,ds in tiers.items()})
                    if model['default_ratio'] not in ratios: continue
                    fresh.append(model)
                if not fresh: raise ValueError('Empty catalog')
                self.models=fresh
                self.source='live_catalog'
                self.expires=time.monotonic()+600
            except (httpx.HTTPError,ValueError,TypeError,AttributeError):
                # Preserve the last verified snapshot; never expand unknown capabilities.
                self.expires=time.monotonic()+60
        return self.models

    async def normalize(self,request,materials):
        model=next((m for m in await self.get() if m['id']==request.model),None)
        if model is None:
            raise VideoError('video_model_unsupported','所选视频模型未开放',422)
        resolution=request.resolution or model['default_resolution']
        duration=request.duration if request.duration is not None else model['default_duration']
        ratio=request.ratio or model['default_ratio']
        if duration not in model['durations_by_resolution'].get(resolution,[]) or ratio not in model['ratios']:
            raise VideoError('video_parameters_invalid','时长、分辨率或比例不在该模型的有效档位内',422)
        names=set()
        sources=set()
        for material in materials:
            if material['name'] in names:
                raise VideoError('video_material_name_duplicate','素材名称必须互不相同',422)
            if material['url'] in sources:
                raise VideoError('video_material_duplicate','不要重复提交同一个素材',422)
            names.add(material['name']); sources.add(material['url'])
        for kind in ('image','video','audio'):
            count=sum(m['type']==kind for m in materials)
            limit=model['reference_limits'][kind]
            if count and (limit is None or count>limit):
                raise VideoError('video_material_unsupported',f'所选模型不支持、尚未确认或超过{kind}参考数量',422)
        if model['max_total_materials'] is not None and len(materials)>model['max_total_materials']:
            raise VideoError('video_material_total','此模型的所有素材合计最多 10 个',422)
        if request.model=='minimax-h3':
            videos=[m for m in materials if m['type']=='video']
            if any(not m.get('duration_seconds') for m in videos) or sum(m.get('duration_seconds',0) for m in videos)>15.001:
                raise VideoError('video_material_duration','参考视频真实时长合计不能超过 15 秒',422)
        payload={'model':request.model,'prompt':request.prompt,'duration':duration,'resolution':resolution,'ratio':ratio}
        for kind,field in (('image','images'),('video','videos'),('audio','audios')):
            items=[]
            for material in materials:
                if material['type']!=kind: continue
                item={'url':material['url'],'name':material['name']}
                if kind=='video' and request.model=='minimax-h3': item['duration_seconds']=material['duration_seconds']
                items.append(item)
            if items: payload[field]=items
        return payload
