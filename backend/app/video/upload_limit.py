"""Bound multipart input while receiving it, independently of image endpoints."""
from urllib.parse import parse_qs
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from app.video.media import LIMITS


class VideoUploadLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path') != '/api/videos/assets/upload':
            return await self.app(scope, receive, send)
        kind = parse_qs(scope.get('query_string', b'').decode('ascii', errors='ignore')).get('type', ['video'])[0]
        limit = LIMITS.get(kind, LIMITS['video']) + 1024 * 1024
        headers = dict(scope.get('headers', []))
        length = headers.get(b'content-length', b'')
        if length.isdigit() and int(length) > limit:
            return await JSONResponse({'error': {'code': 'video_file_too_large', 'message': '上传超过本应用文件大小限制'}}, status_code=413)(scope, receive, send)
        total = 0
        async def limited_receive():
            nonlocal total
            message = await receive()
            if message['type'] == 'http.request':
                total += len(message.get('body', b''))
                if total > limit:
                    raise HTTPException(413, {'error': {'code': 'video_file_too_large', 'message': '上传超过本应用文件大小限制'}})
            return message
        await self.app(scope, limited_receive, send)
