<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { ChevronDown, ChevronRight, FileImage, Folder, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-vue-next";

export type HistorySummary = {
  id: number; prompt: string; model: string; status: string; created_at: string;
};
export type ProjectSummary = { id: number; name: string; history: HistorySummary[]; history_count: number };

const props = defineProps<{ projects: ProjectSummary[]; selectedProjectId: number | null; loading?: boolean }>();
const emit = defineEmits<{
  "select-project": [id: number]; "new-conversation": []; "create-project": [];
  "rename-project": [project: ProjectSummary]; "delete-project": [project: ProjectSummary];
  "delete-history": [project: ProjectSummary, ids: number[]]; "open-history": [id: number];
}>();
const expanded = ref<Record<number, boolean>>({});
const projectExpanded = ref<Record<number, boolean>>({});
const selectedHistory = ref<Record<number, number[]>>({});
const menuProjectId = ref<number | null>(null);

function visibleHistory(project: ProjectSummary) {
  return expanded.value[project.id] ? project.history : project.history.slice(0, 5);
}
function isProjectExpanded(project: ProjectSummary) {
  return projectExpanded.value[project.id] ?? project.id === props.selectedProjectId;
}
function toggleProject(project: ProjectSummary) {
  projectExpanded.value[project.id] = !isProjectExpanded(project);
}
function toggleHistory(project: ProjectSummary) { expanded.value[project.id] = !expanded.value[project.id]; }
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
    <div class="sidebar-heading"><div><span>工作区</span><h2>项目</h2></div><button type="button" class="icon-action" title="新建项目" aria-label="新建项目" @click="emit('create-project')"><Plus :size="17" /></button></div>
    <p v-if="loading" class="sidebar-muted">正在加载项目...</p>
    <div v-else class="project-list">
      <section v-for="project in projects" :key="project.id" :data-project-id="project.id" class="project-group" :class="{ active: project.id === selectedProjectId }">
        <div class="project-row">
          <button type="button" class="project-select" @click="emit('select-project', project.id)"><Folder :size="16" /><span>{{ project.name }}</span><small>{{ project.history_count }}</small></button>
          <button type="button" class="project-toggle" :aria-label="isProjectExpanded(project) ? '收起项目' : '展开项目'" :aria-expanded="isProjectExpanded(project)" @click.stop="toggleProject(project)"><ChevronDown v-if="isProjectExpanded(project)" :size="15" /><ChevronRight v-else :size="15" /></button>
          <button type="button" class="icon-action" data-project-menu-trigger title="项目操作" aria-label="项目操作" @click="menuProjectId = menuProjectId === project.id ? null : project.id"><MoreHorizontal :size="17" /></button>
        </div>
        <div v-if="menuProjectId === project.id" class="project-menu project-menu-overlay"><button type="button" @click="emit('new-conversation'); menuProjectId = null"><Plus :size="14" />新建对话</button><button type="button" data-project-action="rename" @click="emit('rename-project', project); menuProjectId = null"><Pencil :size="14" />重命名</button><button type="button" class="danger-text" @click="emit('delete-project', project); menuProjectId = null"><Trash2 :size="14" />删除项目</button></div>
        <div v-if="isProjectExpanded(project)" class="project-history">
          <p v-if="!project.history.length" class="sidebar-muted">暂无历史记录</p>
          <label v-for="item in visibleHistory(project)" :key="item.id" class="history-row">
            <input class="history-checkbox" type="checkbox" :checked="selected(project).includes(item.id)" @click.stop @change="toggleHistorySelection(project, item.id)" />
            <button type="button" class="history-select" :class="{ failed: item.status === 'failed' }" @click="emit('open-history', item.id)"><FileImage :size="14" /><span>{{ item.prompt }}</span></button>
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
