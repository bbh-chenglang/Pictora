# beibeihai AI 生图 API 接口文档

> 文档版本：v1.1  
> 更新时间：2026-08-12  
> 接口协议：OpenAI Images API 兼容格式

## 1. 接入信息

| 项目 | 内容 |
| --- | --- |
| API Base URL | `https://sub.beibeihai.xyz/v1` |
| 文生图接口 | `POST /images/generations` |
| 图生图接口 | `POST /images/edits` |
| 模型列表 | `GET /models` |
| 鉴权方式 | `Authorization: Bearer <API_KEY>` |
| 请求格式 | 文生图使用 `application/json`；图生图使用 `multipart/form-data` |
| 响应格式 | `application/json` |

完整请求地址：

```text
文生图：https://sub.beibeihai.xyz/v1/images/generations
图生图：https://sub.beibeihai.xyz/v1/images/edits
```

本文示例使用模型 `gpt-image-1.5`。调用方实际可用的模型以 API Key 权限及 `GET /v1/models` 的返回结果为准。

## 2. 获取与保管 API Key

API Key 由服务提供方单独分配。请勿将 Key 写入前端代码、公开仓库、聊天截图或日志正文中，也不要把 Key 提交到 Git。

推荐通过环境变量保存：

```bash
BEIBEIHAI_API_KEY=你的API_KEY
```

所有请求都应携带以下请求头：

```http
Authorization: Bearer YOUR_API_KEY
```

服务也支持 `x-api-key` 和 `x-goog-api-key` 请求头，但普通 OpenAI 兼容客户端应优先使用 `Authorization: Bearer`。

## 3. 查询可用模型

在正式调用生图接口前，建议先查询当前 API Key 可访问的模型。

### 请求

```http
GET /v1/models HTTP/1.1
Host: sub.beibeihai.xyz
Authorization: Bearer YOUR_API_KEY
```

### cURL 示例

```bash
curl "https://sub.beibeihai.xyz/v1/models" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### 响应示例

实际字段可能随模型来源变化，调用时主要读取 `data[].id`：

```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-image-1.5",
      "object": "model"
    }
  ]
}
```

## 4. 文生图

### 4.1 请求

```http
POST /v1/images/generations HTTP/1.1
Host: sub.beibeihai.xyz
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

### 4.2 请求参数

| 参数 | 类型 | 必填 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `model` | string | 是 | `gpt-image-1.5` | 模型 ID，应使用 `/v1/models` 返回的可用模型 |
| `prompt` | string | 是 | `雨后的上海街道，电影感摄影` | 图片描述，建议写清主体、场景、构图、风格和限制条件 |
| `size` | string | 否 | `1024x1024` | 输出尺寸；可选值和最大尺寸取决于模型 |
| `quality` | string | 否 | `medium` | 常见值为 `low`、`medium`、`high`，取决于模型支持情况 |
| `n` | integer | 否 | `1` | 生成数量，默认为 `1`；上限取决于模型和账户权限 |
| `output_format` | string | 否 | `png` | 常见值为 `png`、`jpeg`、`webp`，取决于模型支持情况 |
| `background` | string | 否 | `auto` | 背景类型；透明背景等能力取决于模型和输出格式 |
| `user` | string | 否 | `user_8f3a12c9` | 调用方内部的稳定用户标识，请勿传入姓名、手机号等敏感信息 |

建议先只传 `model`、`prompt`、`size`、`quality` 和 `n`。其他参数应在确认所选模型支持后再使用。

### 4.3 最简请求体

```json
{
  "model": "gpt-image-1.5",
  "prompt": "一只坐在窗边的橘猫，午后自然光，写实摄影风格",
  "size": "1024x1024",
  "quality": "medium",
  "n": 1
}
```

### 4.4 cURL 示例

```bash
curl -X POST "https://sub.beibeihai.xyz/v1/images/generations" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-1.5",
    "prompt": "一张极简产品摄影：白色陶瓷咖啡杯放在浅灰色摄影台中央，柔和棚拍光，无人物，无文字，无水印",
    "size": "1024x1024",
    "quality": "medium",
    "n": 1
  }'
```

## 5. 图生图（图片编辑）

图生图用于根据一张或多张参考图生成新图片，也可以配合遮罩图进行局部重绘。请求必须以文件上传方式提交，不能把图片文件直接放进文生图 JSON 请求体。

### 5.1 请求

