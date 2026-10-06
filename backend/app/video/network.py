import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit
import httpcore
import httpx
from app.video.repository import VideoError


def https_url(value: str) -> str:
    try:
        parsed=urlsplit(value)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None,443):
            raise ValueError()
        if parsed.hostname.rstrip('.').lower() in ('localhost','localhost.localdomain'):
            raise ValueError()
        try:
            address=ipaddress.ip_address(parsed.hostname)
        except ValueError:
            pass
        else:
            if not address.is_global: raise ValueError()
    except (ValueError,TypeError):
        raise VideoError('video_url_invalid','素材或结果地址必须是公网 HTTPS 地址，不能包含凭据、片段或自定义端口',422) from None
    return value

class PublicNetworkBackend(httpcore.AsyncNetworkBackend):
    """Resolve, validate and pin the TCP destination; TLS still verifies the original host."""
    def __init__(self):
        self.backend=httpcore.AnyIOBackend()

    async def connect_tcp(self,host,port,timeout=None,local_address=None,socket_options=None):
        if isinstance(host,bytes): host=host.decode('ascii')
        records=await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host,port,type=socket.SOCK_STREAM),min(timeout or 10,10))
        addresses=list(dict.fromkeys(r[4][0] for r in records))
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise VideoError('video_url_private','素材或结果地址解析到非公网地址',422)
        last=None
        for address in addresses:
            try:
                return await self.backend.connect_tcp(address,port,timeout,local_address,socket_options)
            except (OSError,httpcore.ConnectError,httpcore.ConnectTimeout) as exc: last=exc
        raise last or httpcore.ConnectError('Unable to connect')

    async def connect_unix_socket(self,*args,**kwargs):
        raise VideoError('video_url_private','禁止本地套接字',422)

    async def sleep(self,seconds):
        await asyncio.sleep(seconds)

class PublicHTTPTransport(httpx.AsyncHTTPTransport):
    def __init__(self):
        super().__init__(trust_env=False,retries=0)
        # httpx 0.28's pool accepts a custom httpcore network backend.
        self._pool._network_backend=PublicNetworkBackend()

async def safe_download(url,destination,max_bytes,transport=None):
    async with asyncio.timeout(180):
        return await _safe_download(url,destination,max_bytes,transport)


async def _safe_download(url,destination,max_bytes,transport=None):
    url=https_url(url)
    try:
        async with httpx.AsyncClient(transport=transport or PublicHTTPTransport(),timeout=httpx.Timeout(120,connect=15),follow_redirects=False,trust_env=False,headers={'Accept-Encoding':'identity'}) as client:
            for _ in range(6):
                # No shared API session, Authorization, Cookie, or automatic redirects.
                client.cookies.clear()
                async with client.stream('GET',url) as response:
                    if response.status_code in (301,302,303,307,308):
                        if not response.headers.get('location'): raise VideoError('video_download_redirect','下载跳转缺少地址',502)
                        url=https_url(urljoin(url,response.headers['location']))
                        continue
                    response.raise_for_status()
                    length=response.headers.get('content-length')
                    if length is not None and (not length.isdigit() or int(length)>max_bytes):
                        raise VideoError('video_file_too_large','媒体超过本应用的文件大小限制',413)
                    count=0
                    with destination.open('wb') as output:
                        async for chunk in response.aiter_bytes():
                            count+=len(chunk)
                            if count>max_bytes: raise VideoError('video_file_too_large','媒体超过本应用的文件大小限制',413)
                            output.write(chunk)
                    if not count or (length is not None and count!=int(length)):
                        raise VideoError('video_download_incomplete','媒体下载不完整',502)
                    return count
            raise VideoError('video_download_redirect','下载重定向次数过多',502)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
