# 多 API Key 配置设计

## 目标

在现有 GenImage 工作台中支持同一用户维护多组 API 配置。每组配置由唯一别名、API Key、提供商类型和模型名组成。工作台的模型下拉框展示配置别名，生成时由后端根据配置 ID 选择对应的 API Key 和调用链路。

## 范围

- GPT 配置继续使用现有 OpenAI 兼容 Images API。
- Gemini 配置使用已验证的 OpenAI 兼容 `/v1/chat/completions` 图片响应解析链路。
- API Key 只写入数据库，不通过 API 响应返回。
- 旧版 `users.api_key` 和 `users.model` 自动迁移为一条默认配置。
- 本次不改变固定的第三方 Base URL，仍由后端配置提供。

## 数据模型

新增 `api_key_configs` 表：

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `user_id` | 所属用户，级联删除 |
| `alias` | 用户可见别名，同一用户内唯一 |
| `api_key` | 加密边界之外的现有 SQLite 密钥字段，永不返回前端 |
| `provider_type` | `gpt` 或 `gemini` |
| `model` | 实际调用的模型名 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

在 `users` 表增加 `active_api_key_config_id`，用于保存当前选择的配置。迁移时将已有单值配置插入 `api_key_configs`，别名使用“默认配置”，并将其 ID 写入用户的当前配置字段。新用户注册时创建一条默认配置；空 API Key 也允许保存，便于先建立配置再补 Key。

## 后端接口

`GET /api/settings` 返回当前配置和配置列表：

```json
{
  "provider_name": "北海AI",
  "base_url": "https://sub.beibeihai.xyz/v1",
  "active_config_id": 1,
  "configs": [
    {
      "id": 1,
      "alias": "Gemini 1K",
      "provider_type": "gemini",
      "model": "gemini-3.1-flash-image-1K",
      "api_key_configured": true
    }
  ]
}
```

新增配置相关接口：

- `POST /api/settings/api-keys`：创建配置。
- `PATCH /api/settings/api-keys/{id}`：更新别名、Key、类型或模型；空 Key 表示保留原 Key。
- `DELETE /api/settings/api-keys/{id}`：删除配置；禁止删除最后一条配置。
- `PUT /api/settings/active`：更新当前配置 ID。

所有配置接口要求当前登录用户拥有目标配置。响应只返回 `api_key_configured` 布尔值，不返回 Key 原文。

## 生成路由

前端生成请求新增 `api_key_config_id`，后端根据该 ID 加载配置并校验归属。请求中保留前端当前的尺寸、质量和提示词字段，但不再由前端决定 API Key。

- `provider_type=gpt`：创建现有 `CompatibleProvider`，调用 `images.generate`。
- `provider_type=gemini`：创建 Gemini 兼容 Provider，调用 `chat.completions.create`，解析 Base64、`image_url` 和 Markdown 图片响应。

配置别名用于界面选择；历史记录继续保存真实模型名，避免别名修改后历史数据失去技术信息。

## 前端交互

设置页的接口配置区域改为配置列表：

- 每行显示别名、类型、模型和 Key 是否已配置。
- 新增/编辑表单包含别名、API Key、类型和模型四个字段。
- 编辑时 API Key 为空表示保持原值。
- 删除前进行确认，最后一条配置不可删除。
- 当前配置可以通过列表选择，并立即保存为 active 配置。

工作台模型下拉框改为显示配置别名。加载设置时使用 `active_config_id` 选中配置；生成时发送配置 ID。没有有效配置时显示配置提示，不发起生成请求。

## 错误处理

- 别名重复、模型为空、类型非法和 Key 长度超限由 Pydantic 校验并返回明确错误。
- 删除不存在或不属于当前用户的配置返回 404。
- 生成时配置被删除或无 Key 返回配置错误，不暴露 Key 内容。
- GPT/Gemini 上游错误继续沿用现有状态码和错误信息传递方式。

## 测试计划

- 数据库迁移保留旧用户配置，并为新用户创建默认配置。
- Repository 覆盖配置创建、更新、删除、别名唯一性和跨用户隔离。
- API 覆盖 Key 不回传、最后配置不可删除、active 配置切换和请求校验。
- Provider 覆盖 GPT Images 路由、Gemini Chat Completions 路由及图片响应解析。
- 前端覆盖配置列表、新增/编辑/删除、别名下拉框、active 配置和生成请求中的配置 ID。
- 运行后端测试、前端测试和前端构建。

