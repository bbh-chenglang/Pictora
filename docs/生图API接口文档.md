# 北海 AI Gemini 生图 API 接入文档

> 文档版本：v2.0
>
> 更新时间：2026-08-13
>
> 接口协议：Google Gemini 原生 REST API 兼容格式

本文档用于指导客户通过北海 AI 中转服务接入 Gemini 生图模型，包括文生图、参考图生图、多图融合和结果解析。

## 1. 接入信息

| 项目 | 内容 |
| --- | --- |
| 服务地址 | `https://sub.beibeihai.xyz` |
| Gemini Base URL | `https://sub.beibeihai.xyz/v1beta` |
| 模型列表 | `GET /models` |
| 图片生成 | `POST /models/{model}:generateContent` |
| 鉴权方式 | `x-goog-api-key: YOUR_API_KEY` |
| 请求格式 | `application/json` |
| 响应格式 | `application/json` |
| API Key 管理 | `https://sub.beibeihai.xyz/home` |

> Base URL 已包含 `/v1beta`。客户端不要再次拼接 `/v1beta`，否则会形成错误的 `/v1beta/v1beta/...` 地址。

## 2. 快速接入

1. 从服务提供方获取 API Key，也可访问 [API Key 管理页面](https://sub.beibeihai.xyz/home)。
2. 请求 `GET https://sub.beibeihai.xyz/v1beta/models` 查询当前 Key 可用的模型。
3. 从返回结果中选择支持图片生成的 Gemini 模型。
4. 请求 `POST /v1beta/models/{model}:generateContent`，并将 `responseModalities` 设置为 `IMAGE` 或 `TEXT` 与 `IMAGE`。
5. 从响应的 `candidates[].content.parts[].inlineData` 中读取并解码图片。

最简 cURL 示例：

```bash
curl -X POST \
  "https://sub.beibeihai.xyz/v1beta/models/gemini-3.1-flash-image:generateContent" \
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

本文使用 `gemini-3.1-flash-image` 作为示例。中转服务的模型可能调整，客户实际可用模型必须以其 API Key 请求 `/v1beta/models` 的返回结果为准。

## 3. API Key 鉴权

推荐将 API Key 保存在服务端环境变量中：

```bash
BEIBEIHAI_API_KEY=你的API_KEY
```

每个请求都应携带以下请求头：

```http
x-goog-api-key: YOUR_API_KEY
```

不要把 API Key 写入浏览器前端、公开仓库、聊天截图或普通业务日志。客户端应为不同项目或环境使用独立 Key，以便控制权限、额度和停用范围。

## 4. 查询可用模型

### 4.1 请求

```http
GET /v1beta/models HTTP/1.1
Host: sub.beibeihai.xyz
x-goog-api-key: YOUR_API_KEY
```

### 4.2 cURL 示例

```bash
curl "https://sub.beibeihai.xyz/v1beta/models" \
  -H "x-goog-api-key: YOUR_API_KEY"
```

### 4.3 响应示例

```json
{
  "models": [
    {
      "name": "models/gemini-3.1-flash-image",
      "displayName": "Gemini 3.1 Flash Image",
      "supportedGenerationMethods": ["generateContent"]
    }
  ]
}
```

模型名称通常带有 `models/` 前缀。拼接生成接口时只保留一个 `models/`：

```text
正确：/v1beta/models/gemini-3.1-flash-image:generateContent
错误：/v1beta/models/models/gemini-3.1-flash-image:generateContent
```

调用方可移除模型返回值开头的 `models/`，再放入生成接口路径。

## 5. 文生图

### 5.1 请求地址

```http
POST /v1beta/models/{model}:generateContent HTTP/1.1
Host: sub.beibeihai.xyz
x-goog-api-key: YOUR_API_KEY
Content-Type: application/json
```

### 5.2 请求体

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

### 5.3 主要参数

| 参数路径 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `contents` | array | 是 | 对话内容列表 |
| `contents[].role` | string | 否 | 调用方角色，通常使用 `user` |
| `contents[].parts` | array | 是 | 文本和参考图片内容 |
| `parts[].text` | string | 是 | 生图提示词 |
| `generationConfig.responseModalities` | string[] | 是 | 设为 `["IMAGE"]` 或 `["TEXT", "IMAGE"]` |
| `generationConfig.imageConfig.aspectRatio` | string | 否 | 输出图片比例，具体取值取决于模型 |
| `generationConfig.imageConfig.imageSize` | string | 否 | 输出分辨率，例如 `1K`、`2K`、`4K`，具体取值取决于模型 |

`responseModalities` 的选择：

- 只需要图片时使用 `["IMAGE"]`。
- 需要模型同时返回文字说明和图片时使用 `["TEXT", "IMAGE"]`。

### 5.4 图片比例与分辨率

常见图片比例：

```text
1:1、2:3、3:2、3:4、4:3、4:5、5:4、9:16、16:9、21:9
```

部分新模型还支持更宽或更长的比例，例如：

```text
1:4、1:8、4:1、8:1
```

支持的分辨率通常包括：

```text
1K、2K、4K
```

不同 Gemini 生图模型支持的比例和分辨率可能不同。若模型不支持某个参数，接口通常返回 `400`；此时应调整参数或暂时移除 `imageConfig`，不要对参数错误自动重试。

## 6. 参考图生图

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

## 7. 多图融合

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
    "responseModalities": ["IMAGE"],
    "imageConfig": {
      "aspectRatio": "2:3",
      "imageSize": "2K"
    }
  }
}
```

可上传的参考图数量取决于具体模型和账户权限。建议先从 1 至 2 张测试，不要假设所有模型具有相同上限。

## 8. 返回结果

Gemini 原生接口会在 `candidates[].content.parts[]` 中返回文本或图片。图片位于 `inlineData`：

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
- 存在 `part.inlineData.data` 时，将 Base64 解码为图片。
- 使用 `part.inlineData.mimeType` 确定文件类型，不要固定假设返回 PNG。
- 不要只读取第一个 `part`，文字和图片可能位于不同位置。

Gemini 原生生图请求没有 OpenAI Images API 的 `n` 参数。需要多张结果时，应由调用方发起多次生成请求，并自行控制并发和重试。

## 9. Python 完整示例

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
MODEL = "gemini-3.1-flash-image"
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

        mime_type = inline_data.get("mimeType", "image/png")
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

## 10. JavaScript 完整示例

以下示例适用于 Node.js 18 及以上版本：

```javascript
import fs from "node:fs/promises";

const apiKey = process.env.BEIBEIHAI_API_KEY;
const model = "gemini-3.1-flash-image";
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
    const extension = extensionByMime[inlineData.mimeType] ?? "bin";
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

## 11. 错误处理

### 11.1 未提供 API Key

HTTP 状态码：`401 Unauthorized`

```json
{
  "error": {
    "code": 401,
    "message": "API key is required",
    "status": "UNAUTHENTICATED"
  }
}
```

### 11.2 常见状态码

| HTTP 状态码 | 含义 | 建议处理 |
| --- | --- | --- |
| `400` | 请求体、图片比例或分辨率不受支持 | 修改参数后重试，不要直接重复原请求 |
| `401` | 未提供 API Key 或 Key 无效 | 检查 `x-goog-api-key` 请求头 |
| `403` | API Key 无模型权限或账号受限 | 联系服务提供方检查权限 |
| `404` | 接口或模型不存在 | 通过 `/v1beta/models` 重新查询模型 |
| `429` | 余额、频率或并发额度不足 | 根据响应信息稍后重试 |
| `500` / `502` / `503` / `504` | 中转或上游暂时异常 | 使用指数退避进行有限次数重试 |

典型错误结构：

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

## 12. 超时与重试

- 图片生成总超时建议设置为至少 `300` 秒。
- `400`、`401`、`403`、`404` 等确定性错误应先修改请求或配置，不要自动重试。
- 对 `429` 和 `5xx` 可采用 `1s`、`2s`、`4s` 指数退避，最多重试 3 次。
- 网络断开或客户端超时不代表服务端一定停止处理，盲目重试可能造成重复生成和重复计费。
- 多张结果需要多次请求时，应限制并发，不要通过大量并发请求规避服务端额度。

## 13. 接入检查清单

正式接入前，请确认：

1. API Key 仅保存在服务端环境变量或密钥管理系统中。
2. `GET /v1beta/models` 能返回当前 Key 可用的模型。
3. 已使用 `1:1`、`1K` 完成一次最小文生图测试。
4. 客户端会遍历所有 `candidates[].content.parts[]`，而不是只读取第一项。
5. 客户端按 `inlineData.mimeType` 保存图片，并能正确解码 Base64。
6. 如需图生图，已使用非敏感测试图验证 `inlineData` 请求格式。
7. 已设置合理的超时、并发限制和有限重试策略。
8. 日志不会记录完整 API Key、原始图片或完整 Base64 数据。

## 14. 技术支持

反馈问题时，请向服务提供方提交请求时间、模型名称、HTTP 状态码、`x-request-id` 和已脱敏错误正文。不要提交完整 API Key 或客户隐私数据。
