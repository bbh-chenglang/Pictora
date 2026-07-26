# Generation Timeout and Error Handling Design

## Goal

Allow slow image generation to run for three minutes per requested image and prevent empty proxy responses from surfacing as JSON parsing errors.

## Behavior

- Backend generation timeout becomes `generated image count * 180 seconds`.
- A request for up to four images can run for up to 720 seconds.
- Nginx waits 780 seconds for API response data, leaving a one-minute margin over the backend limit.
- The frontend reads the response body as text and parses JSON only when content exists and is valid.
- Empty or non-JSON failed responses show `生成失败（HTTP <status>）`.
- A successful response with invalid JSON shows `服务返回了无效响应`.
- Existing structured provider errors continue through `readableError` unchanged.

## Testing

- Backend unit test captures the timeout passed to `asyncio.timeout` and expects 540 seconds for three images.
- Frontend component test returns an empty HTTP 504 response and expects a stable Chinese error message.
- Full backend tests, frontend tests, frontend production build, and Compose validation run before publication.
