# 北海 AI 多模型生图 API 接入文档

> 文档版本：v2.4
>
> 更新时间：2026-09-09
>
> 适用版本：Pictora `V2`（已包含 GPT Image 2.5 与 `gemini-3-pro-image` 支持）
>
> 接口协议：OpenAI Images API 兼容格式 + Google Gemini 原生 REST API 兼容格式

本文档用于指导客户通过北海 AI 中转服务接入 GPT、Gemini 和 Grok 生图模型，包括模型查询、文生图、参考图生图、多图融合和结果解析。本文只描述客户直接调用中转服务的公开协议，不包含 Pictora 内部后台接口。

## 1. 接入信息

| 项目 | 内容 |
| --- | --- |
| 服务地址 | `https://sub.beibeihai.xyz` |
| GPT / Grok Base URL | `https://sub.beibeihai.xyz/v1` |
| Gemini Base URL | `https://sub.beibeihai.xyz/v1beta` |
| GPT / Grok 模型列表 | `GET /v1/models` |
| Gemini 模型列表 | `GET /v1beta/models` |
| GPT / Grok 文生图 | `POST /v1/images/generations` |
| GPT 参考图 | `POST /v1/images/edits`，`multipart/form-data` |
| Grok 参考图 | `POST /v1/images/edits`，JSON Data URL |
| Gemini 生图 | `POST /v1beta/models/{model}:generateContent` |
| GPT / Grok 鉴权 | `Authorization: Bearer YOUR_API_KEY` |
| Gemini 鉴权 | `x-goog-api-key: YOUR_API_KEY` |
| 请求格式 | 通常为 `application/json`；GPT 参考图为 `multipart/form-data` |
| 响应格式 | `application/json` |
| API Key 管理 | `https://sub.beibeihai.xyz/home` |

> Base URL 应按协议选择，并且只包含一次版本路径。GPT/Grok 客户端使用 `/v1`，Gemini 原生客户端使用 `/v1beta`。不要形成 `/v1/v1/...` 或 `/v1beta/v1beta/...`。

## 2. 快速接入

