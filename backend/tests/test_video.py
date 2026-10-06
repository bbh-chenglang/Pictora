"""All video acceptance tests use a fake vendor and a fake R2, never paid APIs."""
import asyncio
import io
import json
import logging
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import aiosqlite
import httpx
import pytest
import pytest_asyncio
from fastapi import UploadFile
from PIL import Image
from pydantic import ValidationError

from app.config import Settings
from app.database import initialize_database
from app.dependencies import get_current_user, get_history_repository, get_video_service
from app.main import app
from app.repositories.admin_repository import AdminRepository
from app.repositories.history_repository import HistoryRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.auth import StoredSessionUser
from app.video.capabilities import RULES, VideoCatalog, bundled_models
from app.video.logging import VideoURLFilter
from app.video.media import LIMITS, probe_image, validate_mp4
from app.video.network import PublicNetworkBackend, https_url, safe_download
from app.video.provider import VideoProvider, retry_after
from app.video.repository import VideoError, VideoRepository
from app.video.schemas import VideoTaskCreate, VideoKeyUpdate
from app.video.service import VideoService
from app.video.storage import R2Storage


class FakeStorage:
    configured = True
    def __init__(self):
        self.ok = True
        self.objects = {}
        self.uploads = 0
        self.fail_uploads = 0
        self.fail_deletes = 0
        self.closed_bodies = []
    async def check(self, force=False): return self.ok
    async def upload(self, key, file):
        self.uploads += 1
        if self.fail_uploads:
            self.fail_uploads -= 1
            raise RuntimeError('Simulated R2 outage')
        self.objects[key] = file.read_bytes()
    async def delete(self, key):
        if self.fail_deletes:
            self.fail_deletes -= 1
            raise RuntimeError('Simulated deletion outage')
        self.objects.pop(key, None)
    def playback_url(self, key): return 'https://r2.example/' + key + '?expires=600'
    async def open_download(self, key, range_header=None):
        data = self.objects[key]
        start, end = 0, len(data)-1
        if range_header:
            value=range_header.removeprefix('bytes=')
            left,right=value.split('-')
            start=int(left) if left else max(0,len(data)-int(right))
            end=min(int(right),len(data)-1) if left and right else len(data)-1
            if start>end:
                error=RuntimeError(); error.response={'Error':{'Code':'InvalidRange'}}; raise error
        body=io.BytesIO(data[start:end+1]); self.closed_bodies.append(body)
        result={'Body':body,'ContentLength':end-start+1}
        if range_header: result['ContentRange']=f'bytes {start}-{end}/{len(data)}'
        return result


class FakeProvider:
    def __init__(self):
        self.posts=[]; self.queries=[]; self.downloads=[]
        self.create_error=None; self.query_error=None; self.status='completed'
        self.block=None
    async def create(self,key,payload):
        self.posts.append(payload)
        public_id = 'remote-'+str(len(self.posts))
        if self.block: await self.block.wait()
        if self.create_error: raise self.create_error
        return {'id':public_id, 'status':'queued'}
    async def query(self,key,task_id,deadline=None):
        self.queries.append(task_id)
        if self.query_error: raise self.query_error
        return {'id':task_id,'model':'sd-2.0-J2','status':self.status,'progress':50}
    async def content_url(self,key,task_id,deadline=None):
        self.downloads.append(task_id)
        return 'https://cdn.example/movie.mp4'
    async def test_key(self,key): return {'connected':True,'models':['sd-2.0-J2'],'message':'non-paid model query'}


async def fake_probe(file, kind):
    assert file.is_file() and file.stat().st_size
    return {'duration_seconds': 5.0, 'mime_type':'video/mp4' if kind=='video' else 'audio/wav', 'extension':'mp4' if kind=='video' else 'wav'}


def snapshot_catalog():
    catalog=VideoCatalog('https://api.beibeihai.xyz')
    catalog.expires=float('inf')
    return catalog


@pytest_asyncio.fixture
async def context(tmp_path):
    db=tmp_path/'video.db'
    await initialize_database(db)
    repository=VideoRepository(db)
    for user in ('alice','bob'):
        await repository.execute('INSERT INTO users(username,email,password_hash) VALUES(?,?,?)',(user,user+'@example.com','test-hash'))
    key=await repository.save_key(1,'Video','secret-video-key','sd-2.0-J2')
    project=(await repository.rows('SELECT id FROM projects WHERE user_id=1'))[0]['id']
    settings=Settings(_env_file=None,video_public_base_url='https://assets.example',video_asset_signing_secret='s'*40,video_poll_interval=0.001,video_max_wait=0.1)
    provider=FakeProvider(); storage=FakeStorage(); media=[]
    def download(request):
        assert 'authorization' not in request.headers and 'cookie' not in request.headers
        media.append(str(request.url))
        return httpx.Response(200,content=b'mock-video-data')
    service=VideoService(repository,settings,storage=storage,provider=provider,catalog=snapshot_catalog(),probe=fake_probe,media_transport=httpx.MockTransport(download))
    state=SimpleNamespace(repository=repository,service=service,provider=provider,storage=storage,project=project,key=key['id'],settings=settings,media=media,db=db)
    yield state
    await service.shutdown()


