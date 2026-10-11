export type TaskErrorDetails = {
  stage?: string; upstream_code?: string; upstream_message?: string; local_message?: string;
  parameter?: string; upstream_request_id?: string; upstream_task_id?: string;
  http_status?: number; reason_provided?: boolean; suggestion?: string; exception_type?: string;
  image_position?: number | null;
  service_code?: string;
  failures?: { position: number; error_code: string; error_message: string; error_details?: TaskErrorDetails | null }[];
};
export const errorStageLabels: Record<string, string> = {
  validation: "参数校验", reference_storage: "参考素材保存", submission: "提交上游",
  generation: "上游生成", query: "查询任务", download: "结果下载与校验",
  storage: "结果保存", completion: "任务收尾",
  response: "上游响应解析",
};

export function failureMessage(details: TaskErrorDetails | null | undefined, position: number, fallback: string): string {
  const failure = details?.failures?.find(item => item.position === position);
  const cause = failure ? failure.error_details : details;
  return cause?.upstream_message || cause?.local_message || failure?.error_message || fallback;
}

export function validationMessage(data: any): string | undefined {
  if (typeof data?.detail === "string") return data.detail;
  if (!Array.isArray(data?.detail)) return undefined;
  return data.detail.slice(0, 5).map((item: any) => {
    const parameter = Array.isArray(item?.loc) ? item.loc.filter((part: unknown) => part !== "body").join(".") : "";
    return typeof item?.msg === "string" ? (parameter ? `${parameter}：${item.msg}` : item.msg) : "";
  }).filter(Boolean).join("；") || undefined;
}

export function apiFailureDetails(data: any, status: number, fallback: string): TaskErrorDetails {
  const error = data?.error ?? data?.detail?.error;
  if (error?.details && typeof error.details === "object") return error.details;
  return {
    stage: status >= 400 && status < 500 ? "validation" : "submission",
    http_status: status, local_message: error?.message || validationMessage(data) || fallback,
    parameter: Array.isArray(data?.detail) ? data.detail.slice(0, 5).map((item: any) => item?.loc?.join(".")).filter(Boolean).join("；") : undefined,
    suggestion: status === 422 ? "请检查相关参数的取值和参考素材，再提交。" : "请结合错误码排查；提交结果不确定时先核对原任务。",
  };
}
