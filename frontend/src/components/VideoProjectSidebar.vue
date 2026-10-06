<script setup lang="ts">
import { ref } from "vue";
import { ChevronDown, ChevronRight, Film, Folder, Plus, Pencil, Trash2 } from "lucide-vue-next";
import type { ProjectSummary } from "./ProjectSidebar.vue";
import { activeVideoStatuses, videoStatusLabels } from "../video";
defineProps<{ projects: ProjectSummary[]; selectedProjectId: number | null; selectedTaskId: number | null }>();
const emit = defineEmits<{ 'select-project': [id: number]; 'new-video': [id: number]; 'create-project': []; 'rename-project': [project: ProjectSummary]; 'delete-project': [project: ProjectSummary]; 'open-video': [projectId: number, taskId: number] }>();
const expanded = ref<Record<number, boolean>>({});
</script>
<template>
  <aside class="project-sidebar" aria-label="视频项目列表">
    <div class="sidebar-heading"><div><span>视频工作区</span><h2>项目</h2></div><button class="icon-action" type="button" aria-label="新建项目" @click="emit('create-project')"><Plus :size="17" /></button></div>
    <div class="project-list"><section v-for="project in projects" :key="project.id" class="project-group" :class="{active: project.id === selectedProjectId}">
      <div class="project-row"><button class="project-select" type="button" @click="emit('select-project', project.id)"><Folder :size="16" /><span>{{ project.name }}</span><small>{{ project.video_history_count || 0 }}</small></button><button class="project-new-conversation" type="button" aria-label="新建视频草稿" @click="emit('new-video', project.id)"><Plus :size="15" /></button><button class="project-toggle" type="button" :aria-expanded="expanded[project.id] ?? project.id === selectedProjectId" aria-label="展开或收起视频历史" @click="expanded[project.id] = !(expanded[project.id] ?? project.id === selectedProjectId)"><ChevronDown v-if="expanded[project.id] ?? project.id === selectedProjectId" :size="15" /><ChevronRight v-else :size="15" /></button></div>
      <div v-if="expanded[project.id] ?? project.id === selectedProjectId" class="project-history">
        <p v-if="!project.video_history?.length" class="sidebar-muted">暂无视频任务</p>
        <button v-for="task in project.video_history || []" :key="task.id" class="history-select" type="button" :class="{ 'video-history-active': task.id === selectedTaskId, failed: task.status === 'failed' }" @click="emit('open-video', project.id, task.id)"><Film :size="14" /><span class="history-copy"><span class="history-prompt">{{ task.prompt }}</span><small class="history-provider-model">{{ task.model }}</small><small class="history-generation-meta">{{ activeVideoStatuses.has(task.status) ? '● ' : '' }}{{ videoStatusLabels[task.status] || task.status }} · {{ task.duration }} 秒 · {{ task.resolution }}</small></span></button>
        <div class="history-tools"><button class="text-action" type="button" @click="emit('rename-project', project)"><Pencil :size="13" />重命名</button><button class="text-action danger-text" type="button" @click="emit('delete-project', project)"><Trash2 :size="13" />删除项目</button></div>
      </div>
    </section></div>
  </aside>
</template>
<style scoped>.video-history-active { background:var(--prompt-snow-surface-muted); outline:1px solid var(--prompt-snow-border-strong); }</style>