def request(context,**overrides):
    return VideoTaskCreate.model_validate({'request_id':str(uuid4()),'project_id':context.project,'api_key_config_id':context.key,'prompt':'cinematic scene',**overrides})


async def drain(service):
    while service.jobs:
        await asyncio.gather(*list(service.jobs.values()),return_exceptions=True)
        await asyncio.sleep(0)


def png():
    file=io.BytesIO(); Image.new('RGB',(2,2),'red').save(file,format='PNG'); return file.getvalue()


@pytest.mark.parametrize('model_id',list(RULES))
@pytest.mark.asyncio
async def test_every_model_parameter_combination_and_defaults(model_id):
    catalog=snapshot_catalog(); model=next(m for m in bundled_models() if m['id']==model_id)
    for resolution,durations in model['durations_by_resolution'].items():
        for duration in durations:
            for ratio in model['ratios']:
                req=SimpleNamespace(model=model_id,prompt='prompt',duration=duration,resolution=resolution,ratio=ratio)
                payload=await catalog.normalize(req,[])
                assert set(payload)=={'model','prompt','duration','resolution','ratio'}
        for invalid in (0, max(durations)+1, 11 if model_id=='sd-2.0-900-J3' else min(durations)-1):
            with pytest.raises(VideoError): await catalog.normalize(SimpleNamespace(model=model_id,prompt='x',duration=invalid,resolution=resolution,ratio=model['default_ratio']),[])
    default=await catalog.normalize(SimpleNamespace(model=model_id,prompt='x',duration=None,resolution=None,ratio=None),[])
    assert (default['duration'],default['resolution'],default['ratio'])==(model['default_duration'],model['default_resolution'],model['default_ratio'])


@pytest.mark.parametrize('model_id',list(RULES))
@pytest.mark.asyncio
async def test_every_model_reference_limits(model_id):
    catalog=snapshot_catalog(); model=next(m for m in bundled_models() if m['id']==model_id)
    req=SimpleNamespace(model=model_id,prompt='x',duration=None,resolution=None,ratio=None)
    for kind,limit in model['reference_limits'].items():
        materials=[{'type':kind,'name':f'm{i}','url':f'https://cdn.example/{i}','duration_seconds':0.1} for i in range((limit or 0)+1)]
        with pytest.raises(VideoError): await catalog.normalize(req,materials)
        if limit:
            valid=materials[:limit]
            if model_id=='minimax-h3': valid=valid[:min(limit,10)]
            assert await catalog.normalize(req,valid)


@pytest.mark.asyncio
async def test_catalog_uses_live_discrete_tiers_and_preserves_verified_on_failure():
    calls=[]
    def respond(req):
        calls.append(req)
        if len(calls)>1: return httpx.Response(503)
        return httpx.Response(200,json={'data':[{'model_name':'sd-2.0-J2','video_pricing':{'default_duration':10,'default_resolution':'1080p','default_ratio':'1:1','ratios':['1:1'],'tiers':[{'duration':10,'resolution':'1080p'},{'duration':15,'resolution':'1080p'}]}}]})
    catalog=VideoCatalog('https://api.beibeihai.xyz',httpx.MockTransport(respond))
    model=(await catalog.get())[0]; assert model['default_resolution']=='1080p' and model['durations_by_resolution']=={'1080p':[10,15]}
    catalog.expires=0
    assert (await catalog.get())[0]==model


@pytest.mark.parametrize('value',[0,-1,1.5,True,'5'])
def test_duration_is_a_positive_json_integer(value):
    with pytest.raises(ValidationError): VideoTaskCreate.model_validate({'request_id':str(uuid4()),'project_id':1,'api_key_config_id':1,'prompt':'x','duration':value})


def test_extra_fields_and_empty_update_key_rejected():
    with pytest.raises(ValidationError): VideoTaskCreate.model_validate({'request_id':str(uuid4()),'project_id':1,'api_key_config_id':1,'prompt':'x','n':2})
    with pytest.raises(ValidationError): VideoKeyUpdate(api_key='   ')


@pytest.mark.asyncio
async def test_success_persistence_idempotency_and_private_storage(context):
    req=request(context)
    first=await context.service.create(1,req)
    second=await context.service.create(1,req)
    await drain(context.service)
    assert first['id']==second['id'] and len(context.provider.posts)==1
    task=await context.repository.get_task(1,first['id'],public=True)
    assert task['status']=='completed' and task['upstream_status']=='completed'
    assert task['results'][0]['stored']==1 and 'object_key' not in task['results'][0]
    assert len(context.storage.objects)==1 and context.media
    altered=req.model_copy(update={'prompt':'changed'})
    with pytest.raises(VideoError,match='请求'): await context.service.create(1,altered)


