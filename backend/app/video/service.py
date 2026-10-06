import asyncio
from datetime import datetime,timezone
import io
import json
import logging
import math
from pathlib import Path
import shutil
import time
from urllib.parse import urlsplit
from uuid import uuid4
from fastapi import UploadFile
from app.video.capabilities import VideoCatalog
from app.video.media import VideoAssets,LIMITS,probe_media
from app.video.network import https_url,safe_download
from app.video.provider import VideoProvider,UnavailableVideoProvider
from app.video.repository import VideoError,VideoRepository
from app.video.storage import R2Storage
from app.video.schemas import TRACKED_STATUSES

logger=logging.getLogger(__name__)
WAIT_STATUSES={'queued','in_progress','unknown','pending','processing'}

class VideoService:
    def __init__(self,repository,settings,*,storage=None,provider=None,catalog=None,probe=probe_media,media_transport=None):
        self.repository=repository
        self.settings=settings
        self.storage=storage or R2Storage(settings)
        self.provider_error=None
        try:
            self.provider=provider or VideoProvider(settings)
        except VideoError as exc:
            self.provider_error=exc
            self.provider=UnavailableVideoProvider(exc)
        self.catalog=catalog or VideoCatalog(settings.video_api_base_url)
        if self.provider_error and catalog is None:
            self.catalog.expires=float('inf')  # Never request an invalid optional root.
        self.assets=VideoAssets(repository,settings,probe)
        self.probe=probe
        self.media_transport=media_transport
        self.jobs={}
        self.semaphore=asyncio.Semaphore(max(1,settings.video_max_concurrency))
        self.maintenance=None
        self.closed=False

    async def features(self):
        return {'api_ready':self.provider_error is None,'assets_ready':self.assets.ready,'storage_configured':self.storage.configured,'storage_ready':await self.storage.check(),'media_tools_ready':self.probe is not probe_media or shutil.which('ffprobe') is not None,'catalog_source':self.catalog.source,'api_base_url':self.settings.video_api_base_url if self.provider_error is None else '','notes':['上传素材需配置公网 HTTPS；结果保存在管理员配置的 R2 私有桶。','任务等待超时或放弃追踪不会取消上游任务，也不代表退款。']}

    async def require_pipeline(self):
        if self.probe is probe_media and not shutil.which('ffprobe'):
            raise VideoError('video_probe_missing','服务器尚未安装 ffprobe，已阻止付费提交',503)
        if not await self.storage.check():
            raise VideoError('video_storage_unavailable','R2 尚未配置或连接检查未通过，已阻止付费提交',503)

    async def create(self,user_id,request):
        request_json=json.dumps(request.model_dump(mode='json'),ensure_ascii=False,sort_keys=True,separators=(',',':'))
        existing=await self.repository.existing_request(user_id,request.request_id,request_json)
        if existing is not None: return existing
        await self.repository.get_key(user_id,request.api_key_config_id)
        owned=await self.repository.rows('SELECT 1 FROM projects WHERE id=? AND user_id=?',(request.project_id,user_id))
        if not owned: raise VideoError('project_not_found','项目不存在',404)
        if self.provider_error: raise self.provider_error
        await self.require_pipeline()
        materials=[]
        asset_ids=[]
        counts={'image':0,'video':0,'audio':0}
        for material in request.materials:
            kind=material.type
            counts[kind]+=1
            item={'type':kind,'name':material.name or {'image':'图片','video':'视频','audio':'音频'}[kind]+str(counts[kind])}
            if material.asset_id:
                asset=await self.repository.get_asset(material.asset_id,user_id)
                if asset['type']!=kind: raise VideoError('video_material_type','素材类型与上传文件不一致',422)
                if not self.assets.path(asset['relative_path']).is_file(): raise VideoError('video_asset_missing','素材文件已不可用',409)
                item['url']=self.assets.signed_url(asset['id'])
                item['duration_seconds']=asset['duration_seconds']
                asset_ids.append(asset['id'])
            else:
                item['url']=https_url(material.url)
            materials.append(item)
        # Check model/type/count rules before fetching any external material.
        model=next((m for m in await self.catalog.get() if m['id']==request.model),None)
        if not model: raise VideoError('video_model_unsupported','视频模型未开放',422)
        for kind,count in counts.items():
            limit=model['reference_limits'][kind]
            if count and (limit is None or count>limit):
                raise VideoError('video_material_unsupported',f'所选模型不支持、尚未确认或超过{kind}参考数量',422)
        if request.model=='minimax-h3':
            for item in materials:
                if item['type']=='video' and not item.get('duration_seconds'):
                    temporary=self.assets.path(f'probe/{uuid4().hex}.mp4')
                    temporary.parent.mkdir(parents=True,exist_ok=True)
                    try:
                        await safe_download(item['url'],temporary,LIMITS['video'],self.media_transport)
                        item['duration_seconds']=(await self.probe(temporary,'video'))['duration_seconds']
                    finally:
                        temporary.unlink(missing_ok=True)
        payload=await self.catalog.normalize(request,materials)
        task_id,created=await self.repository.create_task(user_id,request,request_json,payload,asset_ids,self.settings)
        if created: self.schedule(user_id,task_id)
        return await self.repository.get_task(user_id,task_id,public=True)

    def schedule(self,user_id,task_id):
        if self.closed or (task_id in self.jobs and not self.jobs[task_id].done()): return
        async def limited():
            async with self.semaphore:
                await self.run(user_id,task_id)
        job=asyncio.create_task(limited(),name=f'video-task-{task_id}')
        self.jobs[task_id]=job
        def discard(done):
            if self.jobs.get(task_id) is done: self.jobs.pop(task_id,None)
            if not done.cancelled() and done.exception() is not None:
                logger.error('Video task worker terminated task_id=%s',task_id)
        job.add_done_callback(discard)

    async def persist_upstream_id(self,task_id,upstream_id):
        work=asyncio.create_task(self.repository.update_task(task_id,upstream_task_id=upstream_id,status='running'))
        try: await asyncio.shield(work)
        except asyncio.CancelledError:
            await work
            raise

    async def run(self,user_id,task_id):
        task=await self.repository.get_task(user_id,task_id)
        key=None
        try:
            if task['tracking_abandoned']: return
            if not task['upstream_task_id']:
                if self.provider_error: raise self.provider_error
                await self.require_pipeline()
                key=(await self.repository.get_key(user_id,task['api_key_config_id']))['api_key']
                if not await self.repository.claim_submission(task_id): return
                payload=json.loads(task['payload_json'])
                # Sign immediately before POST, not when a queued task was created.
                request=json.loads(task['request_json'])
                for material in request.get('materials',[]):
                    if material.get('asset_id'):
                        asset=await self.repository.get_asset(material['asset_id'],user_id)
                        field={'image':'images','video':'videos','audio':'audios'}[material['type']]
                        for item in payload.get(field,[]):
                            if item['url'].split('?')[0].endswith('/'+asset['id']):
                                item['url']=self.assets.signed_url(asset['id'])
                response=await self.provider.create(key,payload)
                upstream_id=response.get('id') or response.get('task_id')
                if not isinstance(upstream_id,str) or not upstream_id.strip() or len(upstream_id)>256:
                    raise VideoError('video_submission_unknown','提交响应未提供任务 ID，请核对控制台，不要重复生成',502)
                await self.persist_upstream_id(task_id,upstream_id)
                task=await self.repository.get_task(user_id,task_id)
            else:
                await self.repository.update_task(task_id,status='running',error_code=None,error_message=None)
                response=None
            # An already completed upstream result can be saved from durable staging without re-querying.
            if task['upstream_status']=='completed' and task['results'] and all(self.assets.path(f"staging/{task_id}/{r['id']}.ready").is_file() or r['stored'] for r in task['results']):
                await self.save_results(user_id,task,{'result_urls':[None]*len(task['results'])},key)
                return
            if key is None: key=(await self.repository.get_key(user_id,task['api_key_config_id']))['api_key']
            deadline=time.monotonic()+max(0.1,self.settings.video_max_wait)
            while True:
                if time.monotonic()>=deadline:
                    raise VideoError('video_poll_timeout','自动等待已结束，上游可能继续执行；请稍后恢复查询',504)
                if response is None: response=await self.provider.query(key,task['upstream_task_id'],deadline)
                status=response.get('status')
                progress=response.get('progress')
                if type(progress) not in (int,float) or not math.isfinite(progress): progress=None
                elif progress is not None: progress=min(100,max(0,progress))
                await self.repository.update_task(task_id,upstream_status=str(status)[:80],progress=progress)
                if status=='completed':
                    task=await self.repository.get_task(user_id,task_id)
                    await self.save_results(user_id,task,response,key,deadline)
                    return
                if status in ('failed','cancelled'):
                    await self.repository.update_task(task_id,status='failed',error_code='video_upstream_failed',error_message='上游视频生成失败或已取消，请核对控制台的错误与账务记录',completed_at=datetime.now(timezone.utc).isoformat())
                    return
                if status not in WAIT_STATUSES:
                    raise VideoError('video_status_unknown','上游返回未识别状态，已暂停查询，请排查或稍后恢复',502)
                delay=max(0.01,self.settings.video_poll_interval)
                if time.monotonic()+delay>=deadline:
                    raise VideoError('video_poll_timeout','自动等待已结束，不代表任务失败或退款；可恢复查询',504)
                await asyncio.sleep(delay)
                response=None
        except asyncio.CancelledError:
            current=await self.repository.get_task(user_id,task_id)
            if not current['tracking_abandoned'] and current['status'] not in ('completed','failed'):
                status='polling_paused' if current['upstream_task_id'] else ('queued' if current['status']=='queued' else 'submission_unknown')
                await self.repository.update_task(task_id,status=status,error_code='video_worker_interrupted',error_message='本地任务中断，已有任务 ID 可恢复查询；未知提交需核对控制台')
            raise
        except Exception as exc:
            current=await self.repository.get_task(user_id,task_id)
            if current['tracking_abandoned']: return
            code=exc.code if isinstance(exc,VideoError) else 'video_operation_error'
            message=exc.message if isinstance(exc,VideoError) else '视频处理发生错误，请恢复原任务或核对控制台，不要自动重新生成'
            if key: message=message.replace(key,'[redacted]')
            if current['upstream_task_id']:
                status='storage_failed' if current['upstream_status']=='completed' else 'polling_paused'
            else:
                status='failed' if code=='video_submit_rejected' or current['status']=='queued' else 'submission_unknown'
            await self.repository.update_task(task_id,status=status,error_code=code,error_message=message)
            logger.warning('Video task paused task_id=%s code=%s',task_id,code)

    async def save_results(self,user_id,task,response,key=None,deadline=None):
        task_id=task['id']
        await self.repository.update_task(task_id,status='saving',upstream_status='completed',progress=100)
        await self.require_pipeline()
        urls=response.get('result_urls')
        count=len(urls) if isinstance(urls,list) and urls else 1
        if count>10: raise VideoError('video_result_count','返回结果数量超过本应用保存上限',502)
        for position in range(count):
            object_key=f"{self.settings.r2_key_prefix.rstrip('/')}/{user_id}/{task_id}/{uuid4().hex}.mp4"
            result=await self.repository.result_for_position(task_id,position,object_key)
            if result['stored']: continue
            ready=self.assets.path(f"staging/{task_id}/{result['id']}.ready")
            ready.parent.mkdir(parents=True,exist_ok=True)
            if not ready.is_file():
                if key is None: key=(await self.repository.get_key(user_id,task['api_key_config_id']))['api_key']
                url=await self.provider.content_url(key,task['upstream_task_id'],deadline) if position==0 else urls[position]
                if not isinstance(url,str): raise VideoError('video_result_not_ready','结果链接暂缺，请重试保存',502)
                partial=ready.with_suffix('.part')
                try:
                    await safe_download(url,partial,self.settings.video_result_max_bytes,self.media_transport)
                    await self.probe(partial,'video')
                    partial.replace(ready)
                finally:
                    partial.unlink(missing_ok=True)
            metadata=await self.probe(ready,'video')
            await self.storage.upload(result['object_key'],ready)
            await self.repository.mark_result_stored(result['id'],ready.stat().st_size,metadata['duration_seconds'])
            ready.unlink(missing_ok=True)
        await self.repository.update_task(task_id,status='completed',progress=100,error_code=None,error_message=None,completed_at=datetime.now(timezone.utc).isoformat())

    async def resume(self,user_id,task_id):
        # Existing upstream IDs remain queryable during a storage outage. Saving
        # still runs its own preflight; resume never creates another paid job.
        if await self.repository.prepare_resume(user_id,task_id,self.settings): self.schedule(user_id,task_id)
        return await self.repository.get_task(user_id,task_id,public=True)

    async def bind(self,user_id,task_id,upstream_id):
        task=await self.repository.get_task(user_id,task_id)
        if task['status'] not in ('submission_unknown','abandoned') or task['upstream_task_id']:
            raise VideoError('video_bind_invalid','只有未取得上游 ID 的不确定提交可以接管',409)
        key=(await self.repository.get_key(user_id,task['api_key_config_id']))['api_key']
        result=await self.provider.query(key,upstream_id)
        returned=result.get('id') or result.get('task_id')
        if returned!=upstream_id or result.get('model',task['model'])!=task['model']:
            raise VideoError('video_bind_invalid','上游任务 ID 或模型不匹配',422)
        await self.repository.bind_task(user_id,task_id,upstream_id)
        return await self.resume(user_id,task_id)

    async def abandon(self,user_id,task_id):
        task=await self.repository.get_task(user_id,task_id)
        if task['status']=='abandoned': return await self.repository.get_task(user_id,task_id,public=True)
        if task['status'] not in TRACKED_STATUSES:
            raise VideoError('video_abandon_invalid','此任务已结束，无需放弃追踪',409)
        job=self.jobs.get(task_id)
        if job:
            job.cancel()
            await asyncio.gather(job,return_exceptions=True)
        current=await self.repository.get_task(user_id,task_id)
        if current['status'] in ('completed','failed'): return await self.repository.get_task(user_id,task_id,public=True)
        await self.repository.update_task(task_id,status='abandoned',tracking_abandoned=1,error_code='video_tracking_abandoned',error_message='已放弃本地追踪；不会取消上游任务或触发退款')
        return await self.repository.get_task(user_id,task_id,public=True)

    async def history_image(self,user_id,history_repository,history_id,image_id,name=''):
        if not self.assets.ready: raise VideoError('video_assets_unconfigured','已有图片引用需要公网 HTTPS 素材配置',503)
        image=await history_repository.get_image(user_id,history_id,image_id)
        if image is None: raise VideoError('video_image_not_found','图片不存在',404)
        upload=UploadFile(filename=image.filename or 'reference.png',file=io.BytesIO(image.data))
        return await self.assets.ingest(user_id,'image',upload,name)

    async def recover(self):
        rows=await self.repository.rows("SELECT * FROM video_tasks WHERE status IN ('queued','submitting','running','saving') AND tracking_abandoned=0")
        for task in rows:
            if not task['upstream_task_id'] and task['status']!='queued':
                await self.repository.update_task(task['id'],status='submission_unknown',error_code='video_worker_interrupted',error_message='服务中断时提交结果不确定，请核对控制台任务 ID，不会自动重发')
            else: self.schedule(task['user_id'],task['id'])
        paused=await self.repository.rows("SELECT * FROM video_tasks WHERE tracking_abandoned=0 AND (status='storage_failed' OR (status='polling_paused' AND error_code='video_worker_interrupted'))")
        for task in paused:
            try:
                if await self.repository.prepare_resume(task['user_id'],task['id'],self.settings): self.schedule(task['user_id'],task['id'])
            except VideoError:
                pass  # Capacity is bounded; paused history remains manually resumable.
        if self.maintenance is None:
            self.maintenance=asyncio.create_task(self.maintain(),name='video-storage-maintenance')

    async def maintain(self):
        while not self.closed:
            try:
                await self.assets.cleanup()
                if self.storage.configured:
                    for item in await self.repository.rows('SELECT * FROM video_storage_cleanup ORDER BY id LIMIT 20'):
                        try:
                            await self.storage.delete(item['object_key'])
                            await self.repository.execute('DELETE FROM video_storage_cleanup WHERE id=?',(item['id'],))
                        except Exception:
                            await self.repository.execute('UPDATE video_storage_cleanup SET attempts=attempts+1 WHERE id=?',(item['id'],))
            except Exception:
                logger.warning('Video storage maintenance deferred; will retry')
            await asyncio.sleep(60)

    async def shutdown(self):
        self.closed=True
        tasks=list(self.jobs.values())+([self.maintenance] if self.maintenance else [])
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        self.jobs.clear()
        self.maintenance=None