1. 从服务提供方获取 API Key，也可访问 [API Key 管理页面](https://sub.beibeihai.xyz/home)。
2. 使用 `/v1/models` 查询 GPT/Grok 模型，或使用 `/v1beta/models` 查询 Gemini 模型。
3. 根据模型类型选择正确协议，不要把 Gemini 请求体发送到 OpenAI Images API。
4. 发起一次最小文生图请求，再分别验证参考图、分辨率和多图等业务参数。
5. GPT/Grok 从 `data[]` 读取图片；Gemini 从 `candidates[].content.parts[]` 读取图片。

协议选择：

| 模型前缀 | 协议 | 文生图端点 | 参考图端点 | 图片返回位置 |
| --- | --- | --- | --- | --- |
| `gpt-image-*` | OpenAI Images API | `/v1/images/generations` | `/v1/images/edits` | `data[].b64_json` 或 `data[].url` |
| `gemini-*` | Gemini 原生 REST | `/v1beta/models/{model}:generateContent` | 同一端点，通过 `inlineData` 传图 | `candidates[].content.parts[]` |
| `grok-imagine-*` | OpenAI 兼容 + Grok 扩展参数 | `/v1/images/generations` | `/v1/images/edits` | `data[].b64_json` 或 `data[].url` |

GPT 最简 cURL 示例：

```bash
curl -X POST \
  "https://sub.beibeihai.xyz/v1/images/generations" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2.5-flare",
    "prompt": "一只坐在窗边的橘猫，午后自然光，写实摄影风格",
    "n": 1,
    "size": "1024x1024",
    "quality": "medium",
    "output_format": "png"
  }'
```

Gemini 最简 cURL 示例：

```bash
curl -X POST \
  "https://sub.beibeihai.xyz/v1beta/models/gemini-3-pro-image:generateContent" \
  -H "x-goog-api-key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [
      {
        "role": "user",
        "parts": [
          {"text": "一只坐在窗边的橘猫，午后自然光，写实摄影风格"}
        ]
      }
    ],
    "generationConfig": {
      "responseModalities": ["TEXT", "IMAGE"],
      "imageConfig": {
        "aspectRatio": "1:1",
        "imageSize": "1K"
      }
    }
  }'
```

Grok 最简 cURL 示例：

```bash
curl -X POST \
  "https://sub.beibeihai.xyz/v1/images/generations" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "grok-imagine-image",
    "prompt": "一只坐在窗边的橘猫，午后自然光，写实摄影风格",
    "n": 1,
    "response_format": "b64_json",
    "aspect_ratio": "1:1",
    "resolution": "1k"
  }'
```

本文分别使用 `gpt-image-2.5-flare`、`gpt-image-2.5-sunburst`、`gemini-3-pro-image` 和 `grok-imagine-image` 作为示例。中转服务的模型可能调整，客户实际可用模型必须以其 API Key 请求模型列表的返回结果为准。

## 3. API Key 鉴权

推荐将 API Key 保存在服务端环境变量中：

```bash
BEIBEIHAI_API_KEY=你的API_KEY
```

GPT 和 Grok 请求使用 Bearer 鉴权：

```http
Authorization: Bearer YOUR_API_KEY
```

Gemini 原生请求使用：

```http
x-goog-api-key: YOUR_API_KEY
```

不要把 API Key 写入浏览器前端、公开仓库、聊天截图或普通业务日志。客户端应为不同项目或环境使用独立 Key，以便控制权限、额度和停用范围。

## 4. 查询可用模型

### 4.1 GPT / Grok 模型列表

```http
GET /v1/models HTTP/1.1
Host: sub.beibeihai.xyz
Authorization: Bearer YOUR_API_KEY
```

```bash
curl "https://sub.beibeihai.xyz/v1/models" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

典型响应：

```json
{
  "object": "list",
  "data": [
    {"id": "gpt-image-2", "object": "model"},
    {"id": "gpt-image-2.5-flare", "object": "model"},
    {"id": "gpt-image-2.5-sunburst", "object": "model"},
    {"id": "grok-imagine-image", "object": "model"}
  ]
}
```

GPT Image 2.5 的两个模型定位不同：

- `gpt-image-2.5-flare`：优先速度，适合高频日常文生图。
- `gpt-image-2.5-sunburst`：优先能力和编辑精度，适合复杂生成与参考图编辑。

Pictora 不会把已有配置中的 `gpt-image-2` 自动改为 2.5。调用方应从模型列表中选择完整 ID，并在自己的业务中显式保存选择结果。

### 4.2 Gemini 模型列表

```http
GET /v1beta/models HTTP/1.1
Host: sub.beibeihai.xyz
x-goog-api-key: YOUR_API_KEY
```

对应的 cURL：

```bash
curl "https://sub.beibeihai.xyz/v1beta/models" \
  -H "x-goog-api-key: YOUR_API_KEY"
```

典型响应：

```json
{
  "models": [
    {
      "name": "models/gemini-3-pro-image",
      "displayName": "Gemini 3 Pro Image",
      "supportedGenerationMethods": ["generateContent"]
    }
  ]
}
```

> 香蕉 Pro 当前使用的模型 ID 为 `gemini-3-pro-image`。它与旧的 `gemini-3-pro-image-preview` 是两个不同的完整 ID，调用时必须使用模型列表实际返回的值，不要自行追加或删除 `-preview`。

### 4.3 模型名称处理

OpenAI 兼容模型列表通常直接返回 `data[].id`，将该值原样放入 `model` 字段。Gemini 模型名称通常带有 `models/` 前缀；拼接生成接口时只保留一个 `models/`：

```text
正确：/v1beta/models/gemini-3-pro-image:generateContent
错误：/v1beta/models/models/gemini-3-pro-image:generateContent
```

调用方可移除 Gemini 模型返回值开头的 `models/`，再放入生成接口路径。

## 5. 当前版本兼容模型

下表来自 Pictora `V2` 当前客户端能力配置，用于确定推荐参数和客户端校验上限。它不代表任意 API Key 都拥有相同权限；模型是否可调用仍以该 Key 的实时模型列表为准。

### 5.1 GPT 模型

| 模型 | 尺寸 | 质量 | 参考图上限 | 当前客户端单次数量上限 |
| --- | --- | --- | --- | --- |
| `gpt-image-2.5-sunburst` | 标准尺寸、2K/4K 预设及合规自定义尺寸 | `auto`、`low`、`medium`、`high`、`xhigh`、`max` | 16 张 | 4 张 |
| `gpt-image-2.5-flare` | 同上 | 同上 | 16 张 | 4 张 |
| `gpt-image-2` | 标准尺寸、2K/4K 预设及合规自定义尺寸 | `auto`、`low`、`medium`、`high` | 16 张 | 4 张 |
| `gpt-image-1.5` | `auto`、`1024x1024`、`1536x1024`、`1024x1536` | 同上 | 16 张 | 4 张 |
| `gpt-image-1` | 同上 | 同上 | 16 张 | 4 张 |
| `gpt-image-1-mini` | 同上 | 同上 | 16 张 | 4 张 |

GPT Image 2.5 和 `gpt-image-2` 的 Pictora 预设还包括 `2048x2048`、`2048x1152`、`1152x2048`、`3840x2160`、`2160x3840`。自定义尺寸要求宽高均为 16 的倍数、长边不超过 3840、宽高比在 1:3 至 3:1 之间，且总像素在 655360 至 8294400 之间。GPT Image 2.5 超过 `2560x1440` 的分辨率属于实验性能力。

GPT 输出格式为 `png`、`jpeg`、`webp`。GPT Image 2.5 背景支持 `auto`、`opaque`、`transparent`；`gpt-image-2` 背景支持 `auto`、`opaque`。透明背景只能搭配 PNG 或 WebP，不能搭配 JPEG。`output_compression` 仅对 JPEG/WebP 生效。

OpenAI 官方参考：[GPT Image 2.5 Flare](https://developers.openai.com/api/docs/models/gpt-image-2.5-flare)、[GPT Image 2.5 Sunburst](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst)、[Image generation 指南](https://developers.openai.com/api/docs/guides/image-generation)。

### 5.2 Gemini 模型

| 模型 | 支持的图片比例 | `imageSize` | 参考图上限 | 当前客户端单次数量上限 |
| --- | --- | --- | --- | --- |
| `gemini-3.1-flash-image` | 标准比例，以及 `1:4`、`1:8`、`4:1`、`8:1` | `1K`、`2K`、`4K` | 14 张 | 4 张 |
| `gemini-3-pro-image` | 标准比例 | `1K`、`2K`、`4K` | 14 张 | 4 张 |
| `gemini-3-pro-image-preview` | 标准比例 | `1K`、`2K`、`4K` | 14 张 | 4 张 |
| `gemini-3.1-flash-lite-image-preview` | 标准比例 | 不发送 | 14 张 | 4 张 |
| `gemini-2.5-flash-image` | 标准比例 | 不发送 | 3 张 | 4 张 |

Gemini 标准比例为 `1:1`、`2:3`、`3:2`、`3:4`、`4:3`、`4:5`、`5:4`、`9:16`、`16:9`、`21:9`。“不发送”表示当前版本不会设置 `generationConfig.imageConfig.imageSize`。

`gemini-3-pro-image` 是当前香蕉 Pro 的正式模型 ID；`gemini-3-pro-image-preview` 仅用于仍然在模型列表中返回该旧 ID 的 API Key。两者不做自动别名转换。

Gemini 原生接口没有 OpenAI Images API 的 `n` 参数。当前客户端的“单次数量”会转换为多次生成请求，不代表单个 Gemini 请求能返回指定数量。

### 5.3 Grok 模型

| 模型 | 图片比例 | 分辨率 | 质量 | 参考图上限 | 当前客户端单次数量上限 |
| --- | --- | --- | --- | --- | --- |
| `grok-imagine-image` | Grok 比例集合 | `1K`、`2K` | 不发送 | 3 张 | 4 张 |
| `grok-imagine-image-2.0` | Grok 比例集合 | `1K`、`2K` | `low`、`medium`，默认 `medium` | 3 张 | 4 张 |

Grok 比例集合为 `auto`、`1:1`、`16:9`、`9:16`、`4:3`、`3:4`、`3:2`、`2:3`、`2:1`、`1:2`、`19.5:9`、`9:19.5`、`20:9`、`9:20`。在线请求中的 `resolution` 使用小写 `1k` 或 `2k`。

## 6. GPT Image API

### 6.1 文生图

```http
POST /v1/images/generations HTTP/1.1
Host: sub.beibeihai.xyz
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

```json
{
  "model": "gpt-image-2.5-flare",
  "prompt": "极简产品摄影，白色陶瓷杯放在浅灰色摄影台中央，柔和棚拍光，无文字",
  "n": 1,
  "size": "2048x2048",
  "quality": "high",
  "output_format": "webp",
  "background": "opaque",
  "output_compression": 85,
  "moderation": "auto"
}
```

### 6.2 GPT 请求参数

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `model` | string | 是 | 当前版本登记的 GPT 模型完整 ID；推荐按场景选择 2.5 Flare 或 Sunburst |
| `prompt` | string | 是 | 生图或编辑指令 |
| `n` | integer | 否 | 图片数量；Pictora 当前限制为 1 至 4 |
| `size` | string | 否 | `auto`、预设尺寸；GPT Image 2.5 和 `gpt-image-2` 还支持合规自定义尺寸 |
| `quality` | string | 否 | 通用值为 `auto`、`low`、`medium`、`high`；仅 GPT Image 2.5 还支持 `xhigh`、`max` |
| `output_format` | string | 否 | `png`、`jpeg`、`webp` |
| `background` | string | 否 | 取值按 5.1 节模型能力设置 |
| `output_compression` | integer | 否 | JPEG/WebP 压缩质量；PNG 请求会忽略该参数 |
| `moderation` | string | 否 | `auto` 或 `low`；参考图编辑时当前客户端不发送此参数 |

### 6.3 GPT 参考图编辑

GPT 参考图使用 `multipart/form-data`。多图时重复提交 `image` 字段，当前客户端最多接收 16 张参考图。

```bash
curl -X POST \
  "https://sub.beibeihai.xyz/v1/images/edits" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "model=gpt-image-2.5-sunburst" \
  -F "prompt=保留主体结构，将背景改为冬日雪山，使用柔和自然光" \
  -F "image=@reference-1.jpg" \
  -F "image=@reference-2.png" \
  -F "n=1" \
  -F "size=2048x2048" \
  -F "quality=max" \
  -F "output_format=png" \
  -F "background=opaque"
```

### 6.4 GPT 返回结果

GPT Images API 返回 `data[]`。客户端应同时支持 Base64 和 URL，不要假设服务端只返回一种形式。

```json
{
  "created": 1787300000,
  "data": [
    {
      "b64_json": "iVBORw0KGgoAAA...",
      "revised_prompt": "优化后的提示词"
    }
  ]
}
```

存在 `b64_json` 时按 Base64 解码；存在 `url` 时及时下载并保存。文件扩展名应优先根据响应 `mime_type` 或请求的 `output_format` 确定。

## 7. Grok Image API

### 7.1 文生图

```http
POST /v1/images/generations HTTP/1.1
Host: sub.beibeihai.xyz
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

```json
{
  "model": "grok-imagine-image-2.0",
  "prompt": "雨后的上海街道，电影感摄影，霓虹灯倒影，无文字",
  "n": 1,
  "response_format": "b64_json",
  "aspect_ratio": "16:9",
  "resolution": "2k",
  "quality": "medium"
}
```

### 7.2 Grok 请求参数

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `model` | string | 是 | `grok-imagine-image` 或 `grok-imagine-image-2.0` |
| `prompt` | string | 是 | 生图或编辑指令 |
| `n` | integer | 否 | 图片数量；Pictora 当前限制为 1 至 4 |
| `response_format` | string | 是 | 当前兼容写法为 `b64_json` |
| `aspect_ratio` | string | 否 | 取值见 5.3 节；默认 `auto` |
| `resolution` | string | 否 | 在线请求使用 `1k` 或 `2k` |
| `quality` | string | 否 | 仅 `grok-imagine-image-2.0` 使用 `low` 或 `medium` |

`grok-imagine-image` 不发送 `quality`。`grok-imagine-image-2.0` 未指定质量时，当前客户端使用 `medium`。

### 7.3 Grok 参考图编辑

Grok 参考图使用 JSON Data URL，不使用 GPT 的 multipart 文件上传格式。单张参考图使用 `image`，多张参考图使用 `images` 数组，最多 3 张。

```json
{
  "model": "grok-imagine-image",
  "prompt": "以第一张图的人物为主体，穿上第二张图中的服装",
  "n": 1,
  "response_format": "b64_json",
  "aspect_ratio": "2:3",
  "resolution": "2k",
  "images": [
    {
      "url": "data:image/jpeg;base64,BASE64_OF_PERSON_IMAGE"
    },
    {
      "url": "data:image/png;base64,BASE64_OF_CLOTHES_IMAGE"
    }
  ]
}
```

请求地址仍为：

```http
POST /v1/images/edits HTTP/1.1
Host: sub.beibeihai.xyz
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

### 7.4 Grok 返回结果

Grok 与 GPT 一样从 `data[]` 返回图片。当前客户端请求 `b64_json`，但解析时仍兼容 URL：

```json
{
  "created": 1787300000,
  "data": [
    {
      "b64_json": "iVBORw0KGgoAAA..."
    }
  ]
}
```

## 8. Gemini 文生图

### 8.1 请求地址

```http
POST /v1beta/models/{model}:generateContent HTTP/1.1
Host: sub.beibeihai.xyz
x-goog-api-key: YOUR_API_KEY
Content-Type: application/json
```

### 8.2 请求体

```json
{
  "contents": [
    {
      "role": "user",
      "parts": [
        {
          "text": "一张极简产品摄影，白色陶瓷咖啡杯位于浅灰色摄影台中央，柔和棚拍光，无人物，无文字，无水印"
        }
      ]
    }
  ],
  "generationConfig": {
    "responseModalities": ["TEXT", "IMAGE"],
    "imageConfig": {
      "aspectRatio": "1:1",
      "imageSize": "1K"
    }
  }
}
```

### 8.3 主要参数

| 参数路径 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `contents` | array | 是 | 对话内容列表 |
| `contents[].role` | string | 否 | 调用方角色，通常使用 `user` |
| `contents[].parts` | array | 是 | 文本和参考图片内容 |
| `parts[].text` | string | 是 | 生图提示词 |
| `generationConfig.responseModalities` | string[] | 是 | 当前兼容写法固定为 `["TEXT", "IMAGE"]` |
| `generationConfig.imageConfig.aspectRatio` | string | 否 | 输出图片比例，具体取值取决于模型 |
| `generationConfig.imageConfig.imageSize` | string | 否 | 输出分辨率，例如 `1K`、`2K`、`4K`，具体取值取决于模型 |

当前版本统一使用 `["TEXT", "IMAGE"]`。即使业务只需要图片，也应忽略返回的文字 `part`，而不是把请求改为仅 `["IMAGE"]`；这一写法与当前 Pictora Gemini 响应兼容逻辑保持一致。

### 8.4 图片比例与分辨率

标准图片比例：

```text
1:1、2:3、3:2、3:4、4:3、4:5、5:4、9:16、16:9、21:9
```

`gemini-3.1-flash-image` 还支持更宽或更长的比例：

```text
1:4、1:8、4:1、8:1
```

支持 `imageSize` 的当前模型可使用：

```text
1K、2K、4K
```

不同 Gemini 生图模型支持的比例和分辨率不同，具体按 5.2 节的能力表设置。若模型不支持某个参数，接口通常返回 `400`；此时应调整参数或暂时移除 `imageConfig`，不要对参数错误自动重试。

## 9. Gemini 参考图生图

参考图片应作为 `parts[].inlineData` 放入 JSON 请求体。`data` 只填写纯 Base64 内容，不要包含 `data:image/png;base64,` 前缀。

```json
{
  "contents": [
    {
      "role": "user",
      "parts": [
        {
          "text": "保持人物面部、发型和服装不变，将背景改为冬日雪山，使用柔和自然光"
        },
        {
          "inlineData": {
            "mimeType": "image/jpeg",
            "data": "BASE64_ENCODED_IMAGE"
          }
        }
      ]
    }
  ],
  "generationConfig": {
    "responseModalities": ["TEXT", "IMAGE"],
    "imageConfig": {
      "aspectRatio": "16:9",
      "imageSize": "2K"
    }
  }
}
```

常用图片 MIME 类型：

- `image/png`
- `image/jpeg`
- `image/webp`

提示词应明确哪些元素需要保留、哪些元素需要修改。输入图片越大、数量越多，请求体积、处理时间和消耗通常也越高。

## 10. Gemini 多图融合

在 `parts` 中依次加入多个 `inlineData` 即可上传多张参考图。提示词中应说明每张图的用途及顺序。

```json
{
  "contents": [
    {
      "role": "user",
      "parts": [
        {
          "text": "以第一张图的人物为主体，保持面部和发型，穿上第二张图中的服装，生成自然的全身棚拍照片"
        },
        {
          "inlineData": {
            "mimeType": "image/jpeg",
            "data": "BASE64_OF_PERSON_IMAGE"
          }
        },
        {
          "inlineData": {
            "mimeType": "image/png",
            "data": "BASE64_OF_CLOTHES_IMAGE"
          }
        }
      ]
    }
  ],
  "generationConfig": {
    "responseModalities": ["TEXT", "IMAGE"],
    "imageConfig": {
      "aspectRatio": "2:3",
      "imageSize": "2K"
    }
  }
}
```

可上传的参考图数量取决于具体模型和账户权限。建议先从 1 至 2 张测试，不要假设所有模型具有相同上限。

## 11. Gemini 返回结果

Gemini 原生接口会在 `candidates[].content.parts[]` 中返回文本或图片。标准 REST 响应的图片字段为 `inlineData`；部分 SDK 或兼容层可能将其转换为 `inline_data`，客户端可同时兼容这两种字段名：

```json
{
  "candidates": [
    {
      "content": {
        "role": "model",
        "parts": [
          {
            "text": "已根据要求生成图片。"
          },
          {
            "inlineData": {
              "mimeType": "image/png",
              "data": "iVBORw0KGgoAAA..."
            }
          }
        ]
      },
      "finishReason": "STOP"
    }
  ]
}
```

调用方应遍历全部 `candidates` 和 `parts`：

- 存在 `part.text` 时，将其作为模型返回的文字内容处理。
- 存在 `part.inlineData.data` 或 `part.inline_data.data` 时，将 Base64 解码为图片。
- 使用 `mimeType`（或兼容层返回的 `mime_type`）确定文件类型，不要固定假设返回 PNG。
- 不要只读取第一个 `part`，文字和图片可能位于不同位置。

Gemini 原生生图请求没有 OpenAI Images API 的 `n` 参数。需要多张结果时，应由调用方发起多次生成请求，并自行控制并发和重试。

## 12. Gemini Python 完整示例

安装依赖：

```bash
pip install requests
```

文生图并保存全部返回图片：

```python
import base64
import os
from pathlib import Path

import requests


API_KEY = os.environ["BEIBEIHAI_API_KEY"]
MODEL = "gemini-3-pro-image"
URL = f"https://sub.beibeihai.xyz/v1beta/models/{MODEL}:generateContent"

payload = {
    "contents": [
        {
            "role": "user",
            "parts": [
                {
                    "text": "雨后的上海街道，电影感摄影，霓虹灯倒影，无文字，无水印"
                }
            ],
        }
    ],
    "generationConfig": {
        "responseModalities": ["TEXT", "IMAGE"],
        "imageConfig": {
            "aspectRatio": "16:9",
            "imageSize": "2K",
        },
    },
}

response = requests.post(
    URL,
    headers={
        "x-goog-api-key": API_KEY,
        "Content-Type": "application/json",
    },
    json=payload,
    timeout=300,
)
response.raise_for_status()
result = response.json()

extension_by_mime = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}

image_index = 0
for candidate in result.get("candidates", []):
    for part in candidate.get("content", {}).get("parts", []):
        inline_data = part.get("inlineData") or part.get("inline_data")
        if not inline_data or not inline_data.get("data"):
            continue

        mime_type = (
            inline_data.get("mimeType")
            or inline_data.get("mime_type")
            or "image/png"
        )
        extension = extension_by_mime.get(mime_type, "bin")
        image_index += 1
        output_path = Path(f"output_{image_index}.{extension}")
        output_path.write_bytes(base64.b64decode(inline_data["data"]))
        print(output_path.resolve())

if image_index == 0:
    raise RuntimeError("接口未返回图片，请检查完整响应和 finishReason")
```

添加参考图时，将图片编码后追加到 `parts`：

```python
image_base64 = base64.b64encode(Path("reference.jpg").read_bytes()).decode("ascii")

payload["contents"][0]["parts"].append(
    {
        "inlineData": {
            "mimeType": "image/jpeg",
            "data": image_base64,
        }
    }
)
```

## 13. Gemini JavaScript 完整示例

以下示例适用于 Node.js 18 及以上版本：

```javascript
import fs from "node:fs/promises";

const apiKey = process.env.BEIBEIHAI_API_KEY;
const model = "gemini-3-pro-image";
const url = `https://sub.beibeihai.xyz/v1beta/models/${model}:generateContent`;

const response = await fetch(url, {
  method: "POST",
  headers: {
    "x-goog-api-key": apiKey,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    contents: [
      {
        role: "user",
        parts: [
          {
            text: "雨后的上海街道，电影感摄影，霓虹灯倒影，无文字，无水印",
          },
        ],
      },
    ],
    generationConfig: {
      responseModalities: ["TEXT", "IMAGE"],
      imageConfig: {
        aspectRatio: "16:9",
        imageSize: "2K",
      },
    },
  }),
  signal: AbortSignal.timeout(300_000),
});

