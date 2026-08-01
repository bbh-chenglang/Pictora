# Images and Vision

> 整理自 OpenAI 官方文档：[Images and vision](https://developers.openai.com/api/docs/guides/images-vision)
>
> 本文用于快速了解 OpenAI API 的图像理解（Vision）和图像生成能力。模型、价格和限制可能变化，使用前请以官网最新文档为准。

## 1. 能力概览

视觉模型可以理解图像中的物体、形状、颜色、纹理以及图像中的文字。GPT Image 模型还可以结合文本和图像输入生成新图像或编辑已有图像。

OpenAI 提供以下接口处理图像：

| API | 适用场景 |
| --- | --- |
| [Responses API](https://developers.openai.com/api/docs/api-reference/responses) | 分析图像；使用图像作为输入；生成图像 |
| [Images API](https://developers.openai.com/api/docs/api-reference/images) | 生成图像，可选地使用图像作为输入 |
| [Chat Completions API](https://developers.openai.com/api/docs/api-reference/chat) | 分析图像并生成文本或音频 |

## 2. 生成或编辑图像

可以通过 Image API 或 Responses API 生成或编辑图像。当前文档中的示例使用 `gpt-image-2` 作为图像模型，并通过 Responses API 的 `image_generation` 工具生成图像。

### JavaScript

```javascript
import OpenAI from "openai";
import fs from "fs";

const openai = new OpenAI();

const response = await openai.responses.create({
  model: "gpt-5.6",
  input: "Generate an image of gray tabby cat hugging an otter with an orange scarf",
  tools: [{ type: "image_generation" }],
});

const imageData = response.output
  .filter((output) => output.type === "image_generation_call")
  .map((output) => output.result);

if (imageData.length > 0) {
  fs.writeFileSync("cat_and_otter.png", Buffer.from(imageData[0], "base64"));
}
```

### Python

```python
from openai import OpenAI
import base64

client = OpenAI()

response = client.responses.create(
    model="gpt-5.6",
    input="Generate an image of gray tabby cat hugging an otter with an orange scarf",
    tools=[{"type": "image_generation"}],
)

image_data = [
    output.result
    for output in response.output
    if output.type == "image_generation_call"
]

if image_data:
    with open("cat_and_otter.png", "wb") as f:
        f.write(base64.b64decode(image_data[0]))
```

更多图像生成细节请参考 [Image generation](https://developers.openai.com/api/docs/guides/image-generation)。

## 3. 分析图像

### 3.1 图像输入方式

图像可以通过以下方式传入：

1. 可公开访问的完整图片 URL。
2. Base64 编码的 Data URL，例如 `data:image/jpeg;base64,...`。
3. 通过 Files API 上传后得到的文件 ID。

一次请求可以在 `content` 数组中传入多张图像，但每张图像都会计入 token 使用量并产生相应费用。

### 3.2 通过 URL 传入图像

#### JavaScript

```javascript
import OpenAI from "openai";

const openai = new OpenAI();

const response = await openai.responses.create({
  model: "gpt-5.6",
  input: [
    {
      role: "user",
      content: [
        { type: "input_text", text: "what's in this image?" },
        {
          type: "input_image",
          image_url:
            "https://api.nga.gov/iiif/a2e6da57-3cd1-4235-b20e-95dcaefed6c8/full/!800,800/0/default.jpg",
          detail: "auto",
        },
      ],
    },
  ],
});

console.log(response.output_text);
```

#### Python

```python
from openai import OpenAI

client = OpenAI()

response = client.responses.create(
    model="gpt-5.6",
    input=[{
        "role": "user",
        "content": [
            {"type": "input_text", "text": "what's in this image?"},
            {
                "type": "input_image",
                "image_url": "https://api.nga.gov/iiif/a2e6da57-3cd1-4235-b20e-95dcaefed6c8/full/!800,800/0/default.jpg",
            },
        ],
    }],
)

print(response.output_text)
```

#### cURL

```bash
curl https://api.openai.com/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "model": "gpt-5.6",
    "input": [
      {
        "role": "user",
        "content": [
          {"type": "input_text", "text": "what is in this image?"},
          {
            "type": "input_image",
            "image_url": "https://api.nga.gov/iiif/a2e6da57-3cd1-4235-b20e-95dcaefed6c8/full/!800,800/0/default.jpg"
          }
        ]
      }
    ]
  }'
```

### 3.3 通过 Base64 Data URL 传入图像

#### JavaScript

```javascript
import fs from "fs";
import OpenAI from "openai";

const openai = new OpenAI();
const base64Image = fs.readFileSync("fixtures/example.jpg", "base64");

const response = await openai.responses.create({
  model: "gpt-5.6",
  input: [
    {
      role: "user",
      content: [
        { type: "input_text", text: "what's in this image?" },
        {
          type: "input_image",
          image_url: `data:image/jpeg;base64,${base64Image}`,
          detail: "auto",
        },
      ],
    },
  ],
});

console.log(response.output_text);
```

#### Python

```python
import base64
from openai import OpenAI

client = OpenAI()

with open("path_to_your_image.jpg", "rb") as image_file:
    base64_image = base64.b64encode(image_file.read()).decode("utf-8")

response = client.responses.create(
    model="gpt-5.6",
    input=[{
        "role": "user",
        "content": [
            {"type": "input_text", "text": "what's in this image?"},
            {
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{base64_image}",
            },
        ],
    }],
)

print(response.output_text)
```

### 3.4 通过文件 ID 传入图像

先使用 Files API 上传文件，并设置 `purpose="vision"`，然后在 Responses API 中通过 `file_id` 引用文件。

```python
from openai import OpenAI

client = OpenAI()

with open("path_to_your_image.jpg", "rb") as image_file:
    uploaded_file = client.files.create(
        file=image_file,
        purpose="vision",
    )

response = client.responses.create(
    model="gpt-5.6",
    input=[{
        "role": "user",
        "content": [
            {"type": "input_text", "text": "what's in this image?"},
            {
                "type": "input_image",
                "file_id": uploaded_file.id,
            },
        ],
    }],
)

print(response.output_text)
```

## 4. 图像输入要求

| 项目 | 要求 |
| --- | --- |
| 支持格式 | PNG、JPEG（`.jpeg` / `.jpg`）、WEBP、非动画 GIF |
| 单次请求总大小 | 最大 512 MB |
| 单次请求图片数量 | 最多 1,500 张 |
| 内容要求 | 不包含水印或 Logo；不包含 NSFW 内容；图像清晰到人类可以理解 |

## 5. `detail` 细节级别

`detail` 决定模型处理图像时使用的细节级别，可选值为 `low`、`high`、`original` 和 `auto`。省略该字段时使用 `auto`。

```json
{
  "type": "input_image",
  "image_url": "https://example.com/image.jpg",
  "detail": "original"
}
```

| 级别 | 适用场景 |
| --- | --- |
| `low` | 速度快、成本低；不需要精细视觉细节时使用。模型接收约 512 x 512 的低分辨率版本 |
| `high` | 标准的高保真图像理解 |
| `original` | 大图、密集内容、空间敏感内容或 computer-use 场景；在 `gpt-5.4` 及未来模型中可用 |
| `auto` | 自动选择。对 `gpt-5.5` 和 GPT-5.6，`auto` 及省略字段的行为等同于 `original` |

对于 `gpt-5.4` 及未来模型中的 computer-use、定位和点击精度场景，推荐使用 `detail: "original"`。

## 6. 模型缩放行为

不同模型在图像 token 化前采用不同的缩放规则：

| 模型系列 | 支持的 `detail` | 行为摘要 |
| --- | --- | --- |
| GPT-5.6 | `low`、`high`、`original`、`auto` | `original` 保留输入尺寸，不受像素或 patch 预算限制；`auto` 与省略字段采用同样行为 |
| `gpt-5.5` | `low`、`high`、`original`、`auto` | `high` 最多 2,500 patches 或最大边 2,048 px；`original` 最多 10,000 patches 或最大边 6,000 px |
| `gpt-5.4` | `low`、`high`、`original`、`auto` | `high` 最多 2,500 patches 或最大边 2,048 px；`original` 最多 10,000 patches 或最大边 6,000 px；`auto` 等同于 `high` |
| `gpt-5.4-mini`、`gpt-5.4-nano`、`gpt-5-mini`、`gpt-5-nano`、`gpt-5.2`、Codex 系列、`o4-mini` 等 | `low`、`high`、`auto` | `high` 最多 1,536 patches 或最大边 2,048 px |
| GPT-4o、GPT-4.1、GPT-4o-mini、computer-use-preview 及除 `o4-mini` 外的 o-series | `low`、`high`、`auto` | 使用基于 tile 的缩放规则 |

超过模型限制时，服务会在保持宽高比的前提下缩放图像。请求 payload 和其他图像输入限制仍然适用。

## 7. 图像 token 与成本

图像输入按 token 计费，并计入 TPM（tokens per minute）限制。实际成本取决于模型、图像尺寸和 `detail`。最新价格请参考 [Pricing](https://openai.com/api/pricing/) 的图像定价和计算器。

### 7.1 基于 patch 的 token 化

部分模型使用 32 x 32 像素 patch 覆盖图像。基本计算过程如下：

1. 原始 patch 数量：

   ```text
   original_patch_count = ceil(width / 32) * ceil(height / 32)
   ```

2. 如果超出模型 patch 预算，按比例缩小图像，并在转换为整数像素后再次调整比例。
3. 计算缩放后的 patch 数量：

   ```text
   resized_patch_count = ceil(resized_width / 32) * ceil(resized_height / 32)
   ```

4. 将 patch 数量乘以模型对应的 token 倍率，得到计费 token 数。

常见模型倍率：

| 模型 | 倍率 |
| --- | ---: |
| `gpt-5.4-mini`、`gpt-5-mini` | 1.62 |
| `gpt-5.4-nano`、`gpt-5-nano` | 2.46 |
| `gpt-4.1-mini`（2025-04-14 snapshot） | 1.62 |
| `gpt-4.1-nano`（2025-04-14 snapshot） | 2.46 |
| `o4-mini` | 1.72 |

例如，对于 1,536 patch 预算的模型：

- 1,024 x 1,024 图像需要 1,024 个 patch，不需要缩放。
- 1,800 x 2,400 图像原始需要 4,275 个 patch，缩放后约为 1,056 x 1,408，得到 1,452 个 patch，再乘以模型倍率计费。

对于 GPT-5.6 使用 `original` 或 `auto` 时，服务直接使用原始 patch 数，不再按 patch 预算或像素上限缩放。若需要控制 token 和延迟，应在请求前自行缩放图片，或使用 `low` / `high`。

### 7.2 基于 tile 的 token 化

适用于 GPT-4o、GPT-4.1、GPT-4o-mini、CUA 及除 `o4-mini` 外的 o-series：

- `detail: "low"` 使用固定的基础 token 数。
- `detail: "high"` 的计算步骤为：先缩放到 2,048 x 2,048 以内，再将短边缩放到 768 px，最后按 512 x 512 tile 数量计费，并加上基础 token。

| 模型 | 基础 token | 每个 tile token |
| --- | ---: | ---: |
| `gpt-5`、`gpt-5-chat-latest` | 70 | 140 |
| `gpt-4o`、`gpt-4.1`、`gpt-4.5` | 85 | 170 |
| `gpt-4o-mini` | 2,833 | 5,667 |
| `o1`、`o1-pro`、`o3` | 75 | 150 |
| `computer-use-preview` | 65 | 129 |

### 7.3 GPT Image 1

GPT Image 1 的图像输入成本计算方式与 tile 方案类似，但会将短边缩放到 512 px。价格还取决于图像尺寸和 [input fidelity](https://developers.openai.com/api/docs/guides/image-generation?image-generation-model=gpt-image-1#image-input-fidelity)：

- 低输入保真度：基础成本 65 image tokens，每个 tile 129 image tokens。
- 高输入保真度：除上述 token 外，还会按宽高比增加 token。
  - 正方形图片增加 4,160 input image tokens。
  - 更接近竖屏或横屏的图片增加 6,240 input image tokens。

## 8. 局限性与注意事项

- **医疗图像**：不适合解读 CT 等专业医疗图像，也不能替代医疗建议。
- **非英文文字**：对日文、韩文等非拉丁文字的识别可能不稳定。
- **小文字**：放大图片中的文字；可用时考虑 `detail: "original"`。
- **旋转内容**：可能误读旋转或倒置的文字和图像。
- **图表和样式**：对依赖颜色或实线、虚线、点线等样式区分的图表可能理解不准确。
- **空间推理**：在棋盘定位等需要精确空间定位的任务上能力有限。
- **准确性**：描述、字幕和视觉判断可能出现错误。
- **图像形状**：对全景图和鱼眼图像的理解可能较弱。
- **元数据和缩放**：模型不会处理原始文件名或元数据；`low`、`high` 以及有固定图像预算的模型可能在分析前缩放图像。
- **计数**：对图像中物体数量的判断可能是近似值。
- **CAPTCHA**：出于安全原因，系统会阻止 CAPTCHA 图片提交。

## 9. 实践建议

1. 普通图片问答优先使用 `detail: "auto"`。
2. 对小文字、密集内容、定位和点击任务，使用 `detail: "original"`（模型支持时）。
3. 对成本和延迟敏感的场景，使用 `low` 或在客户端预先缩放图片。
4. 多图请求前估算总 payload、图片数量和 token 使用量。
5. 不要把视觉输出当作医疗、身份、法律或其他高风险场景的唯一依据。

## 10. 相关链接

- [Images and vision 官方指南](https://developers.openai.com/api/docs/guides/images-vision)
- [Responses API](https://developers.openai.com/api/docs/api-reference/responses)
- [Images API](https://developers.openai.com/api/docs/api-reference/images)
- [Chat Completions API](https://developers.openai.com/api/docs/api-reference/chat)
- [Image generation 指南](https://developers.openai.com/api/docs/guides/image-generation)
- [Models](https://developers.openai.com/api/docs/models)
- [Pricing](https://openai.com/api/pricing/)