```http
POST /v1/images/edits HTTP/1.1
Host: sub.beibeihai.xyz
Authorization: Bearer YOUR_API_KEY
Content-Type: multipart/form-data; boundary=自动生成
```

使用 cURL 或 SDK 时，不要手动设置 `Content-Type`。客户端会自动生成包含 `boundary` 的完整请求头。

### 5.2 请求参数

| 参数 | 类型 | 必填 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `model` | string | 是 | `gpt-image-1.5` | 支持图片编辑的模型 ID |
| `image[]` | file | 是 | `@input.png` | 输入图片；至少上传一张，重复该字段可上传多张参考图 |
| `prompt` | string | 是 | `保持人物不变，将背景改为雪山` | 描述希望如何修改、融合或重新生成图片 |
| `mask` | file | 否 | `@mask.png` | 遮罩图，用于指示希望修改的区域 |
| `input_fidelity` | string | 否 | `high` | `high` 更强调保留输入图细节，`low` 更允许模型重新创作 |
| `size` | string | 否 | `1024x1024` | 输出尺寸；支持值取决于模型 |
| `quality` | string | 否 | `medium` | 常见值为 `low`、`medium`、`high` 或 `auto` |
| `n` | integer | 否 | `1` | 输出图片数量；上限取决于模型和账户权限 |
| `output_format` | string | 否 | `png` | 常见值为 `png`、`jpeg`、`webp` |
| `output_compression` | integer | 否 | `80` | `jpeg` 或 `webp` 的压缩参数，范围通常为 `0` 到 `100` |
| `background` | string | 否 | `auto` | 背景类型，透明背景能力取决于模型和输出格式 |
| `user` | string | 否 | `user_8f3a12c9` | 调用方内部的稳定、非敏感用户标识 |

本文档的 cURL 示例使用原始表单字段 `image[]`。OpenAI SDK 会自动处理表单编码，SDK 参数名使用 `image`。

### 5.3 单张参考图

下面的请求会尽量保留人物主体，只修改背景和整体光线：

```bash
curl -X POST "https://sub.beibeihai.xyz/v1/images/edits" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "model=gpt-image-1.5" \
  -F "image[]=@input.png" \
  -F "prompt=保持人物的面部、发型、服装和姿势不变，将背景改为冬日雪山，使用柔和自然光，写实摄影风格" \
  -F "input_fidelity=high" \
  -F "size=1024x1024" \
  -F "quality=medium" \
  -F "n=1"
```

### 5.4 多张参考图融合

重复提交 `image[]` 即可上传多张参考图。提示词中应明确每张图的用途，例如“以第一张图的人物为主体，穿上第二张图中的服装”。

```bash
curl -X POST "https://sub.beibeihai.xyz/v1/images/edits" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "model=gpt-image-1.5" \
  -F "image[]=@person.png" \
  -F "image[]=@clothes.png" \
  -F "prompt=以第一张图的人物为主体，保持面部特征和发型，穿上第二张图中的服装，生成自然的全身棚拍照片" \
  -F "input_fidelity=high" \
  -F "size=1024x1536" \
  -F "quality=high" \
  -F "n=1"
```

OpenAI 兼容协议下，`gpt-image-1.5` 最多可接受 16 张输入图；本服务的实际可用数量仍以 API Key、模型权限和接口返回为准。图片越多，处理时间和输入成本通常越高。

### 5.5 遮罩局部重绘

上传 `mask` 可以指示需要修改的区域。透明区域通常表示希望编辑的部分；模型会把遮罩作为引导，但不保证严格按照每个像素的边界修改。

```bash
curl -X POST "https://sub.beibeihai.xyz/v1/images/edits" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "model=gpt-image-1.5" \
  -F "image[]=@room.png" \
  -F "mask=@mask.png" \
  -F "prompt=只在遮罩区域添加一张浅灰色布艺沙发，保持房间其余结构、光线和构图不变" \
  -F "input_fidelity=high" \
  -F "size=1024x1024" \
  -F "quality=medium"
```

遮罩图要求：

- 原图与遮罩图应具有相同的尺寸和文件格式。
- 遮罩图必须包含 Alpha 透明通道，推荐使用 PNG。
- 原图和遮罩图均应小于 `50 MB`。
- 上传多张参考图时，遮罩只应用于第一张输入图。

### 5.6 Python 示例