@pytest.mark.asyncio
async def test_concurrent_duplicate_request_posts_only_once(context):
    req=request(context)
    tasks=await asyncio.gather(*(context.service.create(1,req) for _ in range(4)))
    await drain(context.service)
    assert len({t['id'] for t in tasks})==1 and len(context.provider.posts)==1


@pytest.mark.parametrize('code,expected',[('video_submission_unknown','submission_unknown'),('video_submit_rejected','failed'),('video_network','submission_unknown')])
@pytest.mark.asyncio
async def test_ambiguous_post_never_replayed(context,code,expected):
    context.provider.create_error=VideoError(code,'simulated timeout',502)
    task=await context.service.create(1,request(context)); await drain(context.service)
    assert (await context.repository.get_task(1,task['id']))['status']==expected
    await context.service.recover(); await drain(context.service)
    assert len(context.provider.posts)==1


@pytest.mark.asyncio
async def test_restart_submission_without_id_remains_unknown(context):
    context.service.schedule=lambda *_:None
    task=await context.service.create(1,request(context))
    await context.repository.claim_submission(task['id'])
    replacement=VideoService(context.repository,context.settings,storage=context.storage,provider=context.provider,catalog=snapshot_catalog(),probe=fake_probe)
    try:
        await replacement.recover()
        assert (await context.repository.get_task(1,task['id']))['status']=='submission_unknown'
        assert not context.provider.posts
    finally: await replacement.shutdown()


@pytest.mark.asyncio
async def test_restart_known_id_resumes_without_post(context):
    context.service.schedule=lambda *_:None
    task=await context.service.create(1,request(context))
    await context.repository.update_task(task['id'],status='running',upstream_task_id='remote-recovered')
    replacement=VideoService(context.repository,context.settings,storage=context.storage,provider=context.provider,catalog=snapshot_catalog(),probe=fake_probe,media_transport=context.service.media_transport)
    try:
        await replacement.recover(); await drain(replacement)
        assert (await context.repository.get_task(1,task['id']))['status']=='completed' and not context.provider.posts
    finally: await replacement.shutdown()


@pytest.mark.parametrize('upstream,expected',[('failed','failed'),('unknown','polling_paused'),('queued','polling_paused'),('in_progress','polling_paused'),('unrecognized','polling_paused')])
@pytest.mark.asyncio
async def test_statuses_and_wait_timeout_do_not_claim_cancellation(context,upstream,expected):
    context.provider.status=upstream
    task=await context.service.create(1,request(context)); await drain(context.service)
    saved=await context.repository.get_task(1,task['id'])
    assert saved['status']==expected and saved['upstream_status']==upstream
    if expected=='polling_paused':
        assert saved['upstream_task_id'] and not saved['completed_at']
        context.provider.status='completed'
        await context.service.resume(1,task['id']); await drain(context.service)
        assert len(context.provider.posts)==1


@pytest.mark.asyncio
async def test_storage_retry_never_regenerates_and_uses_staging(context):
    context.storage.fail_uploads=1
    task=await context.service.create(1,request(context)); await drain(context.service)
    saved=await context.repository.get_task(1,task['id'])
    assert saved['status']=='storage_failed' and saved['upstream_status']=='completed'
    reads=len(context.media); queries=len(context.provider.queries)
    await context.service.resume(1,task['id']); await drain(context.service)
    assert (await context.repository.get_task(1,task['id']))['status']=='completed'
    assert len(context.provider.posts)==1 and len(context.media)==reads and len(context.provider.queries)==queries


@pytest.mark.asyncio
async def test_missing_r2_or_media_tools_blocks_before_persist_or_post(context,monkeypatch):
    context.storage.ok=False
    with pytest.raises(VideoError,match='R2'): await context.service.create(1,request(context))
    assert not context.provider.posts and not await context.repository.rows('SELECT 1 FROM video_tasks')
    context.storage.ok=True
    from app.video.media import probe_media
    context.service.probe=probe_media
    monkeypatch.setattr('app.video.service.shutil.which',lambda _:None)
    with pytest.raises(VideoError,match='ffprobe'): await context.service.create(1,request(context))


@pytest.mark.asyncio
async def test_https_gate_only_blocks_local_assets(context):
    context.settings.video_public_base_url=''
    with pytest.raises(VideoError): await context.service.assets.ingest(1,'image',UploadFile(file=io.BytesIO(png()),filename='x.png'))
    task=await context.service.create(1,request(context,materials=[{'type':'image','name':'subject','url':'https://cdn.example/subject.png'}]))
    await drain(context.service)
    assert context.provider.posts[0]['images'][0]['name']=='subject'


