<script setup lang="ts">
import { computed, ref } from "vue";
import { ChevronDown, ChevronRight, FileImage, Folder, MoreHorizontal, Plus, Trash2 } from "lucide-vue-next";

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
const selectedHistory = ref<Record<number, number[]>>({});
const menuProjectId = ref<number | null>(null);
const selectedProject = computed(() => props.projects.find((item) => item.id === props.selectedProjectId));

function visibleHistory(project: ProjectSummary) {
  return expanded.value[project.id] ? project.history : project.history.slice(0, 5);
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
</script>

<template>
  <aside class="project-sidebar" aria-label="项目列表">
    <div class="sidebar-heading"><div><span>工作区</span><h2>项目</h2></div><button type="button" class="icon-action" title="新建项目" aria-label="新建项目" @click="emit('create-project')"><Plus :size="17" /></button></div>
    <button type="button" class="new-conversation" :disabled="!selectedProject" @click="emit('new-conversation')"><Plus :size="16" />新建对话</button>
    <p v-if="loading" class="sidebar-muted">正在加载项目...</p>
    <div v-else class="project-list">
      <section v-for="project in projects" :key="project.id" class="project-group" :class="{ active: project.id === selectedProjectId }">
        <div class="project-row">
          <button type="button" class="project-select" @click="emit('select-project', project.id)"><Folder :size="16" /><span>{{ project.name }}</span><small>{{ project.history_count }}</small></button>
          <button type="button" class="icon-action" title="项目操作" aria-label="项目操作" @click="menuProjectId = menuProjectId === project.id ? null : project.id"><MoreHorizontal :size="17" /></button>
          <div v-if="menuProjectId === project.id" class="project-menu"><button type="button" @click="emit('rename-project', project); menuProjectId = null">重命名</button><button type="button" class="danger-text" @click="emit('delete-project', project); menuProjectId = null"><Trash2 :size="14" />删除项目</button></div>
        </div>
        <div v-if="project.id === selectedProjectId" class="project-history">
          <p v-if="!project.history.length" class="sidebar-muted">暂无历史记录</p>
          <label v-for="item in visibleHistory(project)" :key="item.id" class="history-row">
            <input type="checkbox" :checked="selected(project).includes(item.id)" @click.stop @change="toggleHistorySelection(project, item.id)" />
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