```python
import base64
import os
from pathlib import Path
from urllib.request import urlopen

from openai import OpenAI


client = OpenAI(
    api_key=os.environ["BEIBEIHAI_API_KEY"],
    base_url="https://sub.beibeihai.xyz/v1",
    timeout=300.0,
)

with open("input.png", "rb") as source_image:
    result = client.images.edit(
        model="gpt-image-1.5",
        image=source_image,
        prompt="保持人物不变，将背景改为冬日雪山，写实摄影风格",
        input_fidelity="high",
        size="1024x1024",
        quality="medium",
        n=1,
    )

image = result.data[0]
output_path = Path("edited.png")

if image.b64_json:
    output_path.write_bytes(base64.b64decode(image.b64_json))
elif image.url:
    output_path.write_bytes(urlopen(image.url, timeout=60).read())
else:
    raise RuntimeError("接口未返回图片数据")

print(output_path.resolve())
```

多图融合时，将 `image` 改为文件对象列表：

```python
with (
    open("person.png", "rb") as person,
    open("clothes.png", "rb") as clothes,
):
    result = client.images.edit(
        model="gpt-image-1.5",
        image=[person, clothes],
        prompt="以第一张图的人物为主体，穿上第二张图中的服装",
        input_fidelity="high",
        size="1024x1536",
        quality="high",
    )
```

局部重绘时，在 `client.images.edit(...)` 中增加 `mask=open("mask.png", "rb")`。正式代码应使用上下文管理器同时关闭原图和遮罩文件。

### 5.7 JavaScript 示例

```javascript
import fs from "node:fs";
import OpenAI, { toFile } from "openai";

const client = new OpenAI({
  apiKey: process.env.BEIBEIHAI_API_KEY,
  baseURL: "https://sub.beibeihai.xyz/v1",
  timeout: 300_000,
});

const sourceImage = await toFile(
  fs.createReadStream("input.png"),
  "input.png",
  { type: "image/png" },
);

const result = await client.images.edit({
  model: "gpt-image-1.5",
  image: sourceImage,
  prompt: "保持人物不变，将背景改为冬日雪山，写实摄影风格",
  input_fidelity: "high",
  size: "1024x1024",
  quality: "medium",
  n: 1,
});

const image = result.data[0];

if (image.b64_json) {
  fs.writeFileSync("edited.png", Buffer.from(image.b64_json, "base64"));
} else if (image.url) {
  const response = await fetch(image.url);
  if (!response.ok) throw new Error(`下载图片失败：${response.status}`);
  fs.writeFileSync("edited.png", Buffer.from(await response.arrayBuffer()));
} else {
  throw new Error("接口未返回图片数据");
}
```

多图融合时，分别使用 `toFile(...)` 创建文件对象，然后传入 `image: [personImage, clothesImage]`。

## 6. 返回结果

文生图和图生图使用相同的返回结构。生成结果通常以 Base64 图片数据返回：

```json
{
  "created": 1786492800,
  "data": [
    {
      "b64_json": "iVBORw0KGgoAAA..."
    }
  ]
}
```

部分上游模型或存储配置也可能返回图片 URL：

```json
{
  "created": 1786492800,
  "data": [
    {
      "url": "https://example.com/generated/image.png"
    }
  ]
}
```

调用方应兼容以下两种结果：

- `data[].b64_json`：Base64 编码的图片内容，解码后保存为图片文件。
- `data[].url`：图片访问地址。URL 可能有有效期，应及时下载并保存。

当 `n` 大于 `1` 时，应遍历整个 `data` 数组，不要只处理第一项。

## 7. Python 文生图示例

安装 OpenAI Python SDK：

```bash
pip install openai
```

调用并保存第一张图片：

```python
import base64
import os
from pathlib import Path
from urllib.request import urlopen

from openai import OpenAI


client = OpenAI(
    api_key=os.environ["BEIBEIHAI_API_KEY"],
    base_url="https://sub.beibeihai.xyz/v1",
    timeout=300.0,
)

result = client.images.generate(
    model="gpt-image-1.5",
    prompt="一只坐在窗边的橘猫，午后自然光，写实摄影风格",
    size="1024x1024",
    quality="medium",
    n=1,
)

image = result.data[0]
output_path = Path("output.png")

if image.b64_json:
    output_path.write_bytes(base64.b64decode(image.b64_json))
elif image.url:
    output_path.write_bytes(urlopen(image.url, timeout=60).read())
else:
    raise RuntimeError("接口未返回图片数据")

print(output_path.resolve())
```

## 8. JavaScript 文生图示例

安装 OpenAI Node.js SDK：

```bash
npm install openai
```

调用并保存第一张图片：