@pytest.mark.asyncio
async def test_material_snapshot_signatures_ownership_and_reference_cleanup(context):
    asset=await context.service.assets.ingest(1,'image',UploadFile(file=io.BytesIO(png()),filename='../../subject.png'))
    assert asset['filename']=='subject.png'
    url=context.service.assets.signed_url(asset['id']); parts=parse_qs(urlsplit(url).query)
    context.service.assets.verify_signature(asset['id'],int(parts['expires'][0]),parts['signature'][0])
    for expires,signature in [(int(time.time())-1,parts['signature'][0]),(int(parts['expires'][0]),'0'*64)]:
        with pytest.raises(VideoError): context.service.assets.verify_signature(asset['id'],expires,signature)
    with pytest.raises(VideoError): await context.repository.get_asset(asset['id'],2)
    task=await context.service.create(1,request(context,materials=[{'type':'image','asset_id':asset['id'],'name':'subject'}])); await drain(context.service)
    payload=context.provider.posts[0]; assert set(payload['images'][0])=={'url','name'} and 'multipart' not in payload
    assert 'signature=' in payload['images'][0]['url']
    await context.repository.delete_task(1,task['id']); await context.service.assets.cleanup_deleted_references()
    with pytest.raises(VideoError): await context.repository.get_asset(asset['id'],1)
    assert not context.service.assets.path(asset['relative_path']).exists()
    cleanup=await context.repository.rows('SELECT * FROM video_storage_cleanup'); assert len(cleanup)==1


@pytest.mark.asyncio
async def test_media_validation_limits_and_unreferenced_24_hour_cleanup(context,monkeypatch):
    bad=context.service.assets.path('bad.png'); bad.parent.mkdir(parents=True,exist_ok=True); bad.write_bytes(b'not a PNG')
    with pytest.raises(VideoError): probe_image(bad)
    monkeypatch.setitem(LIMITS,'image',8)
    with pytest.raises(VideoError) as err: await context.service.assets.ingest(1,'image',UploadFile(file=io.BytesIO(png()),filename='x.png'))
    assert err.value.status==413
    monkeypatch.setitem(LIMITS,'image',10*1024*1024)
    asset=await context.service.assets.ingest(1,'image',UploadFile(file=io.BytesIO(png()),filename='x.png'))
    await context.repository.execute("UPDATE video_assets SET created_at=datetime('now','-25 hours') WHERE id=?",(asset['id'],))
    await context.service.assets.cleanup()
    assert not context.service.assets.path(asset['relative_path']).exists()


@pytest.mark.asyncio
async def test_minimax_server_probes_actual_reference_duration(context):
    count=[]
    async def probe(file,kind): count.append(file); return {'duration_seconds':16,'mime_type':'video/mp4','extension':'mp4'}
    context.service.probe=probe
    with pytest.raises(VideoError,match='15'): await context.service.create(1,request(context,model='minimax-h3',materials=[{'type':'video','url':'https://cdn.example/ref.mp4','name':'motion'}]))
    assert len(count)==1 and not context.provider.posts
    assert not list(context.service.assets.path('probe/x').parent.glob('*.mp4'))


@pytest.mark.asyncio
async def test_minimax_combined_count_and_duplicate_names():
    catalog=snapshot_catalog(); req=SimpleNamespace(model='minimax-h3',prompt='x',duration=None,resolution=None,ratio=None)
    items=[{'type':'image','url':f'https://cdn.example/{i}','name':str(i)} for i in range(9)]+[{'type':'audio','url':f'https://cdn.example/a{i}','name':'a'+str(i)} for i in range(2)]
    with pytest.raises(VideoError,match='10'): await catalog.normalize(req,items)
    with pytest.raises(VideoError,match='名称'): await catalog.normalize(req,[items[0],items[1]|{'name':'0'}])


@pytest.mark.asyncio
async def test_user_and_global_capacity_are_persisted(context):
    context.provider.block=asyncio.Event()
    for _ in range(2): await context.service.create(1,request(context))
    with pytest.raises(VideoError) as err: await context.service.create(1,request(context))
    assert err.value.status==429
    context.settings.video_max_active_tasks=2
    other_key=await context.repository.save_key(2,'Video','bob-key','sd-2.0-J2')
    other_project=(await context.repository.rows('SELECT id FROM projects WHERE user_id=2'))[0]['id']
    with pytest.raises(VideoError): await context.service.create(2,request(context,project_id=other_project,api_key_config_id=other_key['id']))
    context.provider.block.set(); await drain(context.service)


@pytest.mark.asyncio
async def test_tracked_key_and_project_deletion_protected_and_explicit_abandon(context):
    context.provider.status='unknown'
    task=await context.service.create(1,request(context)); await drain(context.service)
    with pytest.raises(VideoError): await context.repository.delete_key(1,context.key)
    with pytest.raises(VideoError): await context.repository.save_key(1,'Video','changed-key','sd-2.0-J2',context.key)
    with pytest.raises(VideoError): await context.repository.delete_task(1,task['id'])
    with pytest.raises(aiosqlite.IntegrityError,match='video_project_tracking'): await ProjectRepository(context.db).delete(context.project,1)
    saved=await context.service.abandon(1,task['id']); assert saved['tracking_abandoned'] and '不会取消' in saved['error_message']
    await context.repository.delete_key(1,context.key)
    await ProjectRepository(context.db).delete(context.project,1)


