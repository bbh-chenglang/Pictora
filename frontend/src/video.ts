export type MaterialType = "image" | "video" | "audio";
export type VideoMaterial = { type: MaterialType; name: string; asset_id?: string; url?: string; preview_url?: string; duration_seconds?: number | null };
export type VideoModel = {
  id: string; default_duration: number; default_resolution: string; default_ratio: string;
  ratios: string[]; durations_by_resolution: Record<string, number[]>;
  reference_limits: Record<MaterialType, number | null>;
  max_total_materials: number | null; max_video_duration_seconds: number | null;
};
export type VideoFeatures = { api_ready?: boolean; assets_ready: boolean; storage_configured: boolean; storage_ready: boolean; media_tools_ready: boolean; catalog_source: string; api_base_url: string; notes: string[] };
export type VideoKey = { id: number; alias: string; model: string; api_key_configured: boolean };
export type VideoHistory = { id: number; prompt: string; model: string; status: string; upstream_status?: string | null; duration: number; resolution: string; ratio: string; created_at: string };
export type VideoResult = { id: number; stored: number; filename: string; byte_size: number | null; duration_seconds: number | null; play_url: string; download_url: string };
export type VideoTask = VideoHistory & { started_at?: string | null; completed_at?: string | null; updated_at?: string | null; project_id: number; request_id: string; api_key_config_id: number | null; upstream_task_id: string | null; progress: number | null; tracking_abandoned: number; error_message: string | null; error_code: string | null; materials: VideoMaterial[]; results: VideoResult[] };
export type VideoRequestState = { state: "missing" | "closed" | "accepted"; task: VideoTask | null };
export type ApiFetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export const materialLabels: Record<MaterialType, string> = { image: "图片", video: "视频", audio: "音频" };
export const activeVideoStatuses = new Set(["queued", "submitting", "running", "saving"]);
export const trackedVideoStatuses = new Set([...activeVideoStatuses, "polling_paused", "storage_failed", "submission_unknown"]);
export const videoStatusLabels: Record<string, string> = {
  queued: "本地排队", submitting: "提交上游中", running: "上游生成中", saving: "已生成，正在保存",
  completed: "已保存完成", failed: "生成失败", polling_paused: "查询暂停", storage_failed: "已生成，保存失败",
  submission_unknown: "提交结果待确认", abandoned: "已放弃本地追踪", expired: "上游任务已过期",
};
export function materialIssue(model: VideoModel | undefined, material: VideoMaterial, all: VideoMaterial[]): string {
  if (!model) return "模型能力尚未加载";
  const limit = model.reference_limits[material.type];
  if (limit == null) return "该素材类型的能力尚未确认";
  if (limit === 0) return "此模型不支持该素材类型";
  if (all.filter(item => item.type === material.type).length > limit) return "超过该类型的素材数量上限（" + limit + "）";
  if (!material.name.trim()) return "请填写素材名称";
  if (all.filter(item => item.name.trim() === material.name.trim()).length > 1) return "素材名称重复";
  const source = material.asset_id || material.url;
  if (!source || all.filter(item => (item.asset_id || item.url) === source).length > 1) return "素材为空或重复";
  if (material.url) {
    try { const u = new URL(material.url); if (u.protocol !== "https:" || u.username || u.password || u.hash || (u.port && u.port !== "443")) return "仅支持不带凭据的 HTTPS 链接"; }
    catch { return "请输入有效的 HTTPS 链接"; }
  }
  return "";
}
export function videoValidation(model: VideoModel | undefined, duration: number, resolution: string, ratio: string, materials: VideoMaterial[]): string[] {
  if (!model) return ["模型目录尚未加载"];
  const issues: string[] = [];
  if (!model.durations_by_resolution[resolution]?.includes(duration) || !model.ratios.includes(ratio)) issues.push("参数不属于该模型的有效档位");
  for (const material of materials) { const issue = materialIssue(model, material, materials); if (issue) issues.push(material.name + "：" + issue); }
  if (model.max_total_materials != null && materials.length > model.max_total_materials) issues.push("所有素材合计最多 " + model.max_total_materials + " 个");
  if (model.max_video_duration_seconds != null && materials.reduce((total, item) => total + (item.type === "video" ? item.duration_seconds || 0 : 0), 0) > model.max_video_duration_seconds) issues.push("参考视频真实时长合计不能超过 " + model.max_video_duration_seconds + " 秒");
  return issues;
}
export class VideoApiError extends Error {
  constructor(message: string, public readonly status: number, public readonly code?: string) {
    super(message);
    this.name = "VideoApiError";
  }
}
export async function videoJson<T>(fetcher: ApiFetch, base: string, route: string, init?: RequestInit): Promise<T> {
  const response = await fetcher(base + route, init);
  // A non-JSON 4xx is still a definitive rejection, whereas an unreadable 202/5xx
  // must remain ambiguous to the caller's persistent idempotency protection.
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new VideoApiError(data?.error?.message || (response.status === 422 ? "参数校验失败，请检查模型与素材" : "视频请求失败（" + response.status + "）"), response.status, data?.error?.code);
  if (data === null && response.status !== 204) throw new Error("视频响应无法读取，请用原请求 UUID 核对任务");
  return data as T;
}
export function jsonBody(body: unknown): RequestInit { return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }; }

// SQLite CURRENT_TIMESTAMP values are UTC, even when they have no explicit zone.
export function videoTimestamp(value?: string | null): number | null {
  if (!value) return null;
  const normalized = value.trim().replace(" ", "T");
  const timestamp = Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized) ? normalized : normalized + "Z");
  return Number.isFinite(timestamp) ? timestamp : null;
}
export function videoElapsedMs(task: VideoTask, now: number): number | null {
  const start = videoTimestamp(task.created_at) ?? videoTimestamp(task.started_at);
  const finish = videoTimestamp(task.completed_at)
    ?? (trackedVideoStatuses.has(task.status) && !task.tracking_abandoned ? now : videoTimestamp(task.updated_at));
  return start === null || finish === null ? null : Math.max(0, finish - start);
}
export function formatVideoElapsed(elapsedMs: number): string {
  const seconds = Math.floor(elapsedMs / 1000);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor(seconds / 60) % 60;
  return (hours ? String(hours).padStart(2, "0") + ":" : "")
    + String(hours ? minutes : Math.floor(seconds / 60)).padStart(2, "0") + ":"
    + String(seconds % 60).padStart(2, "0");
}