if (!response.ok) {
  throw new Error(`请求失败：${response.status} ${await response.text()}`);
}

const result = await response.json();
const extensionByMime = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/webp": "webp",
};

let imageIndex = 0;
for (const candidate of result.candidates ?? []) {
  for (const part of candidate.content?.parts ?? []) {
    const inlineData = part.inlineData ?? part.inline_data;
    if (!inlineData?.data) continue;

    imageIndex += 1;
    const mimeType = inlineData.mimeType ?? inlineData.mime_type ?? "image/png";
    const extension = extensionByMime[mimeType] ?? "bin";
    await fs.writeFile(
      `output_${imageIndex}.${extension}`,
      Buffer.from(inlineData.data, "base64"),
    );
  }
}

if (imageIndex === 0) {
  throw new Error("接口未返回图片，请检查完整响应和 finishReason");
}
```

## 14. 错误处理

### 14.1 未提供 API Key

HTTP 状态码：`401 Unauthorized`

GPT/Grok 的 OpenAI 兼容端点可能返回：

```json
{
  "code": "API_KEY_REQUIRED",
  "message": "API key is required in Authorization header (Bearer scheme)"
}
```

Gemini 原生端点可能返回：

```json
{
  "error": {
    "code": 401,
    "message": "API key is required",
    "status": "UNAUTHENTICATED"
  }
}
```

### 14.2 常见状态码

| HTTP 状态码 | 含义 | 建议处理 |
| --- | --- | --- |
| `400` | 请求体、图片比例或分辨率不受支持 | 修改参数后重试，不要直接重复原请求 |
| `401` | 未提供 API Key 或 Key 无效 | GPT/Grok 检查 `Authorization: Bearer`；Gemini 检查 `x-goog-api-key` |
| `403` | API Key 无模型权限或账号受限 | 联系服务提供方检查权限 |
| `404` | 接口或模型不存在 | GPT/Grok 查询 `/v1/models`；Gemini 查询 `/v1beta/models` |
| `429` | 余额、频率或并发额度不足 | 根据响应信息稍后重试 |
| `500` / `502` / `503` / `504` | 中转或上游暂时异常 | 使用指数退避进行有限次数重试 |

错误正文可能是平铺的 `code` / `message`，也可能使用嵌套 `error`。典型嵌套结构：

```json
{
  "error": {
    "code": 400,
    "message": "错误说明",
    "status": "INVALID_ARGUMENT"
  }
}
```

排查问题时请记录：

- 请求时间及所在时区；
- 接口路径和模型名称；
- HTTP 状态码；
- 响应头中的 `x-request-id`；
- 已脱敏的请求体和完整错误正文。

请勿发送完整 API Key、客户隐私图片或完整图片 Base64 数据。

## 15. 超时与重试

- 图片生成总超时建议设置为至少 `300` 秒。
- `400`、`401`、`403`、`404` 等确定性错误应先修改请求或配置，不要自动重试。
- 对 `429` 和 `5xx` 可采用 `1s`、`2s`、`4s` 指数退避，最多重试 3 次。
- 网络断开或客户端超时不代表服务端一定停止处理，盲目重试可能造成重复生成和重复计费。
- 多张结果需要多次请求时，应限制并发，不要通过大量并发请求规避服务端额度。

## 16. 接入检查清单

正式接入前，请确认：

1. API Key 仅保存在服务端环境变量或密钥管理系统中。
2. 已按协议使用 `/v1/models` 或 `/v1beta/models` 查询当前 Key 可用的模型。
3. GPT/Grok 使用 `Authorization: Bearer`，Gemini 使用 `x-goog-api-key`。
4. GPT 已通过 `/v1/images/generations` 完成最小请求，并能解析 `data[].b64_json` 或 `data[].url`。
5. Grok 已验证 `aspect_ratio`、小写 `resolution`；如需参考图，已验证 JSON Data URL 格式。
6. Gemini 已使用 `responseModalities: ["TEXT", "IMAGE"]` 完成最小请求。
7. Gemini 客户端会遍历全部 `candidates[].content.parts[]`，并兼容驼峰和蛇形图片字段。
8. 各协议的参考图已使用非敏感测试图片验证，且未混用 multipart、Data URL 和纯 Base64 格式。
9. 已设置合理的超时、并发限制和有限重试策略。
10. 日志不会记录完整 API Key、原始图片或完整 Base64 数据。

## 17. 技术支持

反馈问题时，请向服务提供方提交请求时间、模型名称、HTTP 状态码、`x-request-id` 和已脱敏错误正文。不要提交完整 API Key 或客户隐私数据。
