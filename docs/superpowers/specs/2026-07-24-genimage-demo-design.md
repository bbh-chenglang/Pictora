# GenImage Demo 设计方案

## 1. 目标

构建一个同时支持文生图和图片分析的全栈 Demo。用户可以选择 OpenAI 或自定义的 OpenAI 兼容提供商，输入提示词或上传图片，并在同一个双栏工作台中查看结果。

首期目标是验证以下能力：

- 多提供商配置和切换
- 文生图请求
- 图片理解请求
- 统一的错误处理和加载状态
- 亮色、具有艺术气息的创作工具界面

首期不包含用户系统、权限、任务队列、流式响应和数据库历史记录。

## 2. 技术栈

### 后端

- FastAPI：HTTP API 和文件上传
- OpenAI Python SDK：调用 OpenAI 及兼容接口
- Provider Adapter：隔离不同提供商的请求格式和响应格式
- Pydantic Settings：读取环境变量配置
- `httpx`：特殊提供商或自定义 HTTP 请求
- `python-multipart`：处理图片上传

### 前端

- Vue 3
- Vite
- TypeScript
- Tailwind CSS
- shadcn-vue
- Vue Composition API
- Lucide 图标

不使用 Pinia。页面状态通过组件内的 `ref`、`computed`、事件回调和组合式函数管理。

## 3. 系统架构

```text
Vue 双栏工作台
        |
        | HTTP / FormData
        v
FastAPI API 层
        |
        v
统一业务服务层
        |
        v
Provider Adapter
   ├── OpenAI Provider
   ├── Compatible Provider
   └── Custom Provider
        |
        v
模型提供商 API
```

前端只依赖统一业务接口，不直接处理厂商特有的请求格式。后端根据 `provider` 选择适配器，并将不同响应转换成统一结构。

## 4. Provider 设计

```text
backend/app/providers/
├── base.py
├── openai_provider.py
├── compatible_provider.py
└── custom_provider.py
```

统一接口：

```python
class ImageProvider:
    async def generate_image(self, request):
        ...

    async def analyze_image(self, request):
        ...
```

Provider Adapter 负责：

- 认证和 Base URL
- 模型名称转换
- 文生图请求转换
- 图片输入转换
- 图片结果统一
- 分析文本统一
- 超时、鉴权失败、模型不存在和参数错误转换

OpenAI 兼容提供商默认使用自定义 `base_url`。完全不兼容 OpenAI 协议的提供商通过 `custom_provider.py` 单独实现。

环境变量示例：

```env
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-image-2

CUSTOM_API_KEY=
CUSTOM_BASE_URL=https://your-provider.example.com/v1
CUSTOM_MODEL=your-vision-model
```

API Key 只允许由后端读取，不返回给前端。

## 5. API 设计

### 获取提供商和模型

```http
GET /api/providers
```

用于初始化前端的 Provider 和 Model 选项。返回内容不包含 API Key。

### 生成图片

```http
POST /api/generate
Content-Type: application/json
```

请求示例：

```json
{
  "provider": "openai",
  "model": "gpt-image-2",
  "prompt": "一只在雪山上的狐狸",
  "detail": "auto"
}
```

返回示例：

```json
{
  "provider": "openai",
  "model": "gpt-image-2",
  "images": [
    {
      "url": "https://example.com/generated-image.png",
      "revised_prompt": null
    }
  ]
}
```

### 分析图片

```http
POST /api/analyze
Content-Type: multipart/form-data
```

字段：

- `provider`
- `model`
- `prompt`
- `detail`
- `image`

返回示例：

```json
{
  "provider": "openai",
  "model": "gpt-5.6",
  "text": "图片中是一片雪山，前景有一只狐狸。"
}
```

### 错误结构

所有业务错误使用统一结构：

```json
{
  "error": {
    "code": "provider_auth_error",
    "message": "Provider authentication failed"
  }
}
```

前端至少需要处理：

- `provider_auth_error`
- `model_not_found`
- `invalid_request`
- `unsupported_image`
- `provider_timeout`
- `provider_unavailable`
- `unknown_error`

## 6. 前端布局

采用 A「双栏工作台」：

### 左侧控制区

- Provider 选择
- Model 选择
- Prompt 多行输入
- 参考图片上传
- `detail` 参数
- 生成图片按钮
- 分析图片按钮
- 当前请求状态

### 右侧结果区

- 图片生成结果网格
- 单张图片预览
- 图片下载按钮
- 图片分析文本
- 空状态
- 加载状态
- 错误状态
- 最近一次请求的 Provider 和 Model 信息

页面状态通过局部组合式函数管理，例如：

```text
useProviders()
useGenerateImage()
useAnalyzeImage()
```

不引入全局状态管理库，不保存跨页面状态。

## 7. 视觉规范

视觉方向为 C「艺术实验室」：

- 亮色背景
- 明黄色、珊瑚红、蓝绿色作为强调色
- 黑色硬边框和清晰网格
- 图片结果采用画廊式排列
- 工具面板保持高对比度和易操作
- 使用现代无衬线 UI 字体，并以少量艺术化标题字体形成层次
- 使用 Lucide 图标，不使用 Unicode 字符代替图标
- 保持按钮、上传区、结果网格的稳定尺寸
- 不使用深色控制台风格、背景渐变和虚假统计数据

视觉重点是图片内容本身，装饰只用于建立艺术实验室的识别度，不能影响参数操作和结果浏览。

## 8. 请求状态与错误处理

生成和分析请求都需要具有以下状态：

```text
idle -> loading -> success
             \-> error
```

加载时：

- 禁用当前操作按钮
- 展示明确的加载状态
- 保留已有结果，避免页面跳动

成功时：

- 更新右侧结果区域
- 展示实际使用的 Provider 和 Model
- 允许预览和下载图片

失败时：

- 保留用户输入
- 将后端错误转换成可读提示
- 不显示 API Key、完整请求头或内部堆栈
- 允许用户修改参数后重新提交

## 9. 目录结构

```text
GenImage/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── generate.py
│   │   │   ├── analyze.py
│   │   │   └── providers.py
│   │   ├── providers/
│   │   ├── schemas/
│   │   └── services/
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── views/
│   │   ├── composables/
│   │   ├── api/
│   │   └── types/
│   └── package.json
└── docs/
    ├── images-vision.md
    └── superpowers/specs/2026-07-24-genimage-demo-design.md
```

## 10. 验收标准

1. 可以在页面中切换 OpenAI 和自定义兼容 Provider。
2. 可以切换对应模型。
3. 可以通过提示词生成图片。
4. 可以上传图片并进行分析。
5. 请求过程中显示加载状态。
6. API 错误可以清晰展示。
7. 图片可以预览和下载。
8. 未配置某个 Provider 时，页面仍然可以正常启动。
9. 前端不依赖 Pinia。
10. API Key 只存在于后端环境变量。
11. 页面在桌面和移动尺寸下不会出现明显布局错乱。

## 11. 范围外事项

以下功能暂不纳入本次 Demo：

- 用户注册和登录
- 多用户权限
- 数据库持久化
- 历史任务和云端图片存储
- 任务队列和重试系统
- 流式响应
- 计费和用量统计
- 生产环境部署
