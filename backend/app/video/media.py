import asyncio
import hashlib
import hmac
import json
import math
from pathlib import Path
import shutil
import time
import warnings
from uuid import uuid4
from urllib.parse import urlencode, urlsplit
from PIL import Image, UnidentifiedImageError
from app.video.network import https_url
from app.video.repository import VideoError

LIMITS={'image':10*1024*1024,'video':100*1024*1024,'audio':20*1024*1024}

def validate_mp4(file: Path):
    # MP4 is an ISO BMFF container. Reject MOV/3GP and truncated top-level atoms,
    # rather than trusting a .mp4 name or ffprobe's shared mov/mp4 demuxer label.
    size=file.stat().st_size
    seen=set()
    with file.open('rb') as stream:
        offset=0
        while offset<size:
            if size-offset<8: raise ValueError('Truncated atom')
            stream.seek(offset)
            header=stream.read(8)
            length=int.from_bytes(header[:4],'big'); kind=header[4:8]; header_size=8
            if length==1:
                length=int.from_bytes(stream.read(8),'big'); header_size=16
            elif length==0: length=size-offset
            if length<header_size or offset+length>size: raise ValueError('Invalid atom length')
            seen.add(kind)
            if kind==b'ftyp':
                brands=stream.read(min(length-header_size,1024))
                valid={b'isom',b'iso2',b'iso3',b'iso4',b'iso5',b'iso6',b'mp41',b'mp42',b'avc1',b'dash',b'M4V '}
                if brands[:4] not in valid and not any(brands[i:i+4] in valid for i in range(8,len(brands)-3,4)):
                    raise ValueError('Not MP4')
                if brands[:4] in (b'qt  ',b'3gp4',b'3gp5',b'3gp6'): raise ValueError('Not MP4')
            offset+=length
    if not {b'ftyp',b'moov',b'mdat'}<=seen: raise ValueError('Incomplete MP4')