@pytest.mark.asyncio
async def test_manual_binding_checks_key_ownership_and_atomic_duplicate_protection(context):
    context.provider.create_error=VideoError('video_submission_unknown','timeout')
    first=await context.service.create(1,request(context)); await drain(context.service)
    context.provider.create_error=None
    task=await context.service.bind(1,first['id'],'verified-id'); await drain(context.service)
    assert (await context.repository.get_task(1,task['id']))['status']=='completed'
    assert len(context.provider.posts)==1
    second=await context.service.create(1,request(context)); await drain(context.service)
    with pytest.raises(VideoError): await context.repository.bind_task(1,second['id'],'verified-id')
    with pytest.raises(VideoError): await context.service.bind(2,first['id'],'stolen-id')


@pytest.mark.parametrize('url',['http://example.com/a','https://localhost/a','https://127.0.0.1/a','https://10.1.1.1/a','https://169.254.169.254/a','https://[::1]/a','https://user:key@example.com/a','https://example.com:8443/a','https://example.com/a#x','file:///C:/secret'])
def test_ssrf_url_precheck(url):
    with pytest.raises(VideoError): https_url(url)


@pytest.mark.asyncio
async def test_dns_rebinding_and_mixed_private_addresses_blocked(monkeypatch):
    backend=PublicNetworkBackend(); calls=[]
    async def resolve(*args,**kwargs): return [(2,1,6,'',('93.184.216.34',443)),(2,1,6,'',('127.0.0.1',443))]
    monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',resolve)
    async def connect(*args,**kwargs): calls.append(args); return 'stream'
    monkeypatch.setattr(backend.backend,'connect_tcp',connect)
    with pytest.raises(VideoError): await backend.connect_tcp('attacker.example',443)
    assert not calls
    async def public(*args,**kwargs): return [(2,1,6,'',('93.184.216.34',443))]
    monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',public)
    assert await backend.connect_tcp('public.example',443)=='stream' and calls[0][0]=='93.184.216.34'


@pytest.mark.asyncio
async def test_media_redirects_are_anonymous_and_bounded(tmp_path):
    calls=[]
    def respond(request):
        calls.append(request)
        assert 'authorization' not in request.headers and 'cookie' not in request.headers
        if len(calls)==1: return httpx.Response(302,headers={'Location':'https://other.example/file','Set-Cookie':'auth=must-not-forward'})
        return httpx.Response(200,content=b'video')
    file=tmp_path/'out.mp4'
    assert await safe_download('https://cdn.example/file',file,20,httpx.MockTransport(respond))==5
    assert len(calls)==2
    with pytest.raises(VideoError): await safe_download('https://cdn.example/file',file,20,httpx.MockTransport(lambda _:httpx.Response(302,headers={'Location':'https://127.0.0.1/private'})))
    assert not file.exists()
    with pytest.raises(VideoError): await safe_download('https://cdn.example/file',file,20,httpx.MockTransport(lambda _:httpx.Response(302,headers={'Location':'https://cdn.example/file'})))
    with pytest.raises(VideoError): await safe_download('https://cdn.example/file',file,2,httpx.MockTransport(lambda _:httpx.Response(200,content=b'longer')))


@pytest.mark.asyncio
async def test_provider_get_retries_and_post_never_retries(context):
    calls=[]
    def respond(request):
        calls.append(request)
        if request.method=='POST': return httpx.Response(503)
        if len(calls)<3: return httpx.Response(429,headers={'Retry-After':'0'})
        return httpx.Response(200,json={'id':'remote','status':'completed'})
    provider=VideoProvider(context.settings,httpx.MockTransport(respond))
    await provider.query('private-key','remote')
    assert len(calls)==3 and all(r.headers['authorization']=='Bearer private-key' for r in calls)
    with pytest.raises(VideoError): await provider.create('private-key',{'model':'sd-2.0-J2'})
    assert len([r for r in calls if r.method=='POST'])==1
    assert retry_after('0',3)==0 and retry_after('bad',3)==3
    with pytest.raises(VideoError): VideoProvider(Settings(_env_file=None,video_api_base_url='https://api.beibeihai.xyz/v1'))


@pytest.mark.asyncio
async def test_authenticated_content_get_disables_redirects(context):
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(302,headers={'Location':'https://cdn.example/video'})
    provider=VideoProvider(context.settings,httpx.MockTransport(respond))
    assert await provider.content_url('secret','remote')=='https://cdn.example/video'
    assert len(calls)==1 and calls[0].headers['authorization']=='Bearer secret'


