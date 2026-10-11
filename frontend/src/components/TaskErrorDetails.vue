<script setup lang="ts">
import { computed, ref } from "vue";
import { Copy } from "lucide-vue-next";
import { errorStageLabels, type TaskErrorDetails } from "../errorDetails";

const props = defineProps<{
  details?: TaskErrorDetails | null; errorCode?: string | null; message?: string | null;
  taskId?: string | number | null; requestId?: string | null; upstreamTaskId?: string | null;
  model?: string | null; position?: number;
}>();
const copyStatus = ref("");
const failure = computed(() => props.details?.failures?.find(item => item.position === props.position));
const details = computed(() => failure.value
  ? failure.value.error_details ?? { stage: props.details?.stage, local_message: failure.value.error_message }
  : props.details);
const code = computed(() => failure.value?.error_code ?? props.errorCode);
const fields = computed(() => [
  ["失败阶段", details.value?.stage ? errorStageLabels[details.value.stage] || details.value.stage : "未记录（旧任务或接口未提供）"],
  ["具体原因", details.value?.upstream_message || details.value?.local_message || failure.value?.error_message || props.message],
  ["错误码", code.value], ["HTTP 状态", details.value?.http_status],
  ["上游错误码", details.value?.upstream_code], ["相关参数", details.value?.parameter],
  ["存储服务错误码", details.value?.service_code],
  ["任务 ID", props.taskId], ["模型", props.model],
  ["图片位置", props.position !== undefined ? `第 ${props.position + 1} 张` : undefined],
  ["异常类型", details.value?.exception_type],
  ["请求 ID", props.requestId], ["上游请求 ID", details.value?.upstream_request_id],
  ["上游任务 ID", details.value?.upstream_task_id || props.upstreamTaskId],
  ["原因状态", details.value?.reason_provided === false ? "上游未提供具体失败原因" : undefined],
  ["排查建议", details.value?.suggestion],
].filter(([, value]) => value !== undefined && value !== null && value !== ""));
async function copyDetails() {
  try {
    await navigator.clipboard.writeText(fields.value.map(([label, value]) => `${label}：${value}`).join("\n"));
    copyStatus.value = "已复制";
  } catch { copyStatus.value = "复制失败，请手动选择详情文字"; }
}
</script>
<template>
  <details class="task-error-details">
    <summary>查看失败详情</summary>
    <dl><template v-for="([label, value]) in fields" :key="String(label)"><dt>{{ label }}</dt><dd>{{ value }}</dd></template></dl>
    <div class="diagnostic-actions"><button type="button" class="text-action" @click="copyDetails"><Copy :size="13" />复制错误信息</button><span role="status">{{ copyStatus }}</span></div>
  </details>
</template>
<style scoped>
.task-error-details{margin:10px 0;padding:10px 12px;border:1px solid var(--prompt-snow-border, #d5dce8);border-radius:8px;font-size:12px;line-height:1.65;color:var(--prompt-snow-text, var(--text));min-width:0;}
summary{cursor:pointer;font-weight:600;}summary:focus-visible{outline:2px solid var(--blue);outline-offset:4px;}
dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 12px;margin:12px 0;max-height:320px;overflow:auto;}
dt{color:var(--prompt-snow-text-muted, var(--muted));}dd{margin:0;overflow-wrap:anywhere;white-space:pre-wrap;user-select:text;}
.diagnostic-actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center;}.diagnostic-actions button{display:inline-flex;align-items:center;gap:5px;font-size:12px;}.diagnostic-actions span{color:var(--prompt-snow-text-muted, var(--muted));}
@media(max-width:420px){dl{grid-template-columns:1fr;gap:2px;}dd{margin-bottom:8px;}}
</style>
