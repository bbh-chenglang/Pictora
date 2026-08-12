<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import { ChevronDown, ChevronRight, FileImage, Folder, LoaderCircle, MoreHorizontal, Pencil, Plus, Trash2, X } from "lucide-vue-next";

export type HistorySummary = {
  id: number;
  kind?: "generate" | "analyze";
  prompt: string;
  provider?: string;
  model: string;
  status: string;
  image_count?: number;
  size?: string | null;
  resolution?: string | null;
  created_at: string;
};
export type ProjectSummary = { id: number; name: string; history: HistorySummary[]; history_count: number };
export type RunningGenerationSummary = {
  id: number;
  projectId: number | null;
  prompt: string;
  model: string;
  size: string;
  resolution: string;
  elapsedMs: number;
};

const props = defineProps<{
  projects: ProjectSummary[];
  selectedProjectId: number | null;
  loading?: boolean;
  runningGenerations?: RunningGenerationSummary[];
  activeGenerationRunId?: number | null;
}>();
const emit = defineEmits<{
  "select-project": [id: number]; "new-conversation": [projectId: number]; "create-project": [];
  "rename-project": [project: ProjectSummary]; "delete-project": [project: ProjectSummary];
  "delete-history": [project: ProjectSummary, ids: number[]]; "open-history": [id: number];
  "open-generation": [id: number];
  "prefetch-history": [id: number];
  close: [];
}>();
const expanded = ref<Record<number, boolean>>({});
const projectExpanded = ref<Record<number, boolean>>({});
const selectedHistory = ref<Record<number, number[]>>({});
const menuProjectId = ref<number | null>(null);

function visibleHistory(project: ProjectSummary) {
  const finished = project.history.filter((item) => item.status !== "pending");
  return expanded.value[project.id] ? finished : finished.slice(0, 5);
}
function isProjectExpanded(project: ProjectSummary) {
  return projectExpanded.value[project.id] ?? project.id === props.selectedProjectId;
}
function toggleProject(project: ProjectSummary) {
  projectExpanded.value[project.id] = !isProjectExpanded(project);
}
function toggleHistory(project: ProjectSummary) { expanded.value[project.id] = !expanded.value[project.id]; }
function runningForProject(project: ProjectSummary) {
  return props.runningGenerations?.filter((run) => run.projectId === project.id) ?? [];
}
function formatDuration(milliseconds: number) {
  return `${(milliseconds / 1000).toFixed(2)} 秒`;
}
function historyProviderLabel(item: HistorySummary) {
  if (item.provider?.toLowerCase() === "gemini" || item.model.toLowerCase().includes("gemini")) return "Gemini";
  if (item.provider?.toLowerCase() === "grok" || item.model.toLowerCase().includes("grok")) return "Grok";
  return "OpenAI";
}
function historyAspectRatio(size?: string | null) {
  if (!size) return "未记录";
  const legacyRatios: Record<string, string> = {
    "1024x1024": "1:1",
    "1536x1024": "3:2",
    "1024x1536": "2:3",
    "1024x1792": "9:16",
    "1792x1024": "16:9",
    "720x1280": "9:16",
    "1280x720": "16:9",
  };
  return legacyRatios[size] ?? size;
}
function historyGenerationMeta(item: HistorySummary) {
  const provider = historyProviderLabel(item);
  const count = item.image_count ? ` · ${item.image_count}张` : "";
  if (provider === "Grok") {
    const resolution = item.resolution ? ` · 分辨率 ${item.resolution}` : "";
    return `比例 ${historyAspectRatio(item.size)}${resolution}${count}`;
  }
  if (provider === "Gemini") {
    const resolution = item.resolution ? ` · 分辨率 ${item.resolution}` : "";
    return `比例 ${historyAspectRatio(item.size)}${resolution}${count}`;
  }
  return `尺寸 ${item.size ?? "未记录"}${count}`;
}
function selected(project: ProjectSummary) { return selectedHistory.value[project.id] ?? []; }
function toggleHistorySelection(project: ProjectSummary, id: number) {
  const ids = new Set(selected(project));
  if (ids.has(id)) ids.delete(id); else ids.add(id);
  selectedHistory.value[project.id] = [...ids];
}
function deleteSelected(project: ProjectSummary) {
  const ids = selected(project);
  if (ids.length) emit("delete-history", project, ids);
}
function selectProject(project: ProjectSummary) {
  emit("select-project", project.id);
}
function openHistoryItem(id: number) {
  emit("open-history", id);
}
function openGeneration(id: number) {
  emit("open-generation", id);
}
function createProject() {
  emit("create-project");
  emit("close");
}
function startConversation(project: ProjectSummary) {
  emit("new-conversation", project.id);
  emit("close");
}
watch(() => props.projects, (projects) => {
  const currentHistoryIds = new Map(projects.map((project) => [project.id, new Set(project.history.map((item) => item.id))]));
  for (const [projectId, ids] of Object.entries(selectedHistory.value)) {
    const availableIds = currentHistoryIds.get(Number(projectId));
    if (!availableIds) {
      delete selectedHistory.value[Number(projectId)];
      continue;
    }
    selectedHistory.value[Number(projectId)] = ids.filter((id) => availableIds.has(id));
  }
}, { deep: true });
function closeMenuOnOutsideClick(event: MouseEvent) {
  if (!(event.target instanceof Element)) return;
  if (event.target.closest(".project-menu, [data-project-menu-trigger]")) return;
  menuProjectId.value = null;
}
onMounted(() => document.addEventListener("click", closeMenuOnOutsideClick));
onUnmounted(() => document.removeEventListener("click", closeMenuOnOutsideClick));
</script>