def test_signed_urls_redacted_from_logs():
    record=logging.LogRecord('uvicorn.access',20,'',0,'%s - "%s %s HTTP/%s" %s',('a','GET','/api/videos/assets/public/a?signature=secret','1.1',200),None)
    VideoURLFilter().filter(record); assert 'secret' not in record.getMessage()
    record=logging.LogRecord('httpx',20,'',0,'HTTP Request: GET %s',('https://cdn.example/v?token=secret',),None)
    VideoURLFilter().filter(record); assert 'secret' not in record.getMessage()


def test_mp4_container_truncation_and_mov_rejected(tmp_path):
    def atom(kind,body): return (8+len(body)).to_bytes(4,'big')+kind+body
    valid=atom(b'ftyp',b'isom'+b'\0'*4+b'mp42')+atom(b'moov',b'1234')+atom(b'mdat',b'1234')
    file=tmp_path/'video.mp4'; file.write_bytes(valid); validate_mp4(file)
    file.write_bytes(valid[:-1])
    with pytest.raises(ValueError): validate_mp4(file)
    file.write_bytes(valid.replace(b'isom',b'qt  '))
    with pytest.raises(ValueError): validate_mp4(file)


@pytest.mark.asyncio
async def test_admin_video_counts_do_not_multiply_image_usage_and_project_summary(context):
    await context.repository.execute("INSERT INTO history(user_id,project_id,kind,status,prompt,provider,model,detail,image_count) VALUES(1,?,'generate','completed','private','gpt','gpt-image-1','auto',2)",(context.project,))
    task=await context.service.create(1,request(context)); await drain(context.service)
    summary=(await ProjectRepository(context.db).list_with_history(1))[0]
    assert summary.history_count==1 and summary.video_history_count==1
    admin=AdminRepository(context.db); user=await admin.get_user(1)
    assert user.usage_count==1 and user.generation_count==1 and user.video_generation_count==1
    usage=await admin.list_usage(1); assert len(usage)==2 and next(u for u in usage if u.kind=='video').image_count==0


@pytest.mark.asyncio
async def test_project_delete_queues_private_objects_durably(context):
    task=await context.service.create(1,request(context)); await drain(context.service)
    key=(await context.repository.get_task(1,task['id']))['results'][0]['object_key']
    await ProjectRepository(context.db).delete(context.project,1)
    assert not await context.repository.rows('SELECT * FROM video_results')
    assert (await context.repository.rows('SELECT * FROM video_storage_cleanup'))[0]['object_key']==key
    await initialize_database(context.db)
    assert (await context.repository.rows('SELECT * FROM video_storage_cleanup'))[0]['object_key']==key


@pytest.mark.asyncio
async def test_api_202_secret_masks_auth_signed_expiry_range_and_key_test(context):
    app.dependency_overrides[get_current_user]=lambda:StoredSessionUser(id=1,username='alice',email='alice@example.com',is_admin=False,api_key='',model='gpt-image-1')
    app.dependency_overrides[get_video_service]=lambda:context.service
    app.dependency_overrides[get_history_repository]=lambda:HistoryRepository(context.db)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            keys=(await client.get('/api/settings/video-api-keys')).json()
            assert 'secret-video-key' not in json.dumps(keys)
            assert (await client.post(f'/api/settings/video-api-keys/{context.key}/test')).json()['connected']
            assert not context.provider.posts
            response=await client.post('/api/videos/tasks',json=request(context).model_dump(mode='json'))
            assert response.status_code==202 and response.json()['status_url']
            task_id=response.json()['task_id']; await drain(context.service)
            task=(await client.get(f'/api/videos/tasks/{task_id}')).json(); result=task['results'][0]
            play=await client.get(result['play_url']); assert play.status_code==307 and 'expires=600' in play.headers['location']
            download=await client.get(result['download_url'],headers={'Range':'bytes=0-3'})
            assert download.status_code==206 and download.content==b'mock'
            assert 'pictora-' in download.headers['content-disposition'] and context.storage.closed_bodies[-1].closed
            assert (await client.get(result['download_url'],headers={'Range':'bytes=1-3,4-5'})).status_code==416
            assert (await client.post(f'/api/videos/tasks/{task_id}/abandon')).status_code==409
            app.dependency_overrides[get_current_user]=lambda:StoredSessionUser(id=2,username='bob',email='bob@example.com',is_admin=False,api_key='',model='gpt-image-1')
            assert (await client.get(result['play_url'])).status_code==404
            app.dependency_overrides.pop(get_current_user)
            assert (await client.get(result['download_url'])).status_code==401
    finally: app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_snapshot_is_independent_of_original_history_and_public_route(context):
    history=await context.repository.execute("INSERT INTO history(user_id,project_id,kind,status,prompt,provider,model,detail) VALUES(1,?,'generate','completed','x','gpt','gpt-image-1','auto')",(context.project,))
    image=await context.repository.execute("INSERT INTO history_images(history_id,role,mime_type,filename,position,data) VALUES(?,'generated','image/png','x.png',0,?)",(history,png()))
    asset=await context.service.history_image(1,HistoryRepository(context.db),history,image)
    await context.repository.execute('DELETE FROM history WHERE id=?',(history,))
    assert context.service.assets.path(asset['relative_path']).read_bytes()==png()
    app.dependency_overrides[get_video_service]=lambda:context.service
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            parts=urlsplit(context.service.assets.signed_url(asset['id']))
            assert (await client.get(parts.path+'?'+parts.query)).content==png()
            assert (await client.get(parts.path+'?expires=1&signature='+'0'*64)).status_code==403
            assert (await client.get(f"/api/videos/assets/{asset['id']}/file")).status_code==401
    finally: app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_r2_mock_sdk_presigning_and_failed_head_caches(context,tmp_path):
    from unittest.mock import Mock
    settings=Settings(_env_file=None,r2_account_id='a'*32,r2_access_key_id='access',r2_secret_access_key='secret',r2_bucket_name='private')
    storage=R2Storage(settings); sdk=Mock(); storage.client=sdk
    sdk.head_bucket.side_effect=RuntimeError('offline')
    assert not await storage.check() and not await storage.check() and sdk.head_bucket.call_count==1
    sdk.head_bucket.side_effect=None; assert await storage.check(force=True)
    sdk.generate_presigned_url.return_value='https://private.example/presigned'
    assert storage.playback_url('pictora/videos/1/1/a.mp4')=='https://private.example/presigned'
    assert sdk.generate_presigned_url.call_args.kwargs['ExpiresIn']==600
    with pytest.raises(VideoError): storage.playback_url('../escape')
    file=tmp_path/'result'; file.write_bytes(b'media'); sdk.head_object.return_value={'ContentLength':5}
    await storage.upload('pictora/videos/1/1/a.mp4',file)
    assert sdk.upload_file.call_count==1


