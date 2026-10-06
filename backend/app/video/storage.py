import asyncio
import re
import time
from app.video.repository import VideoError

class R2Storage:
    def __init__(self,settings):
        self.settings=settings
        self.client=None
        self.checked_until=0.0
        self.ok=False
        self.lock=asyncio.Lock()

    @property
    def configured(self):
        s=self.settings
        return bool(re.fullmatch('[a-fA-F0-9]{32}',s.r2_account_id) and s.r2_access_key_id.get_secret_value() and s.r2_secret_access_key.get_secret_value() and s.r2_bucket_name and re.fullmatch('[a-zA-Z0-9/_-]+',s.r2_key_prefix) and not s.r2_key_prefix.startswith('/'))

    def sdk(self):
        if not self.configured: raise VideoError('video_storage_unconfigured','管理员尚未配置 R2 私有桶',503)
        if self.client is None:
            import boto3
            from botocore.config import Config
            self.client=boto3.client('s3',endpoint_url=f'https://{self.settings.r2_account_id}.r2.cloudflarestorage.com',region_name='auto',aws_access_key_id=self.settings.r2_access_key_id.get_secret_value(),aws_secret_access_key=self.settings.r2_secret_access_key.get_secret_value(),config=Config(signature_version='s3v4',connect_timeout=10,read_timeout=60,retries={'max_attempts':2}))
        return self.client

    async def check(self,force=False):
        if not self.configured: return False
        async with self.lock:
            if not force and time.monotonic()<self.checked_until: return self.ok
            try:
                await asyncio.to_thread(self.sdk().head_bucket,Bucket=self.settings.r2_bucket_name)
                self.ok=True
            except Exception:
                self.ok=False
            self.checked_until=time.monotonic()+60
            return self.ok

    def valid_key(self,key):
        if not key.startswith(self.settings.r2_key_prefix.rstrip('/')+'/') or '..' in key:
            raise VideoError('video_storage_key','无效的存储对象键',422)

    async def upload(self,key,file):
        self.valid_key(key)
        # Shield and join in-flight SDK work so a deletion cannot race a background upload.
        async def operation():
            await asyncio.to_thread(self.sdk().upload_file,str(file),self.settings.r2_bucket_name,key,ExtraArgs={'ContentType':'video/mp4','CacheControl':'private, max-age=0'})
            info=await asyncio.to_thread(self.sdk().head_object,Bucket=self.settings.r2_bucket_name,Key=key)
            if info.get('ContentLength')!=file.stat().st_size: raise ValueError('Stored size mismatch')
        work=asyncio.create_task(operation())
        try:
            await asyncio.shield(work)
        except asyncio.CancelledError:
            await asyncio.gather(work,return_exceptions=True)
            raise

    def playback_url(self,key):
        self.valid_key(key)
        return self.sdk().generate_presigned_url('get_object',Params={'Bucket':self.settings.r2_bucket_name,'Key':key},ExpiresIn=600)

    async def open_download(self,key,range_header=None):
        self.valid_key(key)
        args={'Bucket':self.settings.r2_bucket_name,'Key':key}
        if range_header: args['Range']=range_header
        work=asyncio.create_task(asyncio.to_thread(self.sdk().get_object,**args))
        try:
            return await asyncio.shield(work)
        except asyncio.CancelledError:
            # The SDK call cannot be cancelled once its thread starts. Join it and
            # close the newly created body even when no streaming response exists.
            try:
                response=await work
            except Exception:
                pass
            else:
                await asyncio.to_thread(response["Body"].close)
            raise

    async def delete(self,key):
        self.valid_key(key)
        await asyncio.to_thread(self.sdk().delete_object,Bucket=self.settings.r2_bucket_name,Key=key)
