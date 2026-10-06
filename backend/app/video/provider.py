import asyncio
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
import time
from urllib.parse import quote,urljoin,urlsplit
import httpx
from app.video.network import https_url
from app.video.repository import VideoError


def retry_after(value,default):
    if not value: return default
    try:
        if value.isdigit(): return max(0,float(value))
        date=parsedate_to_datetime(value)
        if date.tzinfo is None: date=date.replace(tzinfo=timezone.utc)
        return max(0,(date-datetime.now(timezone.utc)).total_seconds())
    except (ValueError,TypeError,OverflowError): return default

class UnavailableVideoProvider:
    """Keep image endpoints available when an optional video root is misconfigured."""
    def __init__(self, error):
        self.error = error

    async def unavailable(self, *args, **kwargs):
        raise self.error

    create = query = content_url = test_key = unavailable


class VideoProvider:
    def __init__(self,settings,transport=None):
        self.settings=settings
        self.base=https_url(settings.video_api_base_url).rstrip('/')
        parts=urlsplit(self.base)
        if parts.path or parts.query:
            raise VideoError('video_base_invalid','视频服务地址必须为 HTTPS 根地址，不能包含 /v1 或查询参数',503)
        self.transport=transport

    async def request(self,method,path,key,payload=None,deadline=None):
        # Each API request gets a fresh client; none is reused for CDN downloads.
        deadline = deadline if deadline is not None else time.monotonic()+120
        for attempt in range(5):
            remaining=deadline-time.monotonic()
            if remaining<=0:
                raise VideoError('video_poll_timeout','本轮查询等待已结束，请稍后恢复',504)
            try:
                async with httpx.AsyncClient(transport=self.transport,timeout=httpx.Timeout(min(60,remaining),connect=min(15,remaining)),follow_redirects=False,trust_env=False) as client:
                    async with asyncio.timeout(remaining):
                        response=await client.request(method,self.base+path,headers={'Authorization':'Bearer '+key},json=payload if method=='POST' else None)
                delay=retry_after(response.headers.get('retry-after'),max(0.1,self.settings.video_poll_interval)*(2**attempt))
                retryable=response.status_code==429 or response.status_code>=500 or (path.endswith('/content') and response.status_code==409)
                if method=='GET' and retryable and attempt<4:
                    if deadline is not None and time.monotonic()+delay>=deadline: raise VideoError('video_poll_timeout','自动等待已结束，请稍后恢复查询；上游任务可能仍在执行',504)
                    await asyncio.sleep(delay)
                    continue
                return response
            except (httpx.RequestError,TimeoutError):
                if method!='GET' or attempt==4:
                    raise VideoError('video_network','视频服务网络异常，请核对原任务，不要重复生成',502) from None
                delay=max(0.1,self.settings.video_poll_interval)*(2**attempt)
                if deadline is not None and time.monotonic()+delay>=deadline:
                    raise VideoError('video_poll_timeout','等待已结束，请恢复查询，不要重新生成',504) from None
                await asyncio.sleep(delay)
        raise VideoError('video_network','视频查询重试耗尽',502)

    @staticmethod
    def json(response):
        if response.status_code>=400:
            # Do not echo upstream request URLs, signed links or arbitrary error bodies.
            code='video_auth' if response.status_code in (401,403) else 'video_upstream_http'
            raise VideoError(code,f'视频服务返回 HTTP {response.status_code}',response.status_code if response.status_code in (400,401,403,404,422,429) else 502)
        try:
            data=response.json()
            if not isinstance(data,dict): raise ValueError()
            return data
        except ValueError:
            raise VideoError('video_response_invalid','视频服务响应格式无效',502) from None

    async def create(self,key,payload):
        response=await self.request('POST','/v1/video/generations',key,payload)
        if response.status_code>=400 and response.status_code<500:
            # Explicit rejection is different from an ambiguous timeout / 5xx.
            error=VideoError('video_submit_rejected',f'视频提交被拒绝（HTTP {response.status_code}），请检查密钥、额度和参数',response.status_code)
            raise error
        if response.status_code>=300:
            raise VideoError('video_submission_unknown','视频提交结果不确定，请核对控制台，不要自动重新生成',502)
        return self.json(response)

    async def query(self,key,task_id,deadline=None):
        return self.json(await self.request('GET','/v1/videos/tasks/'+quote(task_id,safe=''),key,deadline=deadline))

    async def content_url(self,key,task_id,deadline=None):
        path='/v1/videos/'+quote(task_id,safe='')+'/content'
        response=await self.request('GET',path,key,deadline=deadline)
        if response.status_code not in (302,307) or not response.headers.get('location'):
            self.json(response)
            raise VideoError('video_content_not_ready','视频下载入口尚未准备好，请重试保存',502)
        return https_url(urljoin(self.base+path,response.headers['location']))

    async def test_key(self,key):
        data=self.json(await self.request('GET','/v1/models',key))
        from app.video.capabilities import RULES
        return {'connected':True,'models':[item['id'] for item in data.get('data',[]) if isinstance(item,dict) and item.get('id') in RULES],'message':'已通过非付费模型查询验证；具体模型权限及额度仍以上游为准'}