@pytest.mark.asyncio
async def test_version_17_upgrade_preserves_images_and_repeat_install(context):
    async with aiosqlite.connect(context.db) as db:
        await db.execute('PRAGMA user_version=17'); await db.commit()
    await initialize_database(context.db); await initialize_database(context.db)
    async with aiosqlite.connect(context.db) as db:
        assert (await (await db.execute('PRAGMA user_version')).fetchone())[0]==18
        assert (await (await db.execute('SELECT COUNT(*) FROM users')).fetchone())[0]==2
        assert (await (await db.execute('SELECT COUNT(*) FROM video_api_key_configs')).fetchone())[0]==1
        assert not await (await db.execute('PRAGMA foreign_key_check')).fetchall()


@pytest.mark.asyncio
async def test_resume_queries_existing_id_during_storage_outage(context):
    context.provider.status='unknown'
    task=await context.service.create(1,request(context)); await drain(context.service)
    before=len(context.provider.queries)
    context.storage.ok=False
    context.provider.status='completed'
    await context.service.resume(1,task['id']); await drain(context.service)
    saved=await context.repository.get_task(1,task['id'])
    assert len(context.provider.queries)>before
    assert saved['upstream_status']=='completed' and saved['status']=='storage_failed'
    assert len(context.provider.posts)==1
    context.storage.ok=True
    await context.service.resume(1,task['id']); await drain(context.service)
    assert (await context.repository.get_task(1,task['id']))['status']=='completed'
    assert len(context.provider.posts)==1


@pytest.mark.asyncio
async def test_optional_bad_video_root_does_not_break_service_initialization(context):
    settings=context.settings.model_copy(update={'video_api_base_url':'https://api.beibeihai.xyz/v1'})
    service=VideoService(context.repository,settings,storage=context.storage,catalog=snapshot_catalog(),probe=fake_probe)
    assert not (await service.features())['api_ready']
    with pytest.raises(VideoError,match='根地址'):
        await service.create(1,request(context))
    assert not await context.repository.rows('SELECT * FROM video_tasks')
    await service.shutdown()


@pytest.mark.asyncio
async def test_separate_video_semaphore_keeps_global_concurrency_at_two(context):
    context.provider.block=asyncio.Event()
    second_key=await context.repository.save_key(2,'Bob','secret-bob','sd-2.0-J2')
    second_project=(await context.repository.rows('SELECT id FROM projects WHERE user_id=2'))[0]['id']
    first=await context.service.create(1,request(context))
    second=await context.service.create(1,request(context))
    third=await context.service.create(2,request(context,project_id=second_project,api_key_config_id=second_key['id']))
    for _ in range(100):
        if len(context.provider.posts)==2: break
        await asyncio.sleep(0.005)
    assert len(context.service.jobs)==3 and len(context.provider.posts)==2
    assert (await context.repository.get_task(2,third['id']))['status']=='queued'
    context.provider.block.set(); await drain(context.service)
    assert len(context.provider.posts)==3
    statuses=[(await context.repository.get_task(user,task_id))['status'] for user,task_id in [(1,first['id']),(1,second['id']),(2,third['id'])]]
    assert statuses==['completed']*3