```javascript
import fs from "node:fs/promises";
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.BEIBEIHAI_API_KEY,
  baseURL: "https://sub.beibeihai.xyz/v1",
  timeout: 300_000,
});

const result = await client.images.generate({
  model: "gpt-image-1.5",
  prompt: "一只坐在窗边的橘猫，午后自然光，写实摄影风格",
  size: "1024x1024",
  quality: "medium",
  n: 1,
});

const image = result.data[0];

if (image.b64_json) {
  await fs.writeFile("output.png", Buffer.from(image.b64_json, "base64"));
} else if (image.url) {
  const response = await fetch(image.url);
  if (!response.ok) throw new Error(`下载图片失败：${response.status}`);
  await fs.writeFile("output.png", Buffer.from(await response.arrayBuffer()));
} else {
  throw new Error("接口未返回图片数据");
}
```

## 9. 错误处理

### 9.1 未提供 API Key

HTTP 状态码：`401 Unauthorized`

```json
{
  "code": "API_KEY_REQUIRED",
  "message": "API key is required in Authorization header (Bearer scheme), x-api-key header, or x-goog-api-key header"
}
```

### 9.2 API Key 无效

HTTP 状态码：`401 Unauthorized`

```json
{
  "code": "INVALID_API_KEY",
  "message": "Invalid API key"
}
```

### 9.3 常见状态码

| HTTP 状态码 | 含义 | 建议处理 |
| --- | --- | --- |
| `400` | 请求参数不正确 | 检查模型、提示词、尺寸和参数取值 |
| `401` | 未提供 Key 或 Key 无效 | 检查鉴权请求头，不要在日志中输出完整 Key |
| `403` | Key、用户或分组无权调用 | 联系服务提供方检查权限 |
| `404` | 路由、模型或可选功能不存在 | 先通过 `/v1/models` 核对模型 |
| `429` | 余额、速率或并发限制 | 读取错误信息和 `Retry-After`，稍后重试 |
| `500` / `502` / `503` / `504` | 服务或上游暂时异常 | 使用指数退避进行有限次数重试 |

不同错误可能使用以下任一种 JSON 结构，客户端应同时兼容：

```json
{
  "code": "ERROR_CODE",
  "message": "错误说明"
}
```

```json
{
  "error": {
    "type": "api_error",
    "code": "ERROR_CODE",
    "message": "错误说明"
  }
}
```

排查问题时，请记录响应头中的 `x-request-id`、HTTP 状态码和错误正文，并将这些信息提供给服务方。请勿提供完整 API Key。

## 10. 配额、并发与计费

- 可用余额、调用频率、并发数和模型权限以分配给调用方的 API Key 策略为准。
- 不同模型、尺寸、质量和生成数量可能采用不同计费标准；接入前请向服务提供方确认当前价格。
- 客户端不应假设固定并发上限，也不应通过高频重试规避服务端限制。
- API Key 停用、过期、余额不足或权限调整后，已有接入可能无法继续调用。

## 11. 超时与重试建议

- 图片生成耗时通常高于普通文本接口，客户端总超时建议设置为至少 `300` 秒。
- 收到明确的 `429` 或 `5xx` 响应时，可采用 `1s`、`2s`、`4s` 的指数退避，最多重试 3 次。
- 网络断开或客户端超时并不代表服务端一定停止生成。不要立即无限重试，否则可能重复生成并重复计费。
- 不要并发复用同一个请求来“抢响应”；并发额度以服务端为准。
- 异步生图接口属于可选能力，是否开放需向服务提供方确认，未确认前不要依赖 `/v1/images/generations/async`。

## 12. 接入检查清单

正式接入前，请确认：

1. 已获得独立 API Key，并放入服务端环境变量。
2. `GET /v1/models` 能正常返回模型列表。
3. 已使用 `1024x1024`、`n: 1` 完成一次最小文生图测试。
4. 如需图生图，已使用一张非敏感测试图完成 `/v1/images/edits` 调用。
5. 程序能够同时处理 `b64_json` 和 `url` 两种图片结果。
6. 已设置足够长的超时时间，并限制重试次数。
7. 日志不会记录完整 API Key、上传的原图或完整 Base64 图片数据。

## 13. 技术支持所需信息

反馈问题时请提供：

- 请求时间及所在时区；
- 请求接口和模型名称；
- HTTP 状态码；
- 响应头中的 `x-request-id`；
- 已脱敏的请求参数与错误正文。

请勿发送完整 API Key、用户隐私数据或完整图片 Base64 内容。