async def probe_media(file: Path,kind: str) -> dict:
    if kind=='video':
        try: await asyncio.to_thread(validate_mp4,file)
        except (ValueError,OSError):
            raise VideoError('video_media_invalid','文件不是完整有效的 MP4 容器',422) from None
    executable=shutil.which('ffprobe')
    if not executable:
        raise VideoError('video_probe_missing','服务器需要安装 ffprobe 才能校验媒体',503)
    # Do not permit container playlists or embedded external protocols to fetch remote resources.
    process=await asyncio.create_subprocess_exec(executable,'-v','error','-protocol_whitelist','file,pipe','-count_packets','-show_entries','format=duration,format_name:stream=codec_type,nb_read_packets','-of','json',str(file),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:
        stdout,stderr=await asyncio.wait_for(process.communicate(),30)
    except BaseException as exc:
        if process.returncode is None: process.kill()
        await process.wait()
        if isinstance(exc, asyncio.TimeoutError):
            raise VideoError('video_probe_timeout','媒体校验超时，请使用较短或较小的有效媒体文件',422) from None
        raise
    try:
        data=json.loads(stdout)
        duration=float(data['format']['duration'])
        formats=set(data['format']['format_name'].split(','))
        if process.returncode or stderr.strip() or not math.isfinite(duration) or duration<=0:
            raise ValueError()
        streams=data.get('streams',[])
        if not any(s.get('codec_type')==kind and str(s.get('nb_read_packets','')).isdigit() and int(s['nb_read_packets'])>0 for s in streams):
            raise ValueError()
        if kind=='video' and ('mp4' not in formats or not any(s.get('codec_type')=='video' for s in streams)):
            raise ValueError()
        if kind=='audio' and (not formats.intersection({'mp3','wav'}) or any(s.get('codec_type')=='video' for s in data.get('streams',[])) or not any(s.get('codec_type')=='audio' for s in data.get('streams',[]))):
            raise ValueError()
        mime='video/mp4' if kind=='video' else ('audio/mpeg' if 'mp3' in formats else 'audio/wav')
        return {'duration_seconds':duration,'mime_type':mime,'extension': 'mp4' if kind=='video' else ('mp3' if 'mp3' in formats else 'wav')}
    except (ValueError,KeyError,TypeError):
        raise VideoError('video_media_invalid','文件不是有效的 MP4 视频或 MP3/WAV 音频',422) from None


def probe_image(file):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(file) as image:
                fmt=image.format
                image.verify()
            # JPEG/GIF verify() alone does not decode pixels or catch every truncation.
            with Image.open(file) as image:
                image.load()
        types={'PNG':('image/png','png'),'JPEG':('image/jpeg','jpg'),'WEBP':('image/webp','webp'),'GIF':('image/gif','gif')}
        if fmt not in types: raise ValueError()
        mime,ext=types[fmt]
        return {'mime_type':mime,'extension':ext,'duration_seconds':None}
    except (OSError,ValueError,UnidentifiedImageError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise VideoError('video_image_invalid','参考图不是有效的 PNG/JPEG/WebP/GIF 图片',422) from None

class VideoAssets:
    def __init__(self,repository,settings,probe=probe_media):
        self.repository=repository
        self.settings=settings
        self.root=(repository.database_path.parent/'video').resolve()
        self.probe=probe

    @property
    def ready(self):
        try:
            url=https_url(self.settings.video_public_base_url)
            if urlsplit(url).query or urlsplit(url).path not in ('','/'):
                return False
            return len(self.settings.video_asset_signing_secret.get_secret_value())>=32
        except VideoError:
            return False

    def path(self,relative):
        target=(self.root/relative).resolve()
        if not target.is_relative_to(self.root) or target==self.root:
            raise VideoError('video_path_invalid','无效媒体路径',422)
        return target

    def signed_url(self,asset_id,expires=None):
        if not self.ready:
            raise VideoError('video_assets_unconfigured','请先配置公网 HTTPS 素材地址和至少 32 字符的持久化签名密钥',503)
        expires=expires or int(time.time())+86400
        secret=self.settings.video_asset_signing_secret.get_secret_value().encode()
        signature=hmac.new(secret,f'video-reference:{asset_id}:{expires}'.encode(),hashlib.sha256).hexdigest()
        return self.settings.video_public_base_url.rstrip('/')+f'/api/videos/assets/public/{asset_id}?'+urlencode({'expires':expires,'signature':signature})

    def verify_signature(self,asset_id,expires,signature):
        if not self.ready or expires<int(time.time()) or expires>int(time.time())+86400+60:
            raise VideoError('video_asset_signature','素材链接无效或已过期',403)
        expected=hmac.new(self.settings.video_asset_signing_secret.get_secret_value().encode(),f'video-reference:{asset_id}:{expires}'.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,signature):
            raise VideoError('video_asset_signature','素材签名无效',403)

    async def ingest(self,user_id,kind,upload,name=''):
        if not self.ready: raise VideoError('video_assets_unconfigured','尚未配置公网 HTTPS 素材地址',503)
        if kind not in LIMITS: raise VideoError('video_material_type','素材类型无效',422)
        asset_id=uuid4().hex
        partial=self.path(f'assets/{asset_id}.part')
        partial.parent.mkdir(parents=True,exist_ok=True)
        count=0
        try:
            with partial.open('wb') as output:
                while chunk:=await upload.read(64*1024):
                    count+=len(chunk)
                    if count>LIMITS[kind]: raise VideoError('video_file_too_large','上传素材超过本应用大小限制',413)
                    output.write(chunk)
            if not count: raise VideoError('video_file_empty','素材不能为空',422)
            meta=await asyncio.to_thread(probe_image,partial) if kind=='image' else await self.probe(partial,kind)
            filename=Path((upload.filename or f'{kind}.{meta["extension"]}').replace('\\','/')).name[:160]
            relative=f'assets/{asset_id}.{meta["extension"]}'
            target=self.path(relative)
            partial.replace(target)
            inserting=asyncio.create_task(self.repository.add_asset({'id':asset_id,'user_id':user_id,'type':kind,'name':name.strip()[:80],'filename':filename,'mime_type':meta['mime_type'],'duration_seconds':meta['duration_seconds'],'byte_size':count,'relative_path':relative}))
            try:
                await asyncio.shield(inserting)
            except asyncio.CancelledError:
                # Preserve the file if the durable insert succeeds after disconnection;
                # unreferenced uploads will be collected after their normal 24h TTL.
                await asyncio.gather(inserting,return_exceptions=True)
                raise
            except Exception:
                target.unlink(missing_ok=True)
                raise
            return await self.repository.get_asset(asset_id,user_id)
        finally:
            partial.unlink(missing_ok=True)

    async def cleanup_deleted_references(self):
        async with self.repository.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            rows=await (await db.execute("SELECT id,relative_path FROM video_assets a WHERE ever_referenced=1 AND NOT EXISTS(SELECT 1 FROM video_task_assets ta WHERE ta.asset_id=a.id)")).fetchall()
            for row in rows:
                self.path(row['relative_path']).unlink(missing_ok=True)
                await db.execute('DELETE FROM video_assets WHERE id=?',(row['id'],))
            await db.commit()

    async def cleanup(self):
        await self.cleanup_deleted_references()
        async with self.repository.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            rows=await (await db.execute("SELECT id,relative_path FROM video_assets a WHERE created_at < datetime('now','-1 day') AND NOT EXISTS(SELECT 1 FROM video_task_assets ta WHERE ta.asset_id=a.id)")).fetchall()
            for row in rows:
                self.path(row['relative_path']).unlink(missing_ok=True)
                await db.execute('DELETE FROM video_assets WHERE id=?',(row['id'],))
            await db.commit()
        # Crash leftovers and completed download staging files have a seven-day recovery window.
        if self.root.exists():
            referenced={r['relative_path'] for r in await self.repository.rows('SELECT relative_path FROM video_assets')}
            for file in self.root.rglob('*'):
                if not file.is_file() or file.is_symlink(): continue
                relative=file.relative_to(self.root).as_posix()
                if relative in referenced: continue
                ttl=86400 if relative.startswith('assets/') else 7*86400
                if file.stat().st_mtime<time.time()-ttl:
                    file.unlink(missing_ok=True)