@pytest.mark.asyncio
async def test_partial_video_schema_migration_adds_retention_marker(context):
    async with aiosqlite.connect(context.db) as db:
        await db.execute('ALTER TABLE video_assets DROP COLUMN ever_referenced'); await db.commit()
    await initialize_database(context.db)
    async with aiosqlite.connect(context.db) as db:
        columns=await (await db.execute('PRAGMA table_info(video_assets)')).fetchall()
        assert 'ever_referenced' in {row[1] for row in columns}
        assert (await (await db.execute('PRAGMA user_version')).fetchone())[0]==18


@pytest.mark.asyncio
async def test_cancelled_r2_get_object_closes_body_without_streaming_response():
    import threading
    from unittest.mock import Mock
    started=threading.Event(); release=threading.Event(); body=io.BytesIO(b'media')
    def get_object(**kwargs):
        started.set(); release.wait(timeout=2)
        return {'Body':body}
    settings=Settings(_env_file=None,r2_account_id='a'*32,r2_access_key_id='access',r2_secret_access_key='secret',r2_bucket_name='private')
    storage=R2Storage(settings); storage.client=Mock(); storage.client.get_object=get_object
    downloading=asyncio.create_task(storage.open_download('pictora/videos/1/1/a.mp4'))
    assert await asyncio.to_thread(started.wait,1)
    downloading.cancel(); release.set()
    with pytest.raises(asyncio.CancelledError): await downloading
    assert body.closed


@pytest.mark.asyncio
@pytest.mark.parametrize('timeout,packets',[(True,'1'),(False,'0'),(False,'N/A'),(False,'3')])
async def test_ffprobe_timeout_and_empty_packets_are_not_trusted(tmp_path,monkeypatch,timeout,packets):
    from app.video.media import probe_media
    import app.video.media as media_module
    def atom(kind,body): return (8+len(body)).to_bytes(4,'big')+kind+body
    file=tmp_path/'test.mp4'
    file.write_bytes(atom(b'ftyp',b'isom'+b'\0'*4+b'mp42')+atom(b'moov',b'1234')+atom(b'mdat',b'1234'))
    killed=[]
    class Process:
        returncode=None if timeout else 0
        async def communicate(self):
            if timeout: raise asyncio.TimeoutError()
            return json.dumps({'format':{'duration':'5','format_name':'mov,mp4'},'streams':[{'codec_type':'video','nb_read_packets':packets}]}).encode(),b''
        def kill(self): self.returncode=-9; killed.append(True)
        async def wait(self): return self.returncode
    async def create(*args,**kwargs):
        assert '-protocol_whitelist' in args and 'file,pipe' in args and '-count_packets' in args
        return Process()
    monkeypatch.setattr(media_module.shutil,'which',lambda name:'ffprobe')
    monkeypatch.setattr(media_module.asyncio,'create_subprocess_exec',create)
    if timeout or packets in ('0','N/A'):
        with pytest.raises(VideoError) as error: await probe_media(file,'video')
        assert error.value.code==('video_probe_timeout' if timeout else 'video_media_invalid')
    else: assert (await probe_media(file,'video'))['duration_seconds']==5
    assert bool(killed)==timeout



def test_reference_jpeg_requires_real_pixel_decode(tmp_path):
    data=io.BytesIO(); Image.new('RGB',(64,64),'blue').save(data,format='JPEG')
    file=tmp_path/'photo.jpg'; file.write_bytes(data.getvalue())
    assert probe_image(file)['mime_type']=='image/jpeg'
    file.write_bytes(data.getvalue()[:-20])
    with pytest.raises(VideoError): probe_image(file)


@pytest.mark.asyncio
async def test_download_body_closed_when_response_disconnects_before_iteration():
    from app.api.videos import VideoDownloadResponse
    body=io.BytesIO(b'media')
    async def chunks(): yield body.read()
    async def receive(): return {'type':'http.disconnect'}
    async def send(message): raise RuntimeError('connection closed before headers')
    result=VideoDownloadResponse(chunks(),body,media_type='video/mp4')
    with pytest.raises(RuntimeError):
        await result({'type':'http','asgi':{'spec_version':'2.4'}},receive,send)
    assert body.closed


@pytest.mark.asyncio
async def test_invalid_optional_root_is_never_queried_or_echoed(context):
    settings=context.settings.model_copy(update={'video_api_base_url':'https://admin:private-value@api.beibeihai.xyz'})
    service=VideoService(context.repository,settings,storage=context.storage,probe=fake_probe)
    assert service.catalog.expires==float('inf')
    features=await service.features()
    assert not features['api_ready'] and features['api_base_url']==''
    assert 'private-value' not in json.dumps(features)
    assert len(await service.catalog.get())==11
    await service.shutdown()