<template>
  <aside class="project-sidebar" aria-label="项目列表">
    <div class="sidebar-heading"><div><span>工作区</span><h2>项目</h2></div><div class="sidebar-heading-actions"><button type="button" class="icon-action" title="新建项目" aria-label="新建项目" @click="createProject"><Plus :size="17" /></button><button type="button" class="icon-action mobile-sidebar-close" title="关闭项目列表" aria-label="关闭项目列表" @click="emit('close')"><X :size="17" /></button></div></div>
    <p v-if="loading" class="sidebar-muted">正在加载项目...</p>
    <div v-else class="project-list">
      <section v-for="project in projects" :key="project.id" :data-project-id="project.id" class="project-group" :class="{ active: project.id === selectedProjectId }">
        <div class="project-row">
          <button type="button" class="project-select" @pointerenter="project.history[0] && emit('prefetch-history', project.history[0].id)" @focus="project.history[0] && emit('prefetch-history', project.history[0].id)" @click="selectProject(project)"><Folder :size="16" /><LoaderCircle v-if="runningForProject(project).length" class="spin project-run-indicator" :size="13" /><span>{{ project.name }}</span><small>{{ project.history_count }}</small></button>
          <button type="button" class="project-new-conversation" :title="`在“${project.name}”中新建对话`" :aria-label="`在“${project.name}”中新建对话`" @click.stop="startConversation(project)"><Plus :size="15" /></button>
          <button type="button" class="project-toggle" :aria-label="isProjectExpanded(project) ? '收起项目' : '展开项目'" :aria-expanded="isProjectExpanded(project)" @click.stop="toggleProject(project)"><ChevronDown v-if="isProjectExpanded(project)" :size="15" /><ChevronRight v-else :size="15" /></button>
          <button type="button" class="icon-action" data-project-menu-trigger title="项目操作" aria-label="项目操作" @click="menuProjectId = menuProjectId === project.id ? null : project.id"><MoreHorizontal :size="17" /></button>
        </div>
        <div v-if="menuProjectId === project.id" class="project-menu project-menu-overlay"><button type="button" @click="startConversation(project); menuProjectId = null"><Plus :size="14" />新建对话</button><button type="button" data-project-action="rename" @click="emit('rename-project', project); menuProjectId = null"><Pencil :size="14" />重命名</button><button type="button" class="danger-text" @click="emit('delete-project', project); menuProjectId = null"><Trash2 :size="14" />删除项目</button></div>
        <div v-if="isProjectExpanded(project)" class="project-history">
          <p v-if="!project.history.length && !runningForProject(project).length" class="sidebar-muted">暂无历史记录</p>
          <button
            v-for="run in runningForProject(project)"
            :key="`running-${run.id}`"
            type="button"
            class="running-generation"
            :class="{ active: run.id === activeGenerationRunId }"
            @click="openGeneration(run.id)"
          >
            <LoaderCircle class="spin" :size="14" />
            <span class="history-copy">
              <span class="history-prompt">{{ run.prompt }}</span>
              <small class="history-provider-model">{{ run.model }}</small>
              <small class="history-generation-meta">正在生成 · {{ formatDuration(run.elapsedMs) }}</small>
            </span>
          </button>
          <label v-for="item in visibleHistory(project)" :key="item.id" class="history-row">
            <input class="history-checkbox" type="checkbox" :checked="selected(project).includes(item.id)" @click.stop @change="toggleHistorySelection(project, item.id)" />
            <button type="button" class="history-select" :class="{ failed: item.status === 'failed' }" @pointerenter="emit('prefetch-history', item.id)" @focus="emit('prefetch-history', item.id)" @click="openHistoryItem(item.id)">
              <FileImage :size="14" />
              <span class="history-copy">
                <span class="history-prompt">{{ item.prompt }}</span>
                <small class="history-provider-model" :title="`${historyProviderLabel(item)} · ${item.model}`">{{ historyProviderLabel(item) }} · {{ item.model }}</small>
                <small v-if="item.kind === 'analyze'" class="history-generation-meta">图片分析</small>
                <small v-else class="history-generation-meta">{{ historyGenerationMeta(item) }}</small>
              </span>
            </button>
          </label>
          <div class="history-tools">
            <button v-if="project.history.length > 5" type="button" class="text-action" @click="toggleHistory(project)">{{ expanded[project.id] ? "收起" : `展开全部（${project.history.length}）` }}<ChevronDown v-if="expanded[project.id]" :size="14" /><ChevronRight v-else :size="14" /></button>
            <button v-if="selected(project).length" type="button" class="text-action danger-text" @click="deleteSelected(project)">删除已选（{{ selected(project).length }}）</button>
          </div>
        </div>
      </section>
    </div>
  </aside>
</template>
