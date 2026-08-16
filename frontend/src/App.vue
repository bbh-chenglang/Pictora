<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import {
  ArrowLeft,
  BookmarkPlus,
  CircleAlert,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Download,
  ExternalLink,
  Grid3X3,
  ImagePlus,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCw,
  KeyRound,
  Settings,
  ShieldCheck,
  Snowflake,
  Sparkles,
  Trash2,
  Upload,
  UserRound,
  X,
} from "lucide-vue-next";
import ProjectSidebar, {
  type ProjectSummary,
  type RunningGenerationSummary,
} from "./components/ProjectSidebar.vue";
import ConfirmDialog from "./components/ConfirmDialog.vue";
import FlowingGridBackground from "./components/FlowingGridBackground.vue";
import ProjectDialog from "./components/ProjectDialog.vue";
import SnowfallBackground from "./components/SnowfallBackground.vue";
import SkillsView, { type SkillWorkflow } from "./components/SkillsView.vue";
import PromptsView, { type PromptEntry } from "./components/PromptsView.vue";
import PromptEditorDialog, { type PromptForm } from "./components/PromptEditorDialog.vue";
import PromptPickerPopover, { type PromptPickerEntry } from "./components/PromptPickerPopover.vue";
import pictoraMark from "./assets/pictora-mark.svg";

type Provider = { id: string; label: string; models: string[] };
type CapabilityOption = { value: string; label: string };
type ModelCapability = {
  provider_type: ApiKeyProvider;
  model: string;
  label: string;
  max_output_count: number;
  max_reference_images: number;
  sizes: CapabilityOption[];
  aspect_ratios: string[];
  resolutions: string[];
  qualities: CapabilityOption[];
  output_formats: string[];
  backgrounds: string[];
  supports_output_compression: boolean;
  moderation_levels: string[];
  default_size?: string | null;
  default_aspect_ratio?: string | null;
  default_resolution?: string | null;
  default_quality: string;
};
type ApiKeyProvider = "gpt" | "gemini" | "grok";
type BackgroundEffect = "gravity-grid" | "snowfall";
type UpdateStatus = "idle" | "checking" | "current" | "available" | "error";
type CurrentView = "workspace" | "settings" | "admin" | "skills" | "prompts";
type ApiKeyConfig = {
  id: number;
  alias: string;
  provider_type: ApiKeyProvider;
  model: string;
  api_key_configured: boolean;
};
type AdminUser = {
  id: number;
  username: string;
  email: string;
  is_admin: boolean;
  password_status: string;
  created_at: string;
  last_login_at: string | null;
  last_activity_at: string | null;
  last_used_at: string | null;
  usage_count: number;
  generation_count: number;
  analysis_count: number;
  total_elapsed_ms: number;
  models_used: string[];
};
type AdminUsage = {
  id: number;
  kind: "generate" | "analyze";
  status: "pending" | "completed" | "failed";
  provider: string;
  model: string;
  detail: string;
  image_count: number;
  size: string | null;
  resolution: string | null;
  elapsed_ms: number | null;
  created_at: string;
  completed_at: string | null;
};
type AdminUserPage = {
  items: AdminUser[];
  total: number;
  result_total: number;
  admin_total: number;
  usage_total: number;
  page: number;
  page_size: number;
};
type DiscoveredModel = { id: string; provider_type: ApiKeyProvider };
type ApiKeyTestResult = {
  message: string;
  models: DiscoveredModel[];
};
type ApiKeyConfigForm = {
  alias: string;
  api_key: string;
  provider_type: ApiKeyProvider | null;
  model: string;
};
type ImageResult = {
  url?: string | null;
  thumbnail_url?: string | null;
  base64_data?: string | null;
  revised_prompt?: string | null;
  generation_time_ms?: number | null;
  history_id?: number;
  history_image_id?: number;
  batch_id?: number | null;
  batch_position?: number | null;
};
type GenerationViewSpec = {
  key: string;
  label: string;
  prompt: string;
};
type HistorySummary = {
  id: number;
  kind: "generate" | "analyze";
  status: "pending" | "completed" | "failed";
  prompt: string;
  provider: string;
  model: string;
  detail: string;
  size?: string | null;
  resolution?: string | null;
  image_count: number;
  elapsed_ms?: number | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
};
type HistoryImage = {
  id: number;
  batch_id?: number | null;
  role: "reference" | "generated";
  mime_type: string;
  filename?: string | null;
  position: number;
  batch_position?: number | null;
  url: string;
  thumbnail_url?: string | null;
  reference_category?: ReferenceCategory | null;
};
type GenerationBatchSummary = {
  id: number;
  status: "pending" | "completed" | "failed";
  image_count: number;
  generated_count: number;
  elapsed_ms?: number | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  deleted_positions?: number[];
  cancelled_positions?: number[];
  views?: GenerationViewSpec[];
};
type HistoryDetail = HistorySummary & {
  analysis_text?: string | null;
  completed_at?: string | null;
  images: HistoryImage[];
  batches?: GenerationBatchSummary[];
};
type GenerationBatchDetail = GenerationBatchSummary & {
  history_id: number;
  images: HistoryImage[];
};
type GenerationTaskDetail = {
  id: number;
  history_id: number;
  project_id?: number;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  batch_id?: number | null;
  api_key_config_id?: number | null;
  prompt?: string;
  provider?: string;
  model?: string;
  detail?: string;
  image_count?: number;
  generated_count?: number;
  images?: HistoryImage[];
  size?: string | null;
  resolution?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at?: string;
  deleted_positions?: number[];
  cancelled_positions?: number[];
  views?: GenerationViewSpec[];
};
type ReferenceCategory = "person" | "environment" | "object";
type ReferencePreview = {
  key: string;
  category: ReferenceCategory;
  name: string;
  url: string;
  file: File | null;
};
type ReferenceFileSnapshot = {
  file: File;
  category: ReferenceCategory;
};
type HistoryImageEditSnapshot = {
  history_id: number;
  image_id: number;
  api_key_config_id?: number | null;
  prompt: string;
  provider: string;
  model: string;
  detail: string;
  image_count: number;
  size?: string | null;
  resolution?: string | null;
  output_format?: string | null;
  background?: string | null;
  output_compression?: number | null;
  moderation?: string | null;
  view_label?: string | null;
  references: Array<{
    id: number;
    category: ReferenceCategory;
    mime_type: string;
    filename?: string | null;
    position: number;
    url: string;
  }>;
};

const LEGACY_SIZE_TO_ASPECT_RATIO: Record<string, string> = {
  "1024x1024": "1:1",
  "1536x1024": "3:2",
  "1024x1536": "2:3",
  "1024x1792": "9:16",
  "1792x1024": "16:9",
  "720x1280": "9:16",
  "1280x720": "16:9",
};
const REFERENCE_CATEGORIES: Array<{
  id: ReferenceCategory;
  label: string;
}> = [
  { id: "person", label: "人物" },
  { id: "environment", label: "环境" },
  { id: "object", label: "物品" },
];
type MultiViewTarget = "person" | "object";
type MultiViewPreset = { key: string; label: string; instruction: string };
const MULTI_VIEW_PRESETS: MultiViewPreset[] = [
  { key: "front", label: "正面", instruction: "相机正对主体，完整展示正面" },
  { key: "left_three_quarter", label: "左前 45°", instruction: "相机位于主体左前方约 45 度" },
  { key: "right_three_quarter", label: "右前 45°", instruction: "相机位于主体右前方约 45 度" },
  { key: "left_profile", label: "左侧面", instruction: "相机正对主体左侧，展示完整左侧面" },
  { key: "right_profile", label: "右侧面", instruction: "相机正对主体右侧，展示完整右侧面" },
  { key: "back", label: "背面", instruction: "相机位于主体正后方，完整展示背面" },
  { key: "top", label: "俯视", instruction: "相机从主体上方向下俯视" },
  { key: "low", label: "仰视", instruction: "相机从主体下方向上仰视" },
];
const DEFAULT_MULTI_VIEW_KEYS = ["front", "left_three_quarter", "right_three_quarter", "back"];
const SUPPORTED_REFERENCE_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);
type ParameterMenu = "apiKey" | "model" | "size" | "resolution" | "quality" | "count";
type GenerationRun = {
  controller: AbortController;
  taskId: number | null;
  batchId: number | null;
  conversationId: number | null;
  startedAt: number;
  elapsedMs: number;
  timer?: number;
  polling: boolean;
  taskApi: boolean;
  projectId: number | null;
  provider: string;
  model: string;
  apiKeyConfigId: number | null;
  prompt: string;
  batchPrompts: string;
  views: GenerationViewSpec[];
  imageCount: number;
  quality: string;
  size: string;
  resolution: string;
  referenceFiles: ReferenceFileSnapshot[];
  images: ImageResult[];
  failureCount: number;
  error: string;
  state: "running" | "failed" | "cancelled";
  deletedPositions: Set<number>;
  cancelledPositions: Set<number>;
};
type HistoryFailureGroup = {
  historyId: number;
  batchId: number;
  positions: number[];
  message: string;
  state: "failed" | "cancelled";
  elapsedMs?: number | null;
  views: GenerationViewSpec[];
};
type GenerationDisplayCard =
  | {
      key: string;
      kind: "image";
      batchId: number | null;
      slotPosition: number;
      image: ImageResult;
    }
  | {
      key: string;
      kind: "run";
      batchId: number | null;
      slotPosition: number;
      runId: number;
      run: GenerationRun;
    }
  | {
      key: string;
      kind: "history-failure";
      batchId: number;
      slotPosition: number;
      group: HistoryFailureGroup;
    };

function rememberGenerationBatchViews(batchId: number | null | undefined, views: GenerationViewSpec[] | undefined) {
  if (batchId == null || !views?.length) return;
  generationBatchViews.value = { ...generationBatchViews.value, [batchId]: views };
}

function rememberHistoryViews(data: HistoryDetail) {
  for (const batch of data.batches ?? []) rememberGenerationBatchViews(batch.id, batch.views);
}

function cardViewLabel(card: GenerationDisplayCard) {
  if (card.kind === "run") return card.run.views[card.slotPosition]?.label ?? "";
  if (card.kind === "history-failure") return card.group.views[card.slotPosition]?.label ?? "";
  if (card.batchId === null) return "";
  return generationBatchViews.value[card.batchId]?.[card.slotPosition]?.label ?? "";
}

const providers = ref<Provider[]>([]);
const capabilities = ref<ModelCapability[]>([]);
const provider = ref("compatible");
const model = ref<string>("");
const prompt = ref("");
const batchPrompts = ref("");
const imageCount = ref(1);
const regularImageCount = ref(1);
const multiViewEnabled = ref(false);
const multiViewTarget = ref<MultiViewTarget>("person");
const selectedMultiViewKeys = ref<string[]>([...DEFAULT_MULTI_VIEW_KEYS]);
const customMultiViews = ref<Array<{ key: string; label: string }>>([]);
const customMultiViewInput = ref("");
const multiViewInputError = ref("");
const quality = ref("auto");
const size = ref<string>("");
const resolution = ref<string>("");
const referencePreviews = ref<ReferencePreview[]>([]);
const referenceDragActiveCategory = ref<ReferenceCategory | null>(null);
const generated = ref<ImageResult[]>([]);
const deletingImageIds = ref<number[]>([]);
const deletingSlotKeys = ref<string[]>([]);
const cancellingSlotKeys = ref<string[]>([]);
const modifyingImageIds = ref<number[]>([]);
const busy = ref<"generate" | "analyze" | "">("");
const generationSubmitting = ref(false);
const error = ref("");
const apiKeyConfigured = ref(false);
const history = ref<HistorySummary[]>([]);
const historyError = ref("");
const projects = ref<ProjectSummary[]>([]);
const selectedProjectId = ref<number | null>(null);
const projectError = ref("");
const projectDialogMode = ref<"create" | "rename" | null>(null);
const projectDialogProject = ref<ProjectSummary | null>(null);
const confirmAction = ref<"project" | "history" | "api-key" | "image" | null>(null);
const confirmProject = ref<ProjectSummary | null>(null);
const confirmHistoryIds = ref<number[]>([]);
const confirmConfig = ref<ApiKeyConfig | null>(null);
const confirmImage = ref<{ item: ImageResult; slotPosition?: number } | null>(null);
const actionBusy = ref(false);
const activeHistoryId = ref<number | null>(null);
const currentConversationId = ref<number | null>(null);
const lightboxUrl = ref("");
const openParameterMenu = ref<ParameterMenu | null>(null);
const authView = ref<"checking" | "login" | "register" | "workspace">("checking");
const username = ref("");
const email = ref("");
const verificationCode = ref("");
const password = ref("");
const passwordConfirmation = ref("");
const currentUsername = ref("");
const currentEmail = ref("");
const currentIsAdmin = ref(false);
const profileUsername = ref("");
const profileStatus = ref("");
const profileSaving = ref(false);
const authError = ref("");
const authSubmitting = ref(false);
const verificationSending = ref(false);
const verificationCooldown = ref(0);
const currentView = ref<CurrentView>(resolveCurrentView());
const apiKeyConfigs = ref<ApiKeyConfig[]>([]);
const activeApiKeyConfigId = ref<number | null>(null);
const legacySettingsMode = ref(false);
const settingsApiKey = ref("");
const configForm = ref<ApiKeyConfigForm>({ alias: "", api_key: "", provider_type: null, model: "" });
const editingConfigId = ref<number | null>(null);
const showConfigForm = ref(false);
const discoveredModels = ref<DiscoveredModel[]>([]);
const discoveringModels = ref(false);
const availableModels = ref<DiscoveredModel[]>([]);
const loadingConfigModels = ref(false);
const testingConfigId = ref<number | null>(null);
const apiKeyTestResults = ref<Record<number, ApiKeyTestResult>>({});
const expandedApiKeyModelLists = ref<Record<number, boolean>>({});
const settingsConfigError = ref("");
const oldPassword = ref("");
const newPassword = ref("");
const newPasswordConfirmation = ref("");
const feedbackMessage = ref("");
const feedbackContact = ref("");
const feedbackStatus = ref("");
const feedbackSubmitting = ref(false);
const adminUsers = ref<AdminUser[]>([]);
const adminUsage = ref<AdminUsage[]>([]);
const adminSearch = ref("");
const adminPage = ref(1);
const adminPageSize = 20;
const adminUserTotal = ref(0);
const adminResultTotal = ref(0);
const adminUserAdminTotal = ref(0);
const adminUsageTotal = ref(0);
const selectedAdminUserId = ref<number | null>(null);
const adminLoading = ref(false);
const adminError = ref("");
const adminResetPassword = ref("");
const adminResetStatus = ref("");
const adminResetting = ref(false);
const promptEditorOpen = ref(false);
const promptEditorInitial = ref<PromptForm | null>(null);
const promptEditorEntryId = ref<number | null>(null);
const promptSaveStatus = ref("");
const promptCategorySuggestions = ref<string[]>([]);
const promptPickerOpen = ref(false);
const promptPickerConfirmOpen = ref(false);
const pendingPromptSelection = ref<PromptPickerEntry | null>(null);
const updateStatus = ref<UpdateStatus>("idle");
const serverVersion = ref("");
const BACKGROUND_EFFECT_KEY = "genimage-background-effect";
const WORKSPACE_RESULT_RATIO_KEY = "genimage-workspace-result-ratio";
const WORKSPACE_COMPOSER_COLLAPSED_KEY = "genimage-workspace-composer-collapsed";
const WORKSPACE_SELECTION_PREFIX = "genimage-workspace-selection:";
const DEFAULT_WORKSPACE_RESULT_RATIO = 48;
const backgroundEffect = ref<BackgroundEffect>(loadBackgroundEffect());
const workspaceResultRatio = ref(loadWorkspaceResultRatio());
const workspaceComposerCollapsed = ref(loadWorkspaceComposerCollapsed());
const workspacePanel = ref<HTMLElement | null>(null);
const workspaceResizing = ref(false);
let settingsSaveQueue: Promise<void> = Promise.resolve();
let apiKeySelectionQueue: Promise<void> = Promise.resolve();
let apiKeySelectionVersion = 0;
let referencePreviewSequence = 0;
let verificationCooldownTimer: number | undefined;
let adminSearchTimer: number | undefined;
let hasStoredWorkspaceSelection = false;
const referenceDragDepth: Record<ReferenceCategory, number> = {
  person: 0,
  environment: 0,
  object: 0,
};

function workspaceSelectionKey() {
  return `${WORKSPACE_SELECTION_PREFIX}${currentUsername.value || "anonymous"}`;
}

function restoreWorkspaceSelection() {
  hasStoredWorkspaceSelection = false;
  try {
    const raw = window.localStorage.getItem(workspaceSelectionKey());
    if (!raw) return;
    hasStoredWorkspaceSelection = true;
    const saved = JSON.parse(raw) as { projectId?: number; conversationId?: number | null };
    if (Number.isInteger(saved.projectId) && saved.projectId! > 0) selectedProjectId.value = saved.projectId!;
    if (saved.conversationId == null || (Number.isInteger(saved.conversationId) && saved.conversationId > 0)) {
      currentConversationId.value = saved.conversationId ?? null;
    }
  } catch {
    // Invalid or unavailable storage should not prevent the workspace from loading.
  }
}

function persistWorkspaceSelection() {
  try {
    window.localStorage.setItem(workspaceSelectionKey(), JSON.stringify({
      projectId: selectedProjectId.value,
      conversationId: currentConversationId.value,
    }));
    hasStoredWorkspaceSelection = true;
  } catch {
    // Workspace state remains available for the current session when storage is unavailable.
  }
}

const generationRuns = new Map<number, GenerationRun>();
const generationVersion = ref(0);
const historyFailureGroups = ref<HistoryFailureGroup[]>([]);
const generationBatchViews = ref<Record<number, GenerationViewSpec[]>>({});
const activeGenerationRunId = ref<number | null>(null);
const historyDetailCache = new Map<number, Promise<HistoryDetail>>();
const historyImagePreloads = new Map<string, HTMLImageElement>();
let historyOpenVersion = 0;

function loadBackgroundEffect(): BackgroundEffect {
  try {
    return window.localStorage.getItem(BACKGROUND_EFFECT_KEY) === "snowfall" ? "snowfall" : "gravity-grid";
  } catch {
    return "gravity-grid";
  }
}

function loadWorkspaceResultRatio() {
  try {
    const stored = Number(window.localStorage.getItem(WORKSPACE_RESULT_RATIO_KEY));
    return Number.isFinite(stored) && stored >= 25 && stored <= 75
      ? stored
      : DEFAULT_WORKSPACE_RESULT_RATIO;
  } catch {
    return DEFAULT_WORKSPACE_RESULT_RATIO;
  }
}

function loadWorkspaceComposerCollapsed() {
  try {
    return window.localStorage.getItem(WORKSPACE_COMPOSER_COLLAPSED_KEY) === "true";
  } catch {
    return false;
  }
}

function toggleWorkspaceComposer() {
  workspaceComposerCollapsed.value = !workspaceComposerCollapsed.value;
  if (workspaceComposerCollapsed.value) finishWorkspaceResize();
  try {
    window.localStorage.setItem(
      WORKSPACE_COMPOSER_COLLAPSED_KEY,
      String(workspaceComposerCollapsed.value),
    );
  } catch {
    // The collapsed state still applies for the current session when storage is unavailable.
  }
}

function persistWorkspaceResultRatio() {
  try {
    window.localStorage.setItem(WORKSPACE_RESULT_RATIO_KEY, String(workspaceResultRatio.value));
  } catch {
    // The resized layout still applies for the current session when storage is unavailable.
  }
}

function workspaceRatioBounds() {
  const height = workspacePanel.value?.getBoundingClientRect().height ?? 0;
  if (height <= 0) return { minimum: 25, maximum: 75 };
  const minimum = Math.max(25, 260 / height * 100);
  const maximum = Math.min(78, (height - 232) / height * 100);
  return maximum > minimum ? { minimum, maximum } : { minimum: 25, maximum: 75 };
}

function setWorkspaceResultRatio(ratio: number, persist = false) {
  const { minimum, maximum } = workspaceRatioBounds();
  workspaceResultRatio.value = Math.round(Math.min(maximum, Math.max(minimum, ratio)) * 10) / 10;
  if (persist) persistWorkspaceResultRatio();
}

function resizeWorkspaceFromPointer(event: PointerEvent) {
  const panel = workspacePanel.value;
  if (!panel) return;
  const bounds = panel.getBoundingClientRect();
  if (!bounds.height) return;
  setWorkspaceResultRatio((event.clientY - bounds.top) / bounds.height * 100);
}

function finishWorkspaceResize() {
  if (!workspaceResizing.value) return;
  workspaceResizing.value = false;
  document.body.classList.remove("workspace-is-resizing");
  window.removeEventListener("pointermove", resizeWorkspaceFromPointer);
  window.removeEventListener("pointerup", finishWorkspaceResize);
  window.removeEventListener("pointercancel", finishWorkspaceResize);
  persistWorkspaceResultRatio();
}

function startWorkspaceResize(event: PointerEvent) {
  if (workspaceComposerCollapsed.value || event.button !== 0) return;
  event.preventDefault();
  workspaceResizing.value = true;
  document.body.classList.add("workspace-is-resizing");
  resizeWorkspaceFromPointer(event);
  window.addEventListener("pointermove", resizeWorkspaceFromPointer);
  window.addEventListener("pointerup", finishWorkspaceResize);
  window.addEventListener("pointercancel", finishWorkspaceResize);
}

function handleWorkspaceResizeKeydown(event: KeyboardEvent) {
  if (workspaceComposerCollapsed.value) return;
  if (event.key === "ArrowUp" || event.key === "ArrowDown") {
    event.preventDefault();
    setWorkspaceResultRatio(workspaceResultRatio.value + (event.key === "ArrowDown" ? 2 : -2), true);
  } else if (event.key === "Home") {
    event.preventDefault();
    setWorkspaceResultRatio(DEFAULT_WORKSPACE_RESULT_RATIO, true);
  }
}

function resetWorkspaceResultRatio() {
  setWorkspaceResultRatio(DEFAULT_WORKSPACE_RESULT_RATIO, true);
}

function resolveCurrentView(): CurrentView {
  if (window.location.pathname === "/settings") return "settings";
  if (window.location.pathname === "/admin") return "admin";
  if (window.location.pathname === "/skills") return "skills";
  if (window.location.pathname === "/prompts") return "prompts";
  return "workspace";
}

function selectBackgroundEffect(effect: BackgroundEffect) {
  backgroundEffect.value = effect;
  try {
    window.localStorage.setItem(BACKGROUND_EFFECT_KEY, effect);
  } catch {
    // The selected effect still applies for the current session when storage is unavailable.
  }
}
const visibleGenerationRuns = computed(() => {
  generationVersion.value;
  if (activeHistoryId.value !== null) return [];

  if (currentConversationId.value !== null) {
    return [...generationRuns.entries()]
      .filter(([, run]) => run.conversationId === currentConversationId.value)
      .map(([id, run]) => ({ id, run }));
  }

  if (activeGenerationRunId.value === null) return [];
  const run = generationRuns.get(activeGenerationRunId.value);
  return run ? [{ id: activeGenerationRunId.value, run }] : [];
});
const visibleHistoryFailureGroups = computed(() => {
  generationVersion.value;
  if (currentConversationId.value === null) return [];
  const liveBatchIds = new Set(
    [...generationRuns.values()]
      .filter((run) => run.conversationId === currentConversationId.value && run.batchId !== null)
      .map((run) => run.batchId as number),
  );
  return historyFailureGroups.value.filter((group) => !liveBatchIds.has(group.batchId));
});
const visibleGenerationCards = computed<GenerationDisplayCard[]>(() => {
  generationVersion.value;
  const cards: GenerationDisplayCard[] = [];
  const fallbackPositions = new Map<string, number>();
  for (const image of generated.value) {
    const batchId = image.batch_id ?? null;
    const fallbackKey = batchId === null ? "legacy" : String(batchId);
    const fallbackPosition = fallbackPositions.get(fallbackKey) ?? 0;
    fallbackPositions.set(fallbackKey, fallbackPosition + 1);
    const slotPosition = image.batch_position ?? fallbackPosition;
    cards.push({
      key: `image-${image.history_image_id ?? imageSource(image) ?? `${fallbackKey}-${slotPosition}`}`,
      kind: "image",
      batchId,
      slotPosition,
      image,
    });
  }
  for (const { id: runId, run } of visibleGenerationRuns.value) {
    const generatedPositions = new Set(
      generated.value
        .filter((image) => run.batchId !== null && image.batch_id === run.batchId)
        .map((image, index) => image.batch_position ?? index),
    );
    for (let slotPosition = 0; slotPosition < run.imageCount; slotPosition += 1) {
      if (run.deletedPositions.has(slotPosition)
        || run.cancelledPositions.has(slotPosition)
        || generatedPositions.has(slotPosition)) continue;
      cards.push({
        key: `run-${runId}-${slotPosition}`,
        kind: "run",
        batchId: run.batchId,
        slotPosition,
        runId,
        run,
      });
    }
  }
  for (const group of visibleHistoryFailureGroups.value) {
    for (const slotPosition of group.positions) {
      cards.push({
        key: `history-failure-${group.batchId}-${slotPosition}`,
        kind: "history-failure",
        batchId: group.batchId,
        slotPosition,
        group,
      });
    }
  }
  return cards.sort((left, right) => {
    if (left.batchId === null || right.batchId === null) {
      if (left.batchId === null && right.batchId !== null) return -1;
      if (left.batchId !== null && right.batchId === null) return 1;
      const leftRunId = left.kind === "run" ? left.runId : 0;
      const rightRunId = right.kind === "run" ? right.runId : 0;
      if (leftRunId !== rightRunId) return rightRunId - leftRunId;
    } else if (left.batchId !== right.batchId) {
      return right.batchId - left.batchId;
    }
    return left.slotPosition - right.slotPosition;
  });
});
const selectedAdminUser = computed(() =>
  adminUsers.value.find((user) => user.id === selectedAdminUserId.value) ?? null,
);
const adminPageCount = computed(() => Math.max(1, Math.ceil(adminResultTotal.value / adminPageSize)));
function generationFillPercent(elapsedMs: number) {
  return Math.min(94, 8 + elapsedMs / 450);
}
const runningGenerations = computed<RunningGenerationSummary[]>(() => {
  generationVersion.value;
  const conversations = new Map<string, { id: number; run: GenerationRun }>();
  for (const [id, run] of generationRuns.entries()) {
    if (run.state !== "running") continue;
    const conversationId = run.conversationId ?? run.taskId;
    const key = conversationId === null ? `run-${id}` : `conversation-${conversationId}`;
    const current = conversations.get(key);
    const shouldReplace = !current
      || id === activeGenerationRunId.value
      || (current.id !== activeGenerationRunId.value && run.startedAt > current.run.startedAt);
    if (shouldReplace) conversations.set(key, { id, run });
  }
  return [...conversations.values()].map(({ id, run }) => ({
    id,
    projectId: run.projectId,
    prompt: run.prompt,
    model: run.model,
    size: run.size,
    resolution: run.resolution,
    elapsedMs: run.elapsedMs,
  }));
});
const canAnalyze = computed(() => referencePreviews.value.length > 0 && busy.value !== "analyze");
const selectedConfig = computed(() => apiKeyConfigs.value.find((item) => item.id === activeApiKeyConfigId.value) ?? null);
const selectedProviderType = computed<ApiKeyProvider>(() =>
  selectedConfig.value?.provider_type
    ?? (provider.value === "gemini" ? "gemini" : provider.value === "grok" ? "grok" : "gpt"),
);
const selectedCapability = computed(() => capabilities.value.find(
  (item) => item.provider_type === selectedProviderType.value && item.model.toLowerCase() === model.value.toLowerCase(),
) ?? null);
const nativeAspectRatioOptions = computed(() => selectedCapability.value?.aspect_ratios ?? []);
const resolutionOptions = computed(() => selectedCapability.value?.resolutions ?? []);
const qualityOptions = computed(() => selectedCapability.value?.qualities ?? []);
const gptSizeOptions = computed(() => selectedCapability.value?.sizes ?? []);
const selectedGptSizeLabel = computed(() => (
  gptSizeOptions.value.find((option) => option.value === size.value)?.label ?? size.value
));
const imageCountOptions = computed(() => Array.from(
  { length: selectedCapability.value?.max_output_count ?? 1 },
  (_, index) => index + 1,
));
const maxReferenceImages = computed(() => selectedCapability.value?.max_reference_images ?? 0);
const hasPersonReferences = computed(() => referencePreviews.value.some((item) => item.category === "person"));
const hasObjectReferences = computed(() => referencePreviews.value.some((item) => item.category === "object"));
const selectedMultiViewOptions = computed(() => [
  ...MULTI_VIEW_PRESETS.filter((preset) => selectedMultiViewKeys.value.includes(preset.key)),
  ...customMultiViews.value.map((view) => ({
    key: view.key,
    label: view.label,
    instruction: view.label,
  })),
]);
const multiViewValidationMessage = computed(() => {
  if (!multiViewEnabled.value) return "";
  if (!hasPersonReferences.value && !hasObjectReferences.value) return "请先添加人物或物品参考图";
  if (multiViewTarget.value === "person" && !hasPersonReferences.value) return "请先添加人物参考图";
  if (multiViewTarget.value === "object" && !hasObjectReferences.value) return "请先添加物品参考图";
  if (selectedMultiViewOptions.value.length === 0) return "请至少选择一个视角";
  return "";
});
const canGenerate = computed(() => Boolean(selectedCapability.value)
  && !generationSubmitting.value
  && !multiViewValidationMessage.value);

watch([hasPersonReferences, hasObjectReferences], ([hasPerson, hasObject]) => {
  if (hasPerson && !hasObject) multiViewTarget.value = "person";
  else if (hasObject && !hasPerson) multiViewTarget.value = "object";
});

function toggleMultiView() {
  if (multiViewEnabled.value) {
    multiViewEnabled.value = false;
    imageCount.value = Math.min(
      regularImageCount.value,
      selectedCapability.value?.max_output_count ?? regularImageCount.value,
    );
    regularImageCount.value = imageCount.value;
    multiViewInputError.value = "";
    return;
  }
  regularImageCount.value = imageCount.value;
  multiViewEnabled.value = true;
  if (hasObjectReferences.value && !hasPersonReferences.value) multiViewTarget.value = "object";
  else if (hasPersonReferences.value) multiViewTarget.value = "person";
}

function disableMultiView() {
  if (multiViewEnabled.value) {
    imageCount.value = Math.min(
      regularImageCount.value,
      selectedCapability.value?.max_output_count ?? regularImageCount.value,
    );
    regularImageCount.value = imageCount.value;
  }
  multiViewEnabled.value = false;
  multiViewInputError.value = "";
}

function toggleMultiViewPreset(key: string) {
  if (selectedMultiViewKeys.value.includes(key)) {
    selectedMultiViewKeys.value = selectedMultiViewKeys.value.filter((item) => item !== key);
    multiViewInputError.value = "";
    return;
  }
  if (selectedMultiViewOptions.value.length >= 8) {
    multiViewInputError.value = "最多选择 8 个视角";
    return;
  }
  selectedMultiViewKeys.value = [...selectedMultiViewKeys.value, key];
  multiViewInputError.value = "";
}

function addCustomMultiView() {
  const label = customMultiViewInput.value.trim();
  if (!label) {
    multiViewInputError.value = "请输入自定义视角";
    return;
  }
  if (label.length > 40) {
    multiViewInputError.value = "自定义视角最多 40 个字";
    return;
  }
  const normalized = label.toLocaleLowerCase();
  const duplicate = MULTI_VIEW_PRESETS.some((preset) => preset.label.toLocaleLowerCase() === normalized)
    || customMultiViews.value.some((view) => view.label.toLocaleLowerCase() === normalized);
  if (duplicate) {
    multiViewInputError.value = "这个视角已经存在";
    return;
  }
  if (selectedMultiViewOptions.value.length >= 8) {
    multiViewInputError.value = "最多选择 8 个视角";
    return;
  }
  const key = `custom_${Date.now().toString(36)}_${customMultiViews.value.length + 1}`;
  customMultiViews.value = [...customMultiViews.value, { key, label }];
  customMultiViewInput.value = "";
  multiViewInputError.value = "";
}

function removeCustomMultiView(key: string) {
  customMultiViews.value = customMultiViews.value.filter((view) => view.key !== key);
  multiViewInputError.value = "";
}

function buildGenerationViews(basePrompt: string): GenerationViewSpec[] {
  const targetLabel = multiViewTarget.value === "person" ? "人物主体" : "物品主体";
  return selectedMultiViewOptions.value.map((view) => {
    const requirements = [
      "多视角生成要求：",
      `- 本张仅展示同一个${targetLabel}的一个独立视角，不要拼图、分镜、文字、多面板或同时展示多个视角。`,
      "- 同一分类内的多张参考图是同一主体的补充证据，严格保持身份、面部、发型、服装、配饰、材质、颜色和比例一致。",
      "- 保持原提示词指定的环境、构图尺度、光线和视觉风格，仅改变相机观察方向以及实现该视角所必需的姿态。",
      `- 当前视角：${view.instruction}。`,
    ].join("\n");
    return {
      key: `${multiViewTarget.value}_${view.key}`,
      label: view.label,
      prompt: `${basePrompt}\n\n${requirements}`,
    };
  });
}

function restoreMultiViewState(views: GenerationViewSpec[] | undefined) {
  if (!views?.length) {
    disableMultiView();
    return;
  }
  regularImageCount.value = imageCount.value;
  multiViewEnabled.value = true;
  const target = views[0].key.startsWith("object_") ? "object" : "person";
  multiViewTarget.value = target;
  const prefix = `${target}_`;
  const presetKeys = new Set(MULTI_VIEW_PRESETS.map((preset) => preset.key));
  selectedMultiViewKeys.value = [];
  customMultiViews.value = [];
  for (const view of views) {
    const rawKey = view.key.startsWith(prefix) ? view.key.slice(prefix.length) : view.key;
    if (presetKeys.has(rawKey)) selectedMultiViewKeys.value.push(rawKey);
    else customMultiViews.value.push({ key: rawKey, label: view.label });
  }
  multiViewInputError.value = "";
}
watch(selectedCapability, (capability) => {
  if (!capability) return;
  imageCount.value = Math.min(imageCount.value, capability.max_output_count);
  const candidateSize = LEGACY_SIZE_TO_ASPECT_RATIO[size.value] ?? size.value;
  if (capability.sizes.length) {
    size.value = capability.sizes.some((option) => option.value === size.value)
      ? size.value
      : capability.default_size ?? capability.sizes[0]?.value ?? "";
  } else {
    size.value = capability.aspect_ratios.includes(candidateSize)
      ? candidateSize
      : capability.default_aspect_ratio ?? capability.aspect_ratios[0] ?? "";
  }
  resolution.value = capability.resolutions.includes(resolution.value)
    ? resolution.value
    : capability.default_resolution ?? capability.resolutions[0] ?? "";
  quality.value = capability.qualities.some((option) => option.value === quality.value)
    ? quality.value
    : capability.default_quality;
  const supportedMenus = [
    "apiKey", "model",
    ...(capability.sizes.length || capability.aspect_ratios.length ? ["size"] : []),
    ...(capability.resolutions.length ? ["resolution"] : []),
    ...(capability.qualities.length ? ["quality"] : []),
    "count",
  ];
  if (openParameterMenu.value && !supportedMenus.includes(openParameterMenu.value)) {
    openParameterMenu.value = null;
  }
});
const selectedApiKeyLabel = computed(() => selectedConfig.value?.alias ?? "未配置");
const selectedModelLabel = computed(() => model.value);
const modelOptions = computed(() => {
  if (selectedConfig.value) {
    return availableModels.value.filter(
      (item) => item.provider_type === selectedConfig.value?.provider_type
        && capabilities.value.some((capability) => capability.provider_type === item.provider_type && capability.model === item.id),
    );
  }
  const providerModels = providers.value.find((item) => item.id === provider.value)?.models;
  const models = providerModels?.length
    ? providerModels
    : capabilities.value.filter((item) => item.provider_type === selectedProviderType.value).map((item) => item.model);
  return models.map((id) => ({
    id,
    provider_type: selectedProviderType.value,
  })) ?? [];
});
const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const CLIENT_VERSION = (import.meta.env.VITE_APP_VERSION ?? "dev").trim() || "dev";

function apiFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  return window.fetch(input, { credentials: "include", ...init });
}
const versionActionLabel = computed(() => {
  if (updateStatus.value === "checking") return "检查中...";
  if (updateStatus.value === "current") return "已是最新版本";
  if (updateStatus.value === "available") return "立即更新";
  if (updateStatus.value === "error") return "重新检查";
  return "检查更新";
});
const versionStatusMessage = computed(() => {
  if (updateStatus.value === "current") return "当前版本已是最新版本";
  if (updateStatus.value === "available") return "发现新版本，可以立即更新";
  if (updateStatus.value === "error") return "检查更新失败，请确认服务连接后重试";
  return "";
});

function readableError(data: any, fallback: string) {
  const messages: Record<string, string> = {
    provider_auth: "服务商鉴权失败，请检查 API Key",
    provider_timeout: "服务商请求超时，请稍后重试",
    provider_request: "服务商请求失败",
    provider_not_found: "找不到所选服务商",
    invalid_image: "图片格式或内容无效",
    history_not_found: "历史记录不存在",
  invalid_credentials: "邮箱、旧用户名或密码错误",
    invalid_verification_code: "验证码错误或已失效",
    email_registered: "该邮箱已注册",
    username_taken: "用户名已存在",
    legacy_password_required: "旧账号需使用原密码绑定邮箱",
    verification_code_cooldown: "验证码发送过于频繁，请稍后重试",
    auth_rate_limited: "请求过于频繁，请稍后重试",
    smtp_not_configured: "邮件服务尚未配置",
    email_delivery_failed: "验证码邮件发送失败",
    admin_required: "需要管理员权限",
  };
  const error = data?.error ?? data?.detail?.error;
  return messages[error?.code] ?? error?.message ?? fallback;
}

function apiErrorCode(data: any): string | undefined {
  return data?.error?.code ?? data?.detail?.error?.code;
}

async function parseJsonResponse(response: Response): Promise<any | null> {
  const text = await response.text();
  if (!text.trim()) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function resourceUrl(path: string) {
  return /^https?:\/\//.test(path) ? path : `${API_BASE}${path}`;
}

async function checkForUpdate() {
  if (updateStatus.value === "checking") return;
  updateStatus.value = "checking";
  serverVersion.value = "";
  try {
    const response = await apiFetch(`${API_BASE}/api/version?t=${Date.now()}`, {
      cache: "no-store",
    });
    const data = await parseJsonResponse(response);
    const deployedVersion = typeof data?.version === "string" ? data.version.trim() : "";
    if (!response.ok || !deployedVersion) throw new Error("Invalid version response");
    serverVersion.value = deployedVersion;
    updateStatus.value = deployedVersion === CLIENT_VERSION ? "current" : "available";
  } catch {
    updateStatus.value = "error";
  }
}

function applyUpdate() {
  if (updateStatus.value !== "available" || !serverVersion.value) return;
  const nextUrl = new URL(window.location.href);
  nextUrl.searchParams.set("_app_version", serverVersion.value);
  window.location.search = nextUrl.search;
}

function handleVersionAction() {
  if (updateStatus.value === "available") applyUpdate();
  else void checkForUpdate();
}

function promptWithAnalysis(currentPrompt: string, analysisText?: string | null) {
  const result = analysisText?.trim() ?? "";
  if (!result) return currentPrompt;
  if (!currentPrompt.trim()) return result;
  return `${currentPrompt.trimEnd()}\n\n${result}`;
}

function promptImageCount(value: string) {
  const match = value.match(/(?:生成|绘制|输出|创建)[^\n]{0,8}?(\d+|一|两|二|三|四)\s*(?:张|幅|个)/);
  if (!match) return 1;
  const chineseCounts: Record<string, number> = { 一: 1, 两: 2, 二: 2, 三: 3, 四: 4 };
  return chineseCounts[match[1]] ?? Number(match[1]);
}

function expectedGenerationImageCount(requestPrompt: string, prompts: string[], count: number) {
  const effectivePrompts = prompts.length ? prompts : [requestPrompt];
  const perPrompt = count > 1 ? count : Math.max(count, ...effectivePrompts.map(promptImageCount));
  return effectivePrompts.length * perPrompt;
}

async function submitAuth(mode: "login" | "register") {
  authError.value = "";
  if (authSubmitting.value) return;
  const passwordsMatch = mode === "login" || password.value === passwordConfirmation.value;
  const registrationValid = mode === "login" || (
    username.value.trim() && /^\d{6}$/.test(verificationCode.value.trim()) && passwordsMatch
  );
  if (!email.value.trim() || password.value.length < 6 || !registrationValid) {
    authError.value = mode === "register"
      ? "请填写用户名、邮箱和 6 位验证码，密码至少 6 位且两次输入一致"
      : "请填写邮箱或旧用户名和密码";
    return;
  }
  const body = mode === "register"
    ? {
        username: username.value.trim(),
        email: email.value.trim(),
        verification_code: verificationCode.value.trim(),
        password: password.value,
        password_confirmation: passwordConfirmation.value,
      }
    : { email: email.value.trim(), password: password.value };
  authSubmitting.value = true;
  try {
    const response = await apiFetch(`${API_BASE}/api/auth/${mode}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await parseJsonResponse(response);
    if (!response.ok) { authError.value = readableError(data, "登录失败"); return; }
    applyCurrentUser(data);
    password.value = "";
    passwordConfirmation.value = "";
    verificationCode.value = "";
    authView.value = "workspace";
    if (currentView.value === "admin" && !currentIsAdmin.value) navigateToWorkspace();
    await loadProviders();
    await loadRuntimeSettings();
    await loadProjects(true);
    if (currentView.value === "admin") await loadAdminUsers();
  } catch {
    authError.value = "无法连接服务器";
  } finally {
    authSubmitting.value = false;
  }
}

function applyCurrentUser(data: any) {
  currentUsername.value = String(data?.username ?? "");
  currentEmail.value = String(data?.email ?? "");
  profileUsername.value = currentUsername.value;
  currentIsAdmin.value = Boolean(data?.is_admin);
  restoreWorkspaceSelection();
}

function startVerificationCooldown(seconds: number) {
  if (verificationCooldownTimer !== undefined) window.clearInterval(verificationCooldownTimer);
  verificationCooldown.value = Math.max(1, seconds);
  verificationCooldownTimer = window.setInterval(() => {
    verificationCooldown.value = Math.max(0, verificationCooldown.value - 1);
    if (verificationCooldown.value === 0 && verificationCooldownTimer !== undefined) {
      window.clearInterval(verificationCooldownTimer);
      verificationCooldownTimer = undefined;
    }
  }, 1000);
}

async function sendVerificationCode() {
  authError.value = "";
  if (!email.value.trim() || verificationSending.value || verificationCooldown.value > 0) {
    if (!email.value.trim()) authError.value = "请先填写邮箱";
    return;
  }
  verificationSending.value = true;
  try {
    const response = await apiFetch(`${API_BASE}/api/auth/verification-code`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.value.trim() }),
    });
    const data = await parseJsonResponse(response);
    if (!response.ok) {
      authError.value = readableError(data, "验证码发送失败");
      const retryAfter = Number(data?.error?.retry_after_seconds ?? 0);
      if (retryAfter > 0) startVerificationCooldown(retryAfter);
      return;
    }
    startVerificationCooldown(Number(data?.retry_after_seconds ?? 60));
  } catch {
    authError.value = "无法连接邮件服务";
  } finally {
    verificationSending.value = false;
  }
}

async function logout() {
  try {
    await apiFetch(`${API_BASE}/api/auth/logout`, { method: "POST" });
  } finally {
    resetAccountWorkspace();
    currentUsername.value = "";
    currentEmail.value = "";
    profileUsername.value = "";
    profileStatus.value = "";
    currentIsAdmin.value = false;
    authView.value = "login";
  }
}

function navigateToSettings() {
  window.history.pushState({}, "", "/settings");
  currentView.value = "settings";
  settingsApiKey.value = "";
  profileUsername.value = currentUsername.value;
  profileStatus.value = "";
}

function navigateToWorkspace() {
  window.history.pushState({}, "", "/");
  currentView.value = "workspace";
  if (activeGenerationRunId.value !== null) {
    void restoreGenerationRun(activeGenerationRunId.value);
  }
}

async function navigateToAdmin() {
  if (!currentIsAdmin.value) return;
  window.history.pushState({}, "", "/admin");
  currentView.value = "admin";
  await loadAdminUsers();
}

async function loadAdminUsers(page = adminPage.value) {
  if (!currentIsAdmin.value) return;
  adminPage.value = Math.max(1, page);
  adminLoading.value = true;
  adminError.value = "";
  try {
    const parameters = new URLSearchParams();
    if (adminPage.value > 1) parameters.set("page", String(adminPage.value));
    if (adminSearch.value.trim()) parameters.set("search", adminSearch.value.trim());
    const query = parameters.size ? `?${parameters.toString()}` : "";
    const response = await apiFetch(`${API_BASE}/api/admin/users${query}`);
    const data = await parseJsonResponse(response);
    if (!response.ok) throw new Error(readableError(data, "无法加载用户信息"));
    const legacyItems = Array.isArray(data) ? data as AdminUser[] : null;
    const pageData = (legacyItems ? null : data) as AdminUserPage | null;
    adminUsers.value = legacyItems ?? (Array.isArray(pageData?.items) ? pageData.items : []);
    adminUserTotal.value = legacyItems?.length ?? Number(pageData?.total ?? 0);
    adminResultTotal.value = legacyItems?.length ?? Number(pageData?.result_total ?? pageData?.total ?? 0);
    adminUserAdminTotal.value = legacyItems?.filter((user) => user.is_admin).length ?? Number(pageData?.admin_total ?? 0);
    adminUsageTotal.value = legacyItems?.reduce((total, user) => total + user.usage_count, 0) ?? Number(pageData?.usage_total ?? 0);
    if (!legacyItems && pageData?.page) adminPage.value = pageData.page;
    const lastPage = Math.max(1, Math.ceil(adminResultTotal.value / adminPageSize));
    if (adminPage.value > lastPage) {
      await loadAdminUsers(lastPage);
      return;
    }
    const selectedExists = adminUsers.value.some((user) => user.id === selectedAdminUserId.value);
    selectedAdminUserId.value = selectedExists
      ? selectedAdminUserId.value
      : adminUsers.value[0]?.id ?? null;
    if (selectedAdminUserId.value !== null) await loadAdminUsage(selectedAdminUserId.value);
    else adminUsage.value = [];
  } catch (loadError) {
    adminError.value = loadError instanceof Error ? loadError.message : "无法加载用户信息";
  } finally {
    adminLoading.value = false;
  }
}

function scheduleAdminSearch() {
  if (adminSearchTimer !== undefined) window.clearTimeout(adminSearchTimer);
  adminSearchTimer = window.setTimeout(() => {
    adminSearchTimer = undefined;
    void loadAdminUsers(1);
  }, 300);
}

function changeAdminPage(page: number) {
  if (page < 1 || page > adminPageCount.value || page === adminPage.value) return;
  void loadAdminUsers(page);
}

async function loadAdminUsage(userId: number) {
  adminError.value = "";
  const response = await apiFetch(`${API_BASE}/api/admin/users/${userId}/usage`);
  const data = await parseJsonResponse(response);
  if (!response.ok) {
    adminError.value = readableError(data, "无法加载使用记录");
    adminUsage.value = [];
    return;
  }
  adminUsage.value = Array.isArray(data) ? data : [];
}

async function selectAdminUser(userId: number) {
  selectedAdminUserId.value = userId;
  adminResetPassword.value = "";
  adminResetStatus.value = "";
  await loadAdminUsage(userId);
}

async function resetAdminUserPassword() {
  if (selectedAdminUserId.value === null || adminResetPassword.value.length < 8) {
    adminResetStatus.value = "新密码至少 8 位";
    return;
  }
  adminResetting.value = true;
  adminResetStatus.value = "";
  try {
    const response = await apiFetch(
      `${API_BASE}/api/admin/users/${selectedAdminUserId.value}/reset-password`,
      {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_password: adminResetPassword.value }),
      },
    );
    const data = await parseJsonResponse(response);
    if (!response.ok) adminResetStatus.value = readableError(data, "密码重置失败");
    else {
      adminResetPassword.value = "";
      adminResetStatus.value = "密码已重置，用户现有会话已退出";
    }
  } catch {
    adminResetStatus.value = "无法连接服务器";
  } finally {
    adminResetting.value = false;
  }
}

function formatAdminDate(value: string | null) {
  if (!value) return "-";
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Shanghai",
  }).format(new Date(normalized));
}

function providerTypeLabel(providerType: ApiKeyProvider) {
  if (providerType === "gemini") return "Gemini";
  if (providerType === "grok") return "Grok";
  return "OpenAI";
}

function formatAdminDuration(milliseconds: number | null) {
  if (!milliseconds) return "-";
  if (milliseconds < 1000) return `${milliseconds} ms`;
  if (milliseconds < 60_000) return `${(milliseconds / 1000).toFixed(1)} 秒`;
  return `${(milliseconds / 60_000).toFixed(1)} 分钟`;
}

function toggleParameterMenu(menu: ParameterMenu) {
  openParameterMenu.value = openParameterMenu.value === menu ? null : menu;
}

function closeParameterMenu() {
  openParameterMenu.value = null;
}

async function persistConfigModel(config: ApiKeyConfig, value: string) {
  const response = await apiFetch(`${API_BASE}/api/settings/api-keys/${config.id}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: value }),
  });
  const data = await parseJsonResponse(response);
  if (!response.ok) throw new Error(readableError(data, "保存模型失败"));
  const savedModel = data?.model ?? value;
  apiKeyConfigs.value = apiKeyConfigs.value.map((item) =>
    item.id === config.id ? { ...item, model: savedModel } : item,
  );
  return savedModel;
}

async function loadConfigModels(config: ApiKeyConfig, selectionVersion: number) {
  const isCurrentSelection = () => (
    selectionVersion === apiKeySelectionVersion
    && activeApiKeyConfigId.value === config.id
  );
  if (!isCurrentSelection()) return;
  availableModels.value = [];
  model.value = config.model;
  loadingConfigModels.value = false;
  if (!config.api_key_configured) return;
  loadingConfigModels.value = true;
  try {
    const response = await apiFetch(`${API_BASE}/api/settings/api-keys/${config.id}/models`);
    const data = await parseJsonResponse(response);
    if (!response.ok) throw new Error(readableError(data, "无法获取模型列表"));
    const models = (data?.models ?? []) as DiscoveredModel[];
    if (!isCurrentSelection()) return;
    availableModels.value = models.filter((item) => item.provider_type === config.provider_type);
    if (availableModels.value.length && !availableModels.value.some((item) => item.id === config.model)) {
      const fallbackModel = availableModels.value[0].id;
      model.value = fallbackModel;
      try {
        const savedModel = await persistConfigModel(config, fallbackModel);
        if (isCurrentSelection()) model.value = savedModel;
      } catch (exception) {
        if (isCurrentSelection()) {
          error.value = exception instanceof Error ? exception.message : "保存模型失败";
        }
      }
    }
  } catch {
    if (!isCurrentSelection()) return;
    availableModels.value = [{ id: config.model, provider_type: config.provider_type }];
    model.value = config.model;
  } finally {
    if (isCurrentSelection()) loadingConfigModels.value = false;
  }
}

async function selectApiKeyConfig(selected: ApiKeyConfig) {
  if (legacySettingsMode.value) return;
  const selectionVersion = ++apiKeySelectionVersion;
  activeApiKeyConfigId.value = selected.id;
  model.value = selected.model;
  loadingConfigModels.value = false;
  provider.value = selected.provider_type === "gemini"
    ? "gemini"
    : selected.provider_type === "grok" ? "grok" : "compatible";
  apiKeyConfigured.value = selected.api_key_configured;
  const selection = apiKeySelectionQueue.then(async () => {
    const response = await apiFetch(`${API_BASE}/api/settings/active`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config_id: selected.id }),
    });
    const data = await parseJsonResponse(response);
    if (!response.ok) throw new Error(readableError(data, "切换 API Key 失败"));
    if (selectionVersion !== apiKeySelectionVersion) return;
    await loadConfigModels(selected, selectionVersion);
    if (selectionVersion === apiKeySelectionVersion) closeParameterMenu();
  });
  apiKeySelectionQueue = selection.catch(() => undefined);
  try {
    await selection;
  } catch (exception) {
    if (selectionVersion !== apiKeySelectionVersion) return;
    error.value = exception instanceof Error ? exception.message : "切换 API Key 失败";
    try {
      await loadRuntimeSettings();
    } catch {
      // Keep the actionable activation error when the recovery request also fails.
    }
  }
}

function historyProviderType(item: Pick<HistorySummary, "provider" | "model">): ApiKeyProvider {
  const providerId = item.provider.toLowerCase();
  const modelId = item.model.toLowerCase();
  if (providerId === "gemini" || modelId.includes("gemini")) return "gemini";
  if (providerId === "grok" || modelId.includes("grok")) return "grok";
  return "gpt";
}

function supportedSizeFor(providerType: ApiKeyProvider, modelId: string, value?: string | null) {
  const capability = capabilities.value.find(
    (item) => item.provider_type === providerType && item.model.toLowerCase() === modelId.toLowerCase(),
  );
  if (!capability) return "";
  const candidate = value ? LEGACY_SIZE_TO_ASPECT_RATIO[value] ?? value : null;
  if (capability.sizes.length) {
    return capability.sizes.some((option) => option.value === candidate)
      ? candidate ?? ""
      : capability.default_size ?? capability.sizes[0]?.value ?? "";
  }
  return capability.aspect_ratios.includes(candidate ?? "")
    ? candidate ?? ""
    : capability.default_aspect_ratio ?? capability.aspect_ratios[0] ?? "";
}

function supportedResolutionFor(providerType: ApiKeyProvider, modelId: string, value?: string | null) {
  const capability = capabilities.value.find(
    (item) => item.provider_type === providerType && item.model.toLowerCase() === modelId.toLowerCase(),
  );
  if (!capability?.resolutions.length) return "";
  return capability.resolutions.includes(value ?? "")
    ? value ?? ""
    : capability.default_resolution ?? capability.resolutions[0] ?? "";
}

async function restoreHistoryApiConfig(
  item: Pick<HistorySummary, "provider" | "model"> & { api_key_config_id?: number | null },
  exactModel = false,
) {
  if (legacySettingsMode.value) {
    provider.value = item.provider;
    model.value = capabilities.value.some((capability) => capability.provider_type === "gpt" && capability.model === item.model)
      ? item.model
      : capabilities.value.find((capability) => capability.provider_type === "gpt")?.model ?? "";
    return;
  }

  const providerType = historyProviderType(item);
  const current = selectedConfig.value;
  const exactConfig = item.api_key_config_id == null
    ? undefined
    : apiKeyConfigs.value.find((config) => config.id === item.api_key_config_id);
  const matchingConfig = exactConfig ?? apiKeyConfigs.value.find(
    (config) => config.provider_type === providerType && config.model === item.model,
  ) ?? (current?.provider_type === providerType ? current : undefined)
    ?? apiKeyConfigs.value.find((config) => config.provider_type === providerType);

  if (matchingConfig) {
    await selectApiKeyConfig(matchingConfig);
  } else if (exactModel) {
    activeApiKeyConfigId.value = null;
    provider.value = item.provider;
  }
  if (exactModel) model.value = item.model;
  if (exactModel && !availableModels.value.some((option) => option.id === item.model)) {
    availableModels.value = [
      ...availableModels.value,
      { id: item.model, provider_type: providerType },
    ];
  }
}

async function selectModel(value: string) {
  const previousModel = model.value;
  model.value = value;
  if (legacySettingsMode.value) {
    await applyRuntimeSettings();
    closeParameterMenu();
    return;
  }
  const config = selectedConfig.value;
  if (config) {
    try {
      model.value = await persistConfigModel(config, value);
    } catch (exception) {
      model.value = previousModel;
      error.value = exception instanceof Error ? exception.message : "保存模型失败";
    }
  }
  closeParameterMenu();
}

function selectSize(value: string) {
  size.value = value;
  closeParameterMenu();
}

function selectResolution(value: string) {
  resolution.value = value;
  closeParameterMenu();
}

function selectQuality(value: string) {
  quality.value = value;
  closeParameterMenu();
}

function selectImageCount(value: number) {
  imageCount.value = value;
  regularImageCount.value = value;
  closeParameterMenu();
}

async function saveSettingsApiKey() {
  if (!legacySettingsMode.value) return;
  const apiKey = settingsApiKey.value.trim() || null;
  const response = await apiFetch(`${API_BASE}/api/settings`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: model.value, api_key: apiKey }),
  });
  const data = await parseJsonResponse(response);
  if (!response.ok) { authError.value = readableError(data, "保存接口配置失败"); return; }
  apiKeyConfigured.value = Boolean(data?.api_key_configured);
  settingsApiKey.value = "";
}

async function changePassword() {
  if (newPassword.value.length < 6 || newPassword.value !== newPasswordConfirmation.value) { authError.value = "新密码至少 6 位且两次输入一致"; return; }
  const response = await apiFetch(`${API_BASE}/api/auth/password`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ old_password: oldPassword.value, new_password: newPassword.value, new_password_confirmation: newPasswordConfirmation.value }) });
  if (!response.ok) { authError.value = readableError(await parseJsonResponse(response), "修改密码失败"); return; }
  oldPassword.value = newPassword.value = newPasswordConfirmation.value = "";
  resetAccountWorkspace();
  authView.value = "login";
}

async function updateProfile() {
  const nextUsername = profileUsername.value.trim();
  profileStatus.value = "";
  if (!nextUsername) {
    profileStatus.value = "用户名不能为空";
    return;
  }
  if (nextUsername === currentUsername.value || profileSaving.value) return;
  profileSaving.value = true;
  try {
    const response = await apiFetch(`${API_BASE}/api/auth/profile`, {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: nextUsername }),
    });
    const data = await parseJsonResponse(response);
    if (!response.ok) {
      profileStatus.value = readableError(data, "用户名修改失败");
      return;
    }
    applyCurrentUser(data);
    profileStatus.value = "用户名已更新";
  } catch {
    profileStatus.value = "无法连接服务器";
  } finally {
    profileSaving.value = false;
  }
}

async function submitFeedback() {
  const message = feedbackMessage.value.trim();
  if (!message || feedbackSubmitting.value) return;
  feedbackStatus.value = "正在提交留言...";
  feedbackSubmitting.value = true;
  try {
    const response = await apiFetch(`${API_BASE}/api/feedback`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, contact: feedbackContact.value.trim() }),
    });
    const data = await parseJsonResponse(response);
    if (!response.ok) throw new Error(readableError(data, "留言提交失败，请稍后重试"));
    feedbackMessage.value = "";
    feedbackContact.value = "";
    feedbackStatus.value = data?.message ?? "留言已提交";
  } catch (exception) {
    feedbackStatus.value = exception instanceof Error ? exception.message : "留言提交失败，请稍后重试";
  } finally {
    feedbackSubmitting.value = false;
  }
}

async function loadRuntimeSettings() {
  const selectionVersion = ++apiKeySelectionVersion;
  const response = await apiFetch(`${API_BASE}/api/settings`);
  const data = await response.json();
  if (!response.ok) throw new Error(readableError(data, "无法加载运行时配置"));
  const hasConfigsField = Object.prototype.hasOwnProperty.call(data, "configs");
  const configs = Array.isArray(data.configs) ? data.configs as ApiKeyConfig[] : [];
  legacySettingsMode.value = !hasConfigsField;
  apiKeyConfigs.value = hasConfigsField
    ? configs
    : capabilities.value.filter((capability) => capability.provider_type === "gpt").map((capability, index) => ({ id: 0 - index, alias: capability.label, provider_type: "gpt", model: capability.model, api_key_configured: Boolean(data.api_key_configured) }));
  activeApiKeyConfigId.value = configs.length ? (data.active_config_id ?? configs[0].id) : null;
  const active = configs.find((item) => item.id === activeApiKeyConfigId.value);
  model.value = active?.model ?? (capabilities.value.some((capability) => capability.provider_type === "gpt" && capability.model === data.model)
    ? data.model
    : capabilities.value.find((capability) => capability.provider_type === "gpt")?.model ?? "");
  if (active) {
    provider.value = active.provider_type === "gemini"
      ? "gemini"
      : active.provider_type === "grok" ? "grok" : "compatible";
    await loadConfigModels(active, selectionVersion);
  } else {
    availableModels.value = [];
  }
  apiKeyConfigured.value = Boolean(data.api_key_configured);
}

function resetConfigForm() {
  editingConfigId.value = null;
  showConfigForm.value = false;
  configForm.value = { alias: "", api_key: "", provider_type: null, model: "" };
  settingsConfigError.value = "";
}

function beginAddConfig() {
  resetConfigForm();
  showConfigForm.value = true;
}

function editConfig(config: ApiKeyConfig) {
  editingConfigId.value = config.id;
  showConfigForm.value = true;
  configForm.value = { alias: config.alias, api_key: "", provider_type: config.provider_type, model: config.model };
  settingsConfigError.value = "";
}

async function discoverConfigModels() {
  const apiKey = configForm.value.api_key.trim();
  if (!apiKey) {
    settingsConfigError.value = "请先输入 API Key";
    return;
  }
  if (!configForm.value.provider_type) {
    settingsConfigError.value = "请先选择 API 类型";
    return;
  }
  discoveringModels.value = true;
  settingsConfigError.value = "";
  try {
    const response = await apiFetch(`${API_BASE}/api/settings/api-keys/models`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_key: apiKey,
        provider_type: configForm.value.provider_type,
      }),
    });
    const data = await parseJsonResponse(response);
    if (!response.ok) throw new Error(readableError(data, "无法获取模型列表"));
    discoveredModels.value = (data?.models ?? []) as DiscoveredModel[];
    const first = discoveredModels.value[0];
    if (!first) throw new Error("未获取到可用模型");
    configForm.value.model = first.id;
    configForm.value.provider_type = first.provider_type;
  } catch (exception) {
    settingsConfigError.value = exception instanceof Error ? exception.message : "无法获取模型列表";
  } finally {
    discoveringModels.value = false;
  }
}

async function testConfig(config: ApiKeyConfig) {
  testingConfigId.value = config.id;
  apiKeyTestResults.value = {
    ...apiKeyTestResults.value,
    [config.id]: { message: "正在测试 API Key...", models: [] },
  };
  try {
    const response = await apiFetch(`${API_BASE}/api/settings/api-keys/${config.id}/test`, { method: "POST" });
    const data = await parseJsonResponse(response);
    apiKeyTestResults.value = {
      ...apiKeyTestResults.value,
      [config.id]: {
        message: response.ok ? (data?.message ?? "测试完成") : readableError(data, "测试失败"),
        models: response.ok ? ((data?.models ?? []) as DiscoveredModel[]) : [],
      },
    };
    if (response.ok && data?.models?.length) {
      expandedApiKeyModelLists.value = {
        ...expandedApiKeyModelLists.value,
        [config.id]: true,
      };
    }
  } catch {
    apiKeyTestResults.value = {
      ...apiKeyTestResults.value,
      [config.id]: { message: "测试失败，请稍后重试", models: [] },
    };
  } finally {
    testingConfigId.value = null;
  }
}

function apiKeyModelListExpanded(configId: number) {
  return expandedApiKeyModelLists.value[configId] !== false;
}

function toggleApiKeyModelList(configId: number) {
  expandedApiKeyModelLists.value = {
    ...expandedApiKeyModelLists.value,
    [configId]: !apiKeyModelListExpanded(configId),
  };
}

async function refreshRuntimeSettings() {
  await loadRuntimeSettings();
  resetConfigForm();
}

async function saveConfig() {
  const form = configForm.value;
  const providerType = form.provider_type;
  if (!providerType) {
    settingsConfigError.value = "请选择 API 类型";
    return;
  }
  if (!form.alias.trim() || (!editingConfigId.value && !form.api_key.trim())) {
    settingsConfigError.value = "请填写别名和 API Key";
    return;
  }
  const editing = editingConfigId.value !== null;
  const body = JSON.stringify({ alias: form.alias, api_key: form.api_key, provider_type: providerType });
  let response = await apiFetch(`${API_BASE}/api/settings/api-keys${editing ? `/${editingConfigId.value}` : ""}`, {
    method: editing ? "PATCH" : "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body,
  });
  let data = await parseJsonResponse(response);
  if (editing && response.status === 404 && apiErrorCode(data) === "api_key_config_not_found") {
    response = await apiFetch(`${API_BASE}/api/settings/api-keys`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body,
    });
    data = await parseJsonResponse(response);
  }
  if (!response.ok) {
    settingsConfigError.value = readableError(data, "保存配置失败");
    return;
  }
  resetConfigForm();
  await loadRuntimeSettings();
}

async function deleteConfig(config: ApiKeyConfig) {
  confirmConfig.value = config;
  confirmAction.value = "api-key";
}

async function deleteConfigNow(config: ApiKeyConfig) {
  const response = await apiFetch(`${API_BASE}/api/settings/api-keys/${config.id}`, { method: "DELETE" });
  if (!response.ok) {
    settingsConfigError.value = readableError(await parseJsonResponse(response), "删除配置失败");
    return;
  }
  await refreshRuntimeSettings();
}

async function loadProviders() {
  const response = await apiFetch(`${API_BASE}/api/providers`);
  const data = await response.json();
  if (!response.ok) throw new Error(readableError(data, "无法加载服务商"));
  providers.value = data.providers ?? [];
  capabilities.value = Array.isArray(data.capabilities) ? data.capabilities : [];
  provider.value = selectedConfig.value?.provider_type === "gemini"
    ? "gemini"
    : selectedConfig.value?.provider_type === "grok"
      ? "grok"
      : providers.value[0]?.id ?? "compatible";
}

async function loadHistory() {
  try {
    const response = await apiFetch(`${API_BASE}/api/history`);
    const data = await response.json();
    if (!response.ok) throw new Error(readableError(data, "无法加载历史记录"));
    history.value = data;
    historyError.value = "";
  } catch (exception) {
    historyError.value =
      exception instanceof Error ? exception.message : "无法加载历史记录";
  }
}

function preloadHistoryImages(data: HistoryDetail) {
  for (const image of data.images.filter((item) => item.role === "generated")) {
    const source = resourceUrl(image.thumbnail_url || image.url);
    if (historyImagePreloads.has(source)) continue;
    const preload = new Image();
    preload.decoding = "async";
    preload.src = source;
    historyImagePreloads.set(source, preload);
    while (historyImagePreloads.size > 4) {
      const oldest = historyImagePreloads.keys().next().value as string | undefined;
      if (!oldest) break;
      const released = historyImagePreloads.get(oldest);
      if (released) released.src = "";
      historyImagePreloads.delete(oldest);
    }
  }
}

function fetchHistoryDetail(historyId: number) {
  const cached = historyDetailCache.get(historyId);
  if (cached) return cached;
  const request = (async () => {
    const response = await apiFetch(`${API_BASE}/api/history/${historyId}`);
    const data = await parseJsonResponse(response);
    if (!response.ok) throw new Error(readableError(data, "无法加载历史详情"));
    const detail = data as HistoryDetail;
    if (detail.status !== "completed") historyDetailCache.delete(historyId);
    return detail;
  })();
  historyDetailCache.set(historyId, request);
  while (historyDetailCache.size > 30) {
    const oldest = historyDetailCache.keys().next().value as number | undefined;
    if (oldest === undefined) break;
    historyDetailCache.delete(oldest);
  }
  void request.catch(() => {
    if (historyDetailCache.get(historyId) === request) historyDetailCache.delete(historyId);
  });
  return request;
}

function prefetchHistory(historyId: number) {
  void fetchHistoryDetail(historyId).then(preloadHistoryImages).catch(() => undefined);
}

async function openHistory(historyId: number) {
  const openVersion = ++historyOpenVersion;
  activeGenerationRunId.value = null;
  error.value = "";
  try {
    const data = await fetchHistoryDetail(historyId);
    if (openVersion !== historyOpenVersion) return;

    const project = projects.value.find((candidate) => candidate.history.some((item) => item.id === historyId));
    if (project) {
      selectedProjectId.value = project.id;
      history.value = project.history;
    }
    activeHistoryId.value = historyId;
    currentConversationId.value = data.kind === "generate" ? historyId : null;
    persistWorkspaceSelection();
    prompt.value = promptWithAnalysis(data.prompt, data.analysis_text);
    const providerType = historyProviderType(data);
    const capability = capabilities.value.find((item) => item.provider_type === providerType && item.model.toLowerCase() === data.model.toLowerCase());
    if (capability?.qualities.some((option) => option.value === data.detail)) {
      quality.value = data.detail;
    }
    size.value = supportedSizeFor(providerType, data.model, data.size);
    resolution.value = supportedResolutionFor(providerType, data.model, data.resolution);
    const latestBatch = data.batches?.at(-1);
    rememberHistoryViews(data);
    restoreMultiViewState(latestBatch?.views);
    if (!latestBatch?.views?.length) {
      imageCount.value = Math.min(capability?.max_output_count ?? 1, Math.max(1, data.image_count));
      regularImageCount.value = imageCount.value;
    }
    generated.value = historyImages(data);
    restoreHistoryFailureGroups(data);

    clearReferencePreviews();
    referencePreviews.value = data.images
      .filter((image) => image.role === "reference")
      .sort((left, right) => left.position - right.position)
      .map((image) => ({
        key: `history-${image.id}`,
        category: image.reference_category ?? "person",
        name: image.filename ?? `历史参考图 ${image.position + 1}`,
        url: resourceUrl(image.url),
        file: null,
      }));
    preloadHistoryImages(data);
    void restoreHistoryApiConfig(data).catch((exception) => {
      if (openVersion === historyOpenVersion) {
        error.value = exception instanceof Error ? exception.message : "无法恢复历史配置";
      }
    });
  } catch (exception) {
    if (openVersion !== historyOpenVersion) return;
    error.value =
      exception instanceof Error ? exception.message : "无法加载历史详情";
  }
}

async function loadProjects(restoreWorkspace = false) {
  const restoreStoredSelection = restoreWorkspace && hasStoredWorkspaceSelection;
  const storedProjectId = selectedProjectId.value;
  const storedConversationId = currentConversationId.value;
  try {
    const response = await apiFetch(`${API_BASE}/api/projects`);
    const data = await response.json();
    if (!response.ok) throw new Error("无法加载项目");
    projects.value = Array.isArray(data) ? data : [];
    const storedConversationProject = storedConversationId === null
      ? null
      : projects.value.find((project) => project.history.some((item) => item.id === storedConversationId)) ?? null;
    const storedProjectExists = projects.value.some((project) => project.id === storedProjectId);
    const restoredProjectId = storedProjectExists
      ? storedProjectId
      : storedConversationProject?.id ?? projects.value[0]?.id ?? null;
    const restoredConversationId = storedConversationProject?.id === restoredProjectId
      ? storedConversationId
      : null;
    if (restoreStoredSelection) {
      selectedProjectId.value = restoredProjectId;
      currentConversationId.value = restoredConversationId;
    } else if (!projects.value.some((project) => project.id === selectedProjectId.value)) {
      selectedProjectId.value = projects.value[0]?.id ?? null;
    }
    history.value = projects.value.find((project) => project.id === selectedProjectId.value)?.history ?? [];
    await restorePendingGenerationTasks(restoreWorkspace && !restoreStoredSelection);
    const activeConversationIds = new Set(
      [...generationRuns.values()]
        .filter((run) => run.state === "running")
        .map((run) => run.conversationId)
        .filter((id): id is number => id !== null),
    );
    if (restoreStoredSelection) {
      selectedProjectId.value = restoredProjectId;
      history.value = projects.value.find((project) => project.id === selectedProjectId.value)?.history ?? [];
      currentConversationId.value = restoredConversationId;
      if (restoredConversationId !== null) {
        const selectedHistory = history.value.find((item) => item.id === restoredConversationId);
        if (selectedHistory?.kind === "generate" && activeConversationIds.has(restoredConversationId)) {
          const activeRun = [...generationRuns.entries()]
            .filter(([, run]) => run.state === "running" && run.conversationId === restoredConversationId)
            .sort(([, left], [, right]) => right.startedAt - left.startedAt)[0];
          if (activeRun) await restoreGenerationRun(activeRun[0]);
        } else if (selectedHistory?.kind === "generate") {
          await openHistory(selectedHistory.id);
        } else {
          currentConversationId.value = null;
          persistWorkspaceSelection();
        }
      } else {
        activeGenerationRunId.value = null;
        activeHistoryId.value = null;
        persistWorkspaceSelection();
      }
    } else if (restoreWorkspace && currentConversationId.value !== null && !activeConversationIds.has(currentConversationId.value)) {
      const selectedHistory = history.value.find((item) => item.id === currentConversationId.value);
      if (selectedHistory?.kind === "generate") {
        await openHistory(selectedHistory.id);
      } else if (selectedHistory == null) {
        currentConversationId.value = null;
        persistWorkspaceSelection();
      }
    }
    projectError.value = "";
  } catch (exception) {
    projectError.value = exception instanceof Error ? exception.message : "无法加载项目";
  }
}

async function refreshConversationLists() {
  await Promise.all([loadProjects(), loadHistory()]);
}

function clearWorkspace() {
  generated.value = [];
  historyFailureGroups.value = [];
  activeHistoryId.value = null;
  currentConversationId.value = null;
  prompt.value = "";
  batchPrompts.value = "";
  disableMultiView();
  selectedMultiViewKeys.value = [...DEFAULT_MULTI_VIEW_KEYS];
  customMultiViews.value = [];
  customMultiViewInput.value = "";
  clearReferencePreviews();
  persistWorkspaceSelection();
}

function resetAccountWorkspace() {
  discardGenerationRuns(() => true);
  generated.value = [];
  historyFailureGroups.value = [];
  history.value = [];
  projects.value = [];
  selectedProjectId.value = null;
  activeHistoryId.value = null;
  currentConversationId.value = null;
  activeGenerationRunId.value = null;
  prompt.value = "";
  batchPrompts.value = "";
  disableMultiView();
  selectedMultiViewKeys.value = [...DEFAULT_MULTI_VIEW_KEYS];
  customMultiViews.value = [];
  customMultiViewInput.value = "";
  generationBatchViews.value = {};
  clearReferencePreviews();
  lightboxUrl.value = "";
  openParameterMenu.value = null;
  historyDetailCache.clear();
  for (const image of historyImagePreloads.values()) image.src = "";
  historyImagePreloads.clear();
  apiKeyConfigs.value = [];
  activeApiKeyConfigId.value = null;
  availableModels.value = [];
  discoveredModels.value = [];
  apiKeyConfigured.value = false;
  generationSubmitting.value = false;
  busy.value = "";
  error.value = "";
  historyError.value = "";
  projectError.value = "";
  adminUsers.value = [];
  adminUsage.value = [];
  selectedAdminUserId.value = null;
  generationVersion.value++;
}

async function restoreGenerationRun(runId: number) {
  const run = generationRuns.get(runId);
  if (!run) return;

  clearWorkspace();
  activeGenerationRunId.value = runId;
  currentConversationId.value = run.conversationId ?? run.taskId;
  if (run.projectId !== null) {
    selectedProjectId.value = run.projectId;
    history.value = projects.value.find((project) => project.id === run.projectId)?.history ?? [];
  }
  provider.value = run.provider;
  model.value = run.model;
  activeApiKeyConfigId.value = run.apiKeyConfigId;
  const config = apiKeyConfigs.value.find((item) => item.id === run.apiKeyConfigId);
  if (config) {
    apiKeyConfigured.value = config.api_key_configured;
    if (!availableModels.value.some((item) => item.id === run.model)) {
      availableModels.value = [{ id: run.model, provider_type: config.provider_type }];
    }
  }
  prompt.value = run.prompt;
  batchPrompts.value = run.batchPrompts;
  restoreMultiViewState(run.views);
  if (!run.views.length) {
    imageCount.value = run.imageCount;
    regularImageCount.value = imageCount.value;
  }
  rememberGenerationBatchViews(run.batchId, run.views);
  quality.value = run.quality;
  size.value = run.size;
  resolution.value = run.resolution;
  referencePreviews.value = run.referenceFiles.map(({ file, category }) => ({
    key: `run-${++referencePreviewSequence}`,
    category,
    name: file.name,
    url: URL.createObjectURL(file),
    file,
  }));
  generated.value = run.images;
  error.value = run.error;
  persistWorkspaceSelection();
  generationVersion.value++;

  const conversationId = run.conversationId ?? run.taskId;
  if (conversationId === null) return;
  try {
    const detail = await fetchHistoryDetail(conversationId);
    const stillShowingConversation = currentConversationId.value === conversationId && activeHistoryId.value === null;
    if (activeGenerationRunId.value !== runId && !stillShowingConversation) return;
    const hydratedImages = historyImages(detail);
    run.images = mergeImageResults(hydratedImages, run.images);
    generated.value = mergeImageResults(hydratedImages, generated.value);
    restoreHistoryFailureGroups(detail);
    clearReferencePreviews();
    referencePreviews.value = detail.images
      .filter((image) => image.role === "reference")
      .sort((left, right) => left.position - right.position)
      .map((image) => ({
        key: `restored-${image.id}`,
        category: image.reference_category ?? "person",
        name: image.filename ?? `历史参考图 ${image.position + 1}`,
        url: resourceUrl(image.url),
        file: null,
      }));
    preloadHistoryImages(detail);
    generationVersion.value++;
  } catch {
    // Keep the in-memory images when history hydration is temporarily unavailable.
  }
}

function selectProject(projectId: number) {
  const previousProjectId = selectedProjectId.value;
  selectedProjectId.value = projectId;
  const selectedHistory = projects.value.find((project) => project.id === projectId)?.history ?? [];
  history.value = selectedHistory;
  const conversationBelongsToProject = currentConversationId.value !== null
    && selectedHistory.some((item) => item.id === currentConversationId.value);
  if (previousProjectId !== projectId && !conversationBelongsToProject) {
    historyOpenVersion++;
    activeGenerationRunId.value = null;
    clearWorkspace();
    history.value = selectedHistory;
  }
  persistWorkspaceSelection();
  const firstCompleted = selectedHistory.find((item) => item.status === "completed");
  if (firstCompleted) prefetchHistory(firstCompleted.id);
}

async function submitCreateProject(name: string) {
  if (!name) return;
  const response = await apiFetch(`${API_BASE}/api/projects`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
  if (!response.ok) { projectError.value = "创建项目失败"; return; }
  const data = await response.json();
  await loadProjects();
  startNewConversation(data.id);
}

async function submitRenameProject(project: ProjectSummary, name: string) {
  if (!name || name === project.name) return;
  const response = await apiFetch(`${API_BASE}/api/projects/${project.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
  if (!response.ok) { projectError.value = "重命名项目失败"; return; }
  await loadProjects();
}

async function submitDeleteProject(project: ProjectSummary) {
  const response = await apiFetch(`${API_BASE}/api/projects/${project.id}`, { method: "DELETE" });
  if (!response.ok) { projectError.value = "删除项目失败"; return; }
  const data = await response.json();
  discardGenerationRuns((run) => run.projectId === project.id);
  selectedProjectId.value = data.selected_project_id;
  await loadProjects();
  clearWorkspace();
}

async function submitDeleteHistory(project: ProjectSummary, ids: number[]) {
  const response = await apiFetch(`${API_BASE}/api/projects/${project.id}/history`, { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ history_ids: ids }) });
  if (!response.ok) { projectError.value = "删除历史记录失败"; return; }
  const deletedIds = new Set(ids);
  discardGenerationRuns((run) => run.conversationId !== null && deletedIds.has(run.conversationId));
  for (const id of ids) historyDetailCache.delete(id);
  if (ids.includes(activeHistoryId.value ?? -1) || ids.includes(currentConversationId.value ?? -1)) clearWorkspace();
  await loadProjects();
}

function createProject() {
  projectDialogProject.value = null;
  projectDialogMode.value = "create";
}

function renameProject(project: ProjectSummary) {
  projectDialogProject.value = project;
  projectDialogMode.value = "rename";
}

function cancelProjectDialog() {
  projectDialogMode.value = null;
  projectDialogProject.value = null;
}

async function submitProjectDialog(name: string) {
  const mode = projectDialogMode.value;
  const project = projectDialogProject.value;
  cancelProjectDialog();
  if (mode === "create") await submitCreateProject(name);
  else if (mode === "rename" && project) await submitRenameProject(project, name);
}

function deleteProject(project: ProjectSummary) {
  confirmProject.value = project;
  confirmHistoryIds.value = [];
  confirmAction.value = "project";
}

function deleteHistory(project: ProjectSummary, ids: number[]) {
  confirmProject.value = project;
  confirmHistoryIds.value = ids;
  confirmAction.value = "history";
}

function cancelConfirm() {
  if (actionBusy.value) return;
  confirmAction.value = null;
  confirmProject.value = null;
  confirmHistoryIds.value = [];
  confirmConfig.value = null;
  confirmImage.value = null;
}

async function confirmDeletion() {
  if (actionBusy.value || !confirmAction.value) return;
  if (confirmAction.value === "image") {
    if (!confirmImage.value) return;
    const target = confirmImage.value;
    actionBusy.value = true;
    try {
      await deleteGeneratedImage(target.item, target.slotPosition);
    } finally {
      actionBusy.value = false;
      cancelConfirm();
    }
    return;
  }
  if (confirmAction.value === "api-key") {
    if (!confirmConfig.value) return;
    actionBusy.value = true;
    try {
      await deleteConfigNow(confirmConfig.value);
    } finally {
      actionBusy.value = false;
      cancelConfirm();
    }
    return;
  }
  if (!confirmProject.value) return;
  const project = confirmProject.value;
  const action = confirmAction.value;
  const ids = confirmHistoryIds.value;
  actionBusy.value = true;
  try {
    if (action === "project") await submitDeleteProject(project);
    else if (action === "history") await submitDeleteHistory(project, ids);
  } finally {
    actionBusy.value = false;
    cancelConfirm();
  }
}

function startNewConversation(projectId: number) {
  selectProject(projectId);
  historyOpenVersion++;
  activeGenerationRunId.value = null;
  clearWorkspace();
  persistWorkspaceSelection();
  if (currentView.value !== "workspace") navigateToWorkspace();
}

async function applyRuntimeSettings() {
  const submittedModel = model.value.trim();
  if (!submittedModel) return;

  error.value = "";
  const save = settingsSaveQueue.then(async () => {
    try {
      const response = await apiFetch(`${API_BASE}/api/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: submittedModel, api_key: null }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(readableError(data, "配置应用失败"));
      model.value = data.model;
      apiKeyConfigured.value = Boolean(data.api_key_configured);
      await loadProviders();
    } catch (exception) {
      error.value = exception instanceof Error ? exception.message : "配置应用失败";
    }
  });
  settingsSaveQueue = save;
  await save;
}

function referenceFileKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function referencesForCategory(category: ReferenceCategory) {
  return referencePreviews.value.filter((preview) => preview.category === category);
}

function referenceOrdinal(key: string) {
  return referencePreviews.value.findIndex((preview) => preview.key === key) + 1;
}

function addReferenceFiles(
  category: ReferenceCategory,
  files?: FileList | File[] | null,
) {
  const incoming = Array.from(files ?? []);
  if (!incoming.length) return;

  const unsupported = incoming.filter((file) => !SUPPORTED_REFERENCE_TYPES.has(file.type));
  const existing = new Set(
    referencePreviews.value
      .filter((preview) => preview.category === category)
      .map((preview) => preview.file)
      .filter((file): file is File => file !== null)
      .map(referenceFileKey),
  );
  const candidates = incoming.filter(
    (file) => SUPPORTED_REFERENCE_TYPES.has(file.type) && !existing.has(referenceFileKey(file)),
  );
  const availableSlots = Math.max(0, maxReferenceImages.value - referencePreviews.value.length);
  const accepted = candidates.slice(0, availableSlots);

  referencePreviews.value = [
    ...referencePreviews.value,
    ...accepted.map((file) => ({
      key: `upload-${++referencePreviewSequence}`,
      category,
      name: file.name,
      url: URL.createObjectURL(file),
      file,
    })),
  ];
  if (accepted.length) activeHistoryId.value = null;

  if (unsupported.length) {
    error.value = "仅支持 PNG、JPG、WEBP 或 GIF 图片";
  } else if (candidates.length > availableSlots) {
    error.value = `参考图片最多添加 ${maxReferenceImages.value} 张`;
  } else {
    error.value = "";
  }
}

function handleReferenceInput(category: ReferenceCategory, event: Event) {
  const input = event.target as HTMLInputElement;
  addReferenceFiles(category, input.files);
  input.value = "";
}

function handleReferenceDragEnter(category: ReferenceCategory) {
  referenceDragDepth[category]++;
  referenceDragActiveCategory.value = category;
}

function handleReferenceDragLeave(category: ReferenceCategory) {
  referenceDragDepth[category] = Math.max(0, referenceDragDepth[category] - 1);
  if (referenceDragDepth[category] === 0 && referenceDragActiveCategory.value === category) {
    referenceDragActiveCategory.value = null;
  }
}

function handleReferenceDragOver(event: DragEvent) {
  if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
}

function handleReferenceDrop(category: ReferenceCategory, event: DragEvent) {
  referenceDragDepth[category] = 0;
  referenceDragActiveCategory.value = null;
  addReferenceFiles(category, event.dataTransfer?.files);
}

function revokeReferencePreview(preview: ReferencePreview) {
  if (preview.url.startsWith("blob:")) URL.revokeObjectURL(preview.url);
}

function removeReference(key: string) {
  const index = referencePreviews.value.findIndex((preview) => preview.key === key);
  if (index === -1) return;
  const [removed] = referencePreviews.value.splice(index, 1);
  if (removed) revokeReferencePreview(removed);
  error.value = "";
}

function clearReferencePreviews() {
  for (const preview of referencePreviews.value) revokeReferencePreview(preview);
  referencePreviews.value = [];
  for (const category of REFERENCE_CATEGORIES) referenceDragDepth[category.id] = 0;
  referenceDragActiveCategory.value = null;
}

async function referenceFilesForRequest() {
  return Promise.all(referencePreviews.value.map(async (preview, index) => {
    if (preview.file) return preview.file;
    const response = await apiFetch(preview.url);
    if (!response.ok) throw new Error(`无法读取参考图片 ${index + 1}`);
    const blob = await response.blob();
    const file = new File([blob], preview.name || `reference-${index + 1}`, {
      type: blob.type || "image/png",
    });
    preview.file = file;
    return file;
  }));
}

function formatDuration(milliseconds?: number | null) {
  if (milliseconds == null) return "计时不可用";
  return `${(milliseconds / 1000).toFixed(2)} 秒`;
}

function formatHistoryTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function startGenerationRun(
  runId: number,
  controller: AbortController,
  snapshot: Omit<GenerationRun, "controller" | "startedAt" | "elapsedMs" | "timer" | "images" | "failureCount" | "error" | "state" | "deletedPositions" | "cancelledPositions">,
  initialElapsedMs = 0,
  activate = true,
) {
  const run: GenerationRun = {
    controller,
    startedAt: performance.now() - initialElapsedMs,
    elapsedMs: initialElapsedMs,
    images: [],
    failureCount: 0,
    error: "",
    state: "running",
    deletedPositions: new Set<number>(),
    cancelledPositions: new Set<number>(),
    ...snapshot,
  };
  run.timer = window.setInterval(() => {
    run.elapsedMs = performance.now() - run.startedAt;
    generationVersion.value++;
  }, 100);
  generationRuns.set(runId, run);
  if (activate) activeGenerationRunId.value = runId;
  generationVersion.value++;
}

function stopGenerationRun(runId: number) {
  const run = generationRuns.get(runId);
  if (!run) return;
  if (run.timer !== undefined) window.clearInterval(run.timer);
  run.elapsedMs = performance.now() - run.startedAt;
  generationRuns.delete(runId);
  generationVersion.value++;
}

function discardGenerationRuns(predicate: (run: GenerationRun) => boolean) {
  for (const [runId, run] of [...generationRuns.entries()]) {
    if (!predicate(run)) continue;
    run.controller.abort();
    stopGenerationRun(runId);
  }
  if (activeGenerationRunId.value !== null && !generationRuns.has(activeGenerationRunId.value)) {
    activeGenerationRunId.value = null;
  }
}

function failGenerationRun(
  runId: number,
  message: string,
  historyId?: number,
  state: "failed" | "cancelled" = "failed",
  failureCount?: number,
) {
  const run = generationRuns.get(runId);
  if (!run) return;
  if (run.timer !== undefined) window.clearInterval(run.timer);
  run.timer = undefined;
  run.elapsedMs = performance.now() - run.startedAt;
  run.polling = false;
  run.error = message;
  run.state = state;
  run.failureCount = failureCount ?? run.imageCount;
  if (historyId !== undefined) run.conversationId = historyId;
  generationVersion.value++;
}

function retainMissingGenerationSlots(
  runId: number,
  generatedCount: number,
  expectedCount?: number,
  historyId?: number,
) {
  const run = generationRuns.get(runId);
  if (!run) return false;
  const requestedCount = Math.max(
    0,
    (expectedCount ?? run.imageCount) - run.deletedPositions.size - run.cancelledPositions.size,
  );
  const missingCount = Math.max(0, requestedCount - generatedCount);
  if (missingCount === 0) return false;
  failGenerationRun(
    runId,
    `本次请求 ${requestedCount} 张，服务商只返回 ${generatedCount} 张，其余 ${missingCount} 张生成失败`,
    historyId,
    "failed",
    missingCount,
  );
  return true;
}

function attachGenerationTask(
  runId: number,
  taskId: number,
  batchId: number | null,
  historyId?: number,
  taskApi = false,
) {
  const run = generationRuns.get(runId);
  if (!run) return null;
  run.taskId = taskId;
  run.batchId = batchId;
  rememberGenerationBatchViews(batchId, run.views);
  run.taskApi = taskApi;
  run.conversationId = historyId ?? taskId;
  if (run.batchId !== null && run.conversationId !== null) {
    for (const position of run.deletedPositions) {
      void persistGenerationSlotDeletion(run.conversationId, run.batchId, position).catch((exception) => {
        run.deletedPositions.delete(position);
        error.value = exception instanceof Error ? exception.message : "删除卡片失败";
        generationVersion.value++;
      });
    }
  }
  generationVersion.value++;
  return run;
}

function mergeImageResults(current: ImageResult[], incoming: ImageResult[]) {
  const merged = [...current];
  const identities = new Set(merged.map((image) =>
    image.history_image_id != null
      ? `history-${image.history_image_id}`
      : `source-${imageSource(image) ?? ""}`,
  ));
  for (const image of incoming) {
    const identity = image.history_image_id != null
      ? `history-${image.history_image_id}`
      : `source-${imageSource(image) ?? ""}`;
    if (identities.has(identity)) continue;
    identities.add(identity);
    merged.push(image);
  }
  return merged;
}

function appendConversationImages(conversationId: number, images: ImageResult[]) {
  if (currentConversationId.value === conversationId && activeHistoryId.value === null) {
    generated.value = mergeImageResults(generated.value, images);
  }
  for (const run of generationRuns.values()) {
    if (run.conversationId === conversationId) {
      run.images = mergeImageResults(run.images, images);
    }
  }
  generationVersion.value++;
}

function historyImages(data: HistoryDetail): ImageResult[] {
  return data.images
    .filter((image) => image.role === "generated")
    .map((image) => ({
      url: resourceUrl(image.url),
      thumbnail_url: resourceUrl(image.thumbnail_url || image.url),
      generation_time_ms: data.elapsed_ms,
      history_id: data.id,
      history_image_id: image.id,
      batch_id: image.batch_id,
      batch_position: image.batch_position,
    }));
}

function restoreHistoryFailureGroups(data: HistoryDetail) {
  rememberHistoryViews(data);
  historyFailureGroups.value = (data.batches ?? []).flatMap((batch) => {
    if (batch.status === "pending") return [];
    const deletedPositions = new Set(batch.deleted_positions ?? []);
    const cancelledPositions = new Set(batch.cancelled_positions ?? []);
    const generatedPositions = new Set(
      data.images
        .filter((image) => image.role === "generated" && image.batch_id === batch.id)
        .map((image, index) => image.batch_position ?? index),
    );
    const positions = Array.from({ length: batch.image_count }, (_, position) => position)
      .filter((position) => !deletedPositions.has(position)
        && !cancelledPositions.has(position)
        && !generatedPositions.has(position));
    const groups: HistoryFailureGroup[] = [];
    if (positions.length === 0) return groups;
    const cancelled = batch.error_code?.includes("cancel") ?? false;
    const message = batch.error_message
      || (batch.status === "completed"
        ? `本次请求 ${batch.image_count} 张，服务商只返回 ${batch.generated_count} 张，其余 ${positions.length} 张生成失败`
        : cancelled ? "生成任务已取消" : "生成失败");
    groups.push({
      historyId: data.id,
      batchId: batch.id,
      positions,
      message,
      state: cancelled ? "cancelled" as const : "failed" as const,
      elapsedMs: batch.elapsed_ms,
      views: batch.views ?? [],
    });
    return groups;
  });
}

function latestBatchImages(data: HistoryDetail): ImageResult[] {
  const generatedImages = data.images.filter((image) => image.role === "generated");
  const batchIds = generatedImages
    .map((image) => image.batch_id)
    .filter((batchId): batchId is number => batchId != null);
  if (!batchIds.length) return historyImages(data);

  const latestBatchId = Math.max(...batchIds);
  return generatedImages
    .filter((image) => image.batch_id === latestBatchId)
    .map((image) => ({
      url: resourceUrl(image.url),
      thumbnail_url: resourceUrl(image.thumbnail_url || image.url),
      generation_time_ms: data.elapsed_ms,
      history_id: data.id,
      history_image_id: image.id,
      batch_id: image.batch_id,
      batch_position: image.batch_position,
    }));
}

function generationBatchImages(data: GenerationBatchDetail): ImageResult[] {
  return data.images
    .filter((image) => image.role === "generated")
    .map((image) => ({
      url: resourceUrl(image.url),
      thumbnail_url: resourceUrl(image.thumbnail_url || image.url),
      generation_time_ms: data.elapsed_ms,
      history_id: data.history_id,
      history_image_id: image.id,
      batch_id: image.batch_id,
      batch_position: image.batch_position,
    }));
}

function syncGenerationTaskProgress(run: GenerationRun, task: GenerationTaskDetail) {
  run.deletedPositions = new Set(task.deleted_positions ?? []);
  run.cancelledPositions = new Set(task.cancelled_positions ?? []);
  const images = (task.images ?? []).map((image) => ({
    url: resourceUrl(image.url),
    thumbnail_url: resourceUrl(image.thumbnail_url || image.url),
    history_id: task.history_id,
    history_image_id: image.id,
    batch_id: image.batch_id,
    batch_position: image.batch_position,
  }));
  run.images = mergeImageResults(run.images, images);
  appendConversationImages(task.history_id, images);
  historyDetailCache.delete(task.history_id);
}

async function deleteGeneratedImage(item: ImageResult, slotPosition?: number) {
  const historyId = item.history_id;
  const imageId = item.history_image_id;
  if (historyId == null || imageId == null || deletingImageIds.value.includes(imageId)) return;

  deletingImageIds.value = [...deletingImageIds.value, imageId];
  try {
    const response = await apiFetch(`${API_BASE}/api/history/${historyId}/images/${imageId}`, {
      method: "DELETE",
      credentials: "include",
    });
    if (!response.ok) {
      throw new Error(readableError(await parseJsonResponse(response), "删除图片失败"));
    }
    const source = imageSource(item);
    generated.value = generated.value.filter((image) => image.history_image_id !== imageId);
    for (const run of generationRuns.values()) {
      run.images = run.images.filter((image) => image.history_image_id !== imageId);
      if (item.batch_id != null && run.batchId === item.batch_id && slotPosition != null) {
        run.deletedPositions.add(slotPosition);
      }
    }
    if (item.batch_id != null && slotPosition != null) {
      for (const group of historyFailureGroups.value) {
        if (group.batchId === item.batch_id) {
          group.positions = group.positions.filter((position) => position !== slotPosition);
        }
      }
      historyFailureGroups.value = historyFailureGroups.value.filter(
        (group) => group.positions.length > 0,
      );
    }
    if (source && lightboxUrl.value === source) lightboxUrl.value = "";
    generationVersion.value++;
    historyDetailCache.delete(historyId);
    await refreshConversationLists();
    error.value = "";
  } catch (exception) {
    error.value = exception instanceof Error ? exception.message : "删除图片失败";
  } finally {
    deletingImageIds.value = deletingImageIds.value.filter((id) => id !== imageId);
  }
}

function requestGeneratedImageDeletion(item: ImageResult, slotPosition?: number) {
  confirmImage.value = { item, slotPosition };
  confirmAction.value = "image";
}

function generationSlotKey(historyId: number, batchId: number, position: number) {
  return `${historyId}-${batchId}-${position}`;
}

async function persistGenerationSlotDeletion(
  historyId: number,
  batchId: number,
  position: number,
) {
  const key = generationSlotKey(historyId, batchId, position);
  if (deletingSlotKeys.value.includes(key)) return;
  deletingSlotKeys.value = [...deletingSlotKeys.value, key];
  try {
    const response = await apiFetch(
      `${API_BASE}/api/history/${historyId}/batches/${batchId}/slots/${position}`,
      { method: "DELETE" },
    );
    if (!response.ok) {
      throw new Error(readableError(await parseJsonResponse(response), "删除卡片失败"));
    }
    historyDetailCache.delete(historyId);
  } finally {
    deletingSlotKeys.value = deletingSlotKeys.value.filter((item) => item !== key);
  }
}

async function deleteGenerationRunSlot(runId: number, position: number) {
  const run = generationRuns.get(runId);
  if (!run || run.deletedPositions.has(position)) return;
  run.deletedPositions.add(position);
  generationVersion.value++;
  if (run.conversationId === null || run.batchId === null) return;
  try {
    await persistGenerationSlotDeletion(run.conversationId, run.batchId, position);
    error.value = "";
  } catch (exception) {
    run.deletedPositions.delete(position);
    error.value = exception instanceof Error ? exception.message : "删除卡片失败";
    generationVersion.value++;
  }
}

async function cancelGenerationRunSlot(runId: number, position: number) {
  const run = generationRuns.get(runId);
  if (!run || run.state !== "running" || run.cancelledPositions.has(position)) return;
  if (run.conversationId === null || run.batchId === null) return;
  const key = `run-${runId}-${position}`;
  if (cancellingSlotKeys.value.includes(key)) return;

  run.cancelledPositions.add(position);
  cancellingSlotKeys.value = [...cancellingSlotKeys.value, key];
  generationVersion.value++;
  try {
    const response = await apiFetch(
      `${API_BASE}/api/history/${run.conversationId}/batches/${run.batchId}/slots/${position}/cancel`,
      { method: "POST", credentials: "include" },
    );
    if (!response.ok) {
      throw new Error(readableError(await parseJsonResponse(response), "取消当前图片失败"));
    }
    historyDetailCache.delete(run.conversationId);
    error.value = "";
  } catch (exception) {
    run.cancelledPositions.delete(position);
    error.value = exception instanceof Error ? exception.message : "取消当前图片失败";
    generationVersion.value++;
  } finally {
    cancellingSlotKeys.value = cancellingSlotKeys.value.filter((item) => item !== key);
  }
}

async function deleteHistoryFailureSlot(group: HistoryFailureGroup, position: number) {
  const historyId = group.historyId;
  const key = generationSlotKey(historyId, group.batchId, position);
  if (deletingSlotKeys.value.includes(key)) return;
  try {
    await persistGenerationSlotDeletion(historyId, group.batchId, position);
    group.positions = group.positions.filter((item) => item !== position);
    historyFailureGroups.value = historyFailureGroups.value.filter(
      (item) => item.positions.length > 0,
    );
    generationVersion.value++;
    await refreshConversationLists();
    error.value = "";
  } catch (exception) {
    error.value = exception instanceof Error ? exception.message : "删除卡片失败";
  }
}

async function modifyGeneratedImage(item: ImageResult) {
  const historyId = item.history_id;
  const imageId = item.history_image_id;
  if (historyId == null || imageId == null || modifyingImageIds.value.includes(imageId)) return;

  modifyingImageIds.value = [...modifyingImageIds.value, imageId];
  try {
    const response = await apiFetch(`${API_BASE}/api/history/${historyId}/images/${imageId}/edit`, {
      credentials: "include",
    });
    const data = await parseJsonResponse(response);
    if (!response.ok) throw new Error(readableError(data, "无法恢复图片参数"));
    const snapshot = data as HistoryImageEditSnapshot;

    disableMultiView();
    prompt.value = snapshot.prompt;
    batchPrompts.value = "";
    const snapshotProviderType = historyProviderType(snapshot);
    const snapshotCapability = capabilities.value.find((item) => item.provider_type === snapshotProviderType && item.model.toLowerCase() === snapshot.model.toLowerCase());
    quality.value = snapshotCapability?.qualities.some((option) => option.value === snapshot.detail)
      ? snapshot.detail
      : snapshotCapability?.default_quality ?? "auto";
    size.value = supportedSizeFor(snapshotProviderType, snapshot.model, snapshot.size);
    resolution.value = supportedResolutionFor(snapshotProviderType, snapshot.model, snapshot.resolution);
    imageCount.value = Math.min(snapshotCapability?.max_output_count ?? 1, Math.max(1, snapshot.image_count));
    regularImageCount.value = imageCount.value;
    currentConversationId.value = snapshot.history_id;
    persistWorkspaceSelection();

    clearReferencePreviews();
    referencePreviews.value = [...snapshot.references]
      .sort((left, right) => left.position - right.position)
      .map((reference) => ({
        key: `edit-${reference.id}`,
        category: reference.category,
        name: reference.filename ?? `历史参考图 ${reference.position + 1}`,
        url: resourceUrl(reference.url),
        file: null,
      }));
    await restoreHistoryApiConfig(snapshot, true);
    error.value = "";

    await nextTick();
    const composer = document.querySelector<HTMLElement>(".composer-dock");
    composer?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
    document.querySelector<HTMLTextAreaElement>(".prompt-row textarea")?.focus();
  } catch (exception) {
    error.value = exception instanceof Error ? exception.message : "无法恢复图片参数";
  } finally {
    modifyingImageIds.value = modifyingImageIds.value.filter((id) => id !== imageId);
  }
}

function pollDelay(signal: AbortSignal, milliseconds: number) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const handleAbort = () => {
      window.clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", handleAbort);
      resolve();
    }, milliseconds);
    signal.addEventListener("abort", handleAbort, { once: true });
  });
}

async function pollGenerationTask(runId: number) {
  const initialRun = generationRuns.get(runId);
  if (!initialRun || initialRun.polling) return;
  if (initialRun.taskId === null) return;
  initialRun.polling = true;
  let transientFailures = 0;
  try {
    while (generationRuns.has(runId)) {
      const run = generationRuns.get(runId);
      if (!run) return;
      if (run.taskId === null) return;
      try {
        if (!run.taskApi) {
          const legacyPath = run.batchId === null ? `/api/history/${run.taskId}` : `/api/history/${run.taskId}/batches/${run.batchId}`;
          const legacyResponse = await apiFetch(`${API_BASE}${legacyPath}`, { signal: run.controller.signal });
          const legacyData = await parseJsonResponse(legacyResponse);
          if (!legacyResponse.ok) throw new Error(readableError(legacyData, `无法查询生成任务（HTTP ${legacyResponse.status}）`));
          const detail = legacyData as HistoryDetail | GenerationBatchDetail;
          transientFailures = 0;
          run.error = "";
          if (detail.status === "pending") { await pollDelay(run.controller.signal, 1500); continue; }
          if (detail.status === "completed") {
            run.images = run.batchId === null ? latestBatchImages(detail as HistoryDetail) : generationBatchImages(detail as GenerationBatchDetail);
            appendConversationImages(run.conversationId ?? run.taskId, run.images);
            const completedBatch = "history_id" in detail
              ? detail
              : detail.batches?.find((batch) => batch.id === run.batchId) ?? detail.batches?.at(-1);
            run.deletedPositions = new Set(completedBatch?.deleted_positions ?? []);
            run.cancelledPositions = new Set(completedBatch?.cancelled_positions ?? []);
            const hasMissingImages = retainMissingGenerationSlots(
              runId,
              completedBatch?.generated_count ?? run.images.length,
              completedBatch?.image_count ?? detail.image_count ?? run.imageCount,
              run.conversationId ?? run.taskId,
            );
            if (!hasMissingImages) {
              stopGenerationRun(runId);
              if (activeGenerationRunId.value === runId) activeGenerationRunId.value = null;
            }
          } else {
            const failedBatch = "history_id" in detail
              ? detail
              : detail.batches?.find((batch) => batch.id === run.batchId) ?? detail.batches?.at(-1);
            const partialImages = "history_id" in detail
              ? generationBatchImages(detail as GenerationBatchDetail)
              : run.batchId === null
                ? latestBatchImages(detail as HistoryDetail)
                : historyImages(detail as HistoryDetail).filter((image) => image.batch_id === run.batchId);
            if (partialImages.length) {
              run.images = partialImages;
              appendConversationImages(run.conversationId ?? run.taskId, partialImages);
            }
            failGenerationRun(
              runId,
              detail.error_message || "生成失败",
              run.conversationId ?? run.taskId,
              "failed",
              Math.max(1, (failedBatch?.image_count ?? run.imageCount) - (failedBatch?.generated_count ?? partialImages.length)),
            );
          }
          return;
        }
        const taskResponse = await apiFetch(`${API_BASE}/api/generation-tasks/${run.taskId}`, {
          credentials: "include",
          signal: run.controller.signal,
        });
        const taskData = await parseJsonResponse(taskResponse) as GenerationTaskDetail | null;
        if (!taskResponse.ok) {
          if (taskResponse.status === 404) { run.taskApi = false; continue; }
          throw new Error(readableError(taskData, `无法查询生成任务（HTTP ${taskResponse.status}）`));
        }
        if (!taskData) throw new Error("服务返回了无效任务状态");
        if (taskData.batch_id != null) run.batchId = taskData.batch_id;
        if (taskData.views?.length) run.views = taskData.views;
        rememberGenerationBatchViews(run.batchId, run.views);
        if (Array.isArray(taskData.deleted_positions)) {
          run.deletedPositions = new Set(taskData.deleted_positions);
        }
        if (Array.isArray(taskData.cancelled_positions)) {
          run.cancelledPositions = new Set(taskData.cancelled_positions);
        }
        if (["queued", "running"].includes(taskData.status)) {
          transientFailures = 0;
          run.error = "";
          if (taskData.status === "running") {
            syncGenerationTaskProgress(run, taskData);
          }
          await pollDelay(run.controller.signal, 1500);
          continue;
        }
        if (taskData.status === "failed" || taskData.status === "cancelled") {
          const message = taskData.error_message
            || (taskData.status === "cancelled" ? "生成任务已取消" : "生成任务失败");
          let failureCount = taskData.image_count ?? run.imageCount;
          if (run.batchId !== null) {
            try {
              const batchResponse = await apiFetch(
                `${API_BASE}/api/history/${taskData.history_id}/batches/${run.batchId}`,
                { credentials: "include", signal: run.controller.signal },
              );
              const batchDetail = await parseJsonResponse(batchResponse) as GenerationBatchDetail;
              if (batchResponse.ok) {
                if (batchDetail.views?.length) run.views = batchDetail.views;
                rememberGenerationBatchViews(run.batchId, run.views);
                run.deletedPositions = new Set(batchDetail.deleted_positions ?? []);
                run.cancelledPositions = new Set(batchDetail.cancelled_positions ?? []);
                run.images = generationBatchImages(batchDetail);
                appendConversationImages(taskData.history_id, run.images);
                failureCount = Math.max(1, batchDetail.image_count - batchDetail.generated_count);
              }
            } catch (exception) {
              if (exception instanceof DOMException && exception.name === "AbortError") return;
            }
          }
          failGenerationRun(
            runId,
            message,
            taskData.history_id,
            taskData.status === "cancelled" ? "cancelled" : "failed",
            failureCount,
          );
          await refreshConversationLists();
          return;
        }
        const detailPath = run.batchId === null ? `/api/history/${taskData.history_id}` : `/api/history/${taskData.history_id}/batches/${run.batchId}`;
        const detailResponse = await apiFetch(`${API_BASE}${detailPath}`, { signal: run.controller.signal });
        const detail = await parseJsonResponse(detailResponse) as HistoryDetail | GenerationBatchDetail;
        if (!detailResponse.ok) throw new Error(readableError(detail, "无法查询生成结果"));
        if ("history_id" in detail) {
          if (detail.views?.length) run.views = detail.views;
          rememberGenerationBatchViews(run.batchId, run.views);
          run.deletedPositions = new Set(detail.deleted_positions ?? []);
          run.cancelledPositions = new Set(detail.cancelled_positions ?? []);
        }

        if (run.batchId === null) {
          historyDetailCache.set(taskData.history_id, Promise.resolve(detail as HistoryDetail));
        } else {
          historyDetailCache.delete(taskData.history_id);
        }
        transientFailures = 0;
        run.error = "";
        if (detail.status === "completed") {
          run.images = run.batchId === null
            ? latestBatchImages(detail as HistoryDetail)
            : generationBatchImages(detail as GenerationBatchDetail);
          if (run.batchId === null) preloadHistoryImages(detail as HistoryDetail);
          appendConversationImages(taskData.history_id, run.images);
          if (currentConversationId.value === taskData.history_id && activeHistoryId.value === null) {
            error.value = "";
          }
          const completedBatch = "history_id" in detail
            ? detail
            : detail.batches?.find((batch) => batch.id === run.batchId) ?? detail.batches?.at(-1);
          run.deletedPositions = new Set(completedBatch?.deleted_positions ?? []);
          run.cancelledPositions = new Set(completedBatch?.cancelled_positions ?? []);
          const hasMissingImages = retainMissingGenerationSlots(
            runId,
            completedBatch?.generated_count ?? run.images.length,
            completedBatch?.image_count ?? detail.image_count ?? run.imageCount,
            taskData.history_id,
          );
          if (!hasMissingImages) {
            stopGenerationRun(runId);
            if (activeGenerationRunId.value === runId) activeGenerationRunId.value = null;
          }
        } else {
          failGenerationRun(runId, detail.error_message || "生成失败", taskData.history_id);
        }
        await refreshConversationLists();
        return;
      } catch (exception) {
        if (exception instanceof DOMException && exception.name === "AbortError") return;
        transientFailures++;
        const message = exception instanceof Error ? exception.message : "无法查询生成任务";
        run.error = transientFailures > 5
          ? `暂时无法同步生成进度，正在重试：${message}`
          : message;
        generationVersion.value++;
        const retryDelay = transientFailures <= 5
          ? 2500
          : Math.min(15000, 2500 * 2 ** Math.min(transientFailures - 5, 3));
        await pollDelay(run.controller.signal, retryDelay);
        continue;
      }
    }
  } finally {
    const run = generationRuns.get(runId);
    if (run) run.polling = false;
  }
}

function pendingElapsedMs(createdAt: string) {
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(createdAt) ? createdAt : `${createdAt}Z`;
  const createdAtMs = Date.parse(normalized);
  return Number.isFinite(createdAtMs) ? Math.max(0, Date.now() - createdAtMs) : 0;
}

async function restorePendingGenerationTasks(activateFirst = true) {
  let activeTasks: GenerationTaskDetail[] | null = null;
  try {
    const response = await apiFetch(`${API_BASE}/api/generation-tasks`);
    if (response.ok) {
      const data = await parseJsonResponse(response);
      activeTasks = Array.isArray(data) ? data as GenerationTaskDetail[] : [];
    }
  } catch {
    // Older servers do not expose the task list; fall back to pending history records below.
  }
  if (activeTasks !== null) {
    const historyById = new Map<number, HistorySummary>();
    for (const project of projects.value) {
      for (const item of project.history) historyById.set(item.id, item);
    }
    let activatedTask = false;
    for (const task of activeTasks) {
      const item = historyById.get(task.history_id);
      if (!item || [...generationRuns.values()].some((run) => run.taskId === task.id && run.state === "running")) continue;
      const project = projects.value.find((candidate) => candidate.id === task.project_id)
        ?? projects.value.find((candidate) => candidate.history.some((historyItem) => historyItem.id === task.history_id));
      const taskProvider = task.provider ?? item.provider;
      const taskModel = task.model ?? item.model;
      const providerType = historyProviderType({ provider: taskProvider, model: taskModel });
      const matchingConfig = apiKeyConfigs.value.find(
        (config) => config.id === task.api_key_config_id,
      ) ?? apiKeyConfigs.value.find(
        (config) => config.provider_type === providerType && config.model === taskModel,
      );
      const activateTask = activateFirst && !activatedTask;
      startGenerationRun(
        task.id,
        new AbortController(),
        {
          taskId: task.id,
          batchId: task.batch_id ?? null,
          conversationId: task.history_id,
          polling: false,
          taskApi: true,
          projectId: project?.id ?? null,
          provider: taskProvider,
          model: taskModel,
          apiKeyConfigId: matchingConfig?.id ?? null,
          prompt: task.prompt ?? item.prompt,
          batchPrompts: "",
          views: task.views ?? [],
          imageCount: task.image_count ?? item.image_count,
          quality: task.detail ?? item.detail,
          size: supportedSizeFor(providerType, taskModel, task.size ?? item.size),
          resolution: supportedResolutionFor(providerType, taskModel, task.resolution ?? item.resolution),
          referenceFiles: [],
        },
        pendingElapsedMs(task.created_at ?? item.created_at),
        activateTask,
      );
      const restoredRun = generationRuns.get(task.id);
      if (restoredRun) {
        restoredRun.deletedPositions = new Set(task.deleted_positions ?? []);
        restoredRun.cancelledPositions = new Set(task.cancelled_positions ?? []);
      }
      if (activateTask) {
        activatedTask = true;
        if (project) {
          selectedProjectId.value = project.id;
          history.value = project.history;
        }
        const run = generationRuns.get(task.id);
        if (run) {
          try {
            const detail = await fetchHistoryDetail(task.history_id);
            run.images = historyImages(detail);
            generated.value = [...run.images];
            restoreHistoryFailureGroups(detail);
            referencePreviews.value = detail.images
              .filter((image) => image.role === "reference")
              .sort((left, right) => left.position - right.position)
              .map((image) => ({
                key: `restored-${image.id}`,
                category: image.reference_category ?? "person",
                name: image.filename ?? `历史参考图 ${image.position + 1}`,
                url: resourceUrl(image.url),
                file: null,
              }));
            preloadHistoryImages(detail);
          } catch {
            generated.value = [];
          }
          provider.value = run.provider;
          model.value = run.model;
          activeApiKeyConfigId.value = run.apiKeyConfigId;
          prompt.value = run.prompt;
          restoreMultiViewState(run.views);
          if (!run.views.length) {
            imageCount.value = run.imageCount;
            regularImageCount.value = imageCount.value;
          }
          rememberGenerationBatchViews(run.batchId, run.views);
          quality.value = run.quality;
          size.value = run.size;
          resolution.value = run.resolution;
        }
        currentConversationId.value = task.history_id;
        activeHistoryId.value = null;
        persistWorkspaceSelection();
        generationVersion.value++;
      }
      void pollGenerationTask(task.id);
    }
    return;
  }
  for (const project of projects.value) {
    for (const item of project.history) {
      if (
        item.kind !== "generate"
        || item.status !== "pending"
        || [...generationRuns.values()].some((run) => run.taskId === item.id && run.state === "running")
      ) continue;
      const providerType = historyProviderType(item);
      const matchingConfig = apiKeyConfigs.value.find(
        (config) => config.provider_type === providerType && config.model === item.model,
      );
      startGenerationRun(
        item.id,
        new AbortController(),
        {
          taskId: item.id,
          batchId: null,
          conversationId: item.id,
          polling: false,
          taskApi: false,
          projectId: project.id,
          provider: item.provider,
          model: item.model,
          apiKeyConfigId: matchingConfig?.id ?? null,
          prompt: item.prompt,
          batchPrompts: "",
          views: [],
          imageCount: item.image_count,
          quality: item.detail,
          size: supportedSizeFor(providerType, item.model, item.size),
          resolution: supportedResolutionFor(providerType, item.model, item.resolution),
          referenceFiles: [],
        },
        pendingElapsedMs(item.created_at),
        false,
      );
      void pollGenerationTask(item.id);
    }
  }
}

async function generateImage() {
  if (generationSubmitting.value) return;
  if (!provider.value || !model.value) {
    error.value = "请先配置 API Key 和模型名称";
    return;
  }
  const capability = selectedCapability.value;
  if (!capability) {
    error.value = "当前模型未登记，无法生成图片";
    return;
  }
  if (multiViewValidationMessage.value) {
    error.value = multiViewValidationMessage.value;
    return;
  }
  const prompts = (multiViewEnabled.value ? "" : batchPrompts.value)
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  const requestPrompt = prompt.value.trim()
    || prompts[0]
    || (multiViewEnabled.value ? "基于参考图，在同一场景中展示同一主体" : "请生成一张图片");
  const generationViews = multiViewEnabled.value ? buildGenerationViews(requestPrompt) : [];
  if (generationViews.some((view) => view.prompt.length > 4000)) {
    error.value = "加入多视角要求后提示词超过 4000 字，请缩短提示词";
    return;
  }
  const generationProvider = provider.value;
  const generationModel = model.value;
  const generationConfigId = activeApiKeyConfigId.value;
  const generationProjectId = selectedProjectId.value;
  const selectedProject = projects.value.find((project) => project.id === generationProjectId);
  const activeConversationBelongsToProject = currentConversationId.value !== null
    && [...generationRuns.values()].some(
      (run) => run.conversationId === currentConversationId.value && run.projectId === generationProjectId,
    );
  const generationConversationId = currentConversationId.value !== null
    && (selectedProject?.history.some((item) => item.id === currentConversationId.value)
      || activeConversationBelongsToProject)
    ? currentConversationId.value
    : null;
  const generationImageCount = multiViewEnabled.value ? 1 : imageCount.value;
  const generationExpectedImageCount = generationViews.length
    || expectedGenerationImageCount(requestPrompt, prompts, generationImageCount);
  if (generationExpectedImageCount > 40) {
    error.value = "单次生成任务最多支持 40 张图片";
    return;
  }
  const perPromptImageCount = generationExpectedImageCount
    / Math.max(1, generationViews.length || prompts.length || 1);
  if (perPromptImageCount > capability.max_output_count) {
    error.value = `当前模型每条提示词最多支持 ${capability.max_output_count} 张图片`;
    return;
  }
  const generationQuality = quality.value;
  const generationSize = size.value;
  const generationResolution = resolution.value;
  let generationReferenceFiles: File[];
  try {
    generationReferenceFiles = await referenceFilesForRequest();
  } catch (exception) {
    error.value = exception instanceof Error ? exception.message : "无法读取参考图片";
    return;
  }
  const generationReferenceSnapshots = generationReferenceFiles.map((file, index) => ({
    file,
    category: referencePreviews.value[index]?.category ?? "person",
  }));
  if (multiViewEnabled.value && !generationReferenceSnapshots.some(
    (reference) => reference.category === multiViewTarget.value,
  )) {
    error.value = multiViewTarget.value === "person" ? "请先添加人物参考图" : "请先添加物品参考图";
    return;
  }
  const generationProviderType = selectedProviderType.value;
  if (generationReferenceFiles.length > maxReferenceImages.value) {
    error.value = `当前模型最多支持 ${maxReferenceImages.value} 张参考图`;
    return;
  }
  const runId = Date.now() + Math.random();
  const controller = new AbortController();
  generationSubmitting.value = true;
  startGenerationRun(runId, controller, {
    taskId: null,
    batchId: null,
    conversationId: generationConversationId,
    polling: false,
    taskApi: false,
    projectId: generationProjectId,
    provider: generationProvider,
    model: generationModel,
    apiKeyConfigId: generationConfigId,
    prompt: requestPrompt,
    batchPrompts: batchPrompts.value,
    views: generationViews,
    imageCount: generationExpectedImageCount,
    quality: generationQuality,
    size: generationSize,
    resolution: generationResolution,
    referenceFiles: generationReferenceSnapshots,
  });
  error.value = "";
  const continuingImages = generationConversationId !== null ? [...generated.value] : [];
  const provisionalRun = generationRuns.get(runId);
  if (provisionalRun) provisionalRun.images = continuingImages;
  if (generationConversationId === null) generated.value = [];
  activeHistoryId.value = null;
  if (generationConversationId !== null) historyDetailCache.delete(generationConversationId);
  try {
    let endpoint = `${API_BASE}/api/generate`;
    let requestInit: RequestInit;
    if (generationReferenceFiles.length) {
      endpoint += "/reference";
      const form = new FormData();
      form.append("provider", generationProvider);
      form.append("model", generationModel);
      form.append("prompt", requestPrompt);
      form.append("count", String(generationImageCount));
      if (capability.sizes.length) {
        form.append("size", generationSize);
      } else if (capability.aspect_ratios.length) {
        form.append("aspect_ratio", generationSize);
      }
      if (capability.resolutions.length) {
        form.append("resolution", generationResolution);
      }
      if (capability.qualities.length) {
        form.append("detail", generationQuality);
      }
      if (generationProviderType === "gpt") {
        form.append("output_format", "png");
        form.append("background", "auto");
        form.append("moderation", "auto");
      }
      if (generationConfigId !== null) form.append("api_key_config_id", String(generationConfigId));
      if (generationProjectId !== null) form.append("project_id", String(generationProjectId));
      if (generationConversationId !== null) form.append("conversation_id", String(generationConversationId));
      if (generationViews.length) form.append("views", JSON.stringify(generationViews));
      else for (const batchPrompt of prompts) form.append("prompts", batchPrompt);
      for (const reference of generationReferenceSnapshots) {
        form.append("images", reference.file);
        form.append("image_categories", reference.category);
      }
      requestInit = { method: "POST", signal: controller.signal, body: form };
    } else {
      requestInit = {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          provider: generationProvider,
          model: generationModel,
          ...(generationConfigId !== null ? { api_key_config_id: generationConfigId } : {}),
          prompt: requestPrompt,
          ...(generationViews.length ? { views: generationViews } : { prompts: prompts.length ? prompts : null }),
          count: generationImageCount,
          ...(capability.sizes.length ? {
            size: generationSize,
          } : {}),
          ...(capability.aspect_ratios.length ? {
            aspect_ratio: generationSize,
          } : {}),
          ...(capability.resolutions.length ? {
            resolution: generationResolution,
          } : {}),
          ...(capability.qualities.length ? {
            detail: generationQuality,
          } : {}),
          ...(generationProviderType === "gpt" ? {
            output_format: "png",
            background: "auto",
            moderation: "auto",
          } : {}),
          project_id: generationProjectId,
          ...(generationConversationId !== null ? { conversation_id: generationConversationId } : {}),
        }),
      };
    }
    const response = await apiFetch(endpoint, requestInit);
    const data = await parseJsonResponse(response);
    if (!response.ok) {
      throw new Error(readableError(data, `生成失败（HTTP ${response.status}）`));
    }
    if (!data) throw new Error("服务返回了无效响应");
    const taskId = Number(data.task_id);
    const historyId = Number(data.history_id ?? taskId);
    if (Number.isInteger(taskId) && taskId > 0) {
      const rawBatchId = Number(data.batch_id);
      const batchId = Number.isInteger(rawBatchId) && rawBatchId > 0 ? rawBatchId : null;
      const taskApi = typeof data.status_url === "string"
        && data.status_url.startsWith("/api/generation-tasks/");
      if (!attachGenerationTask(runId, taskId, batchId, historyId, taskApi)) return;
      currentConversationId.value = historyId;
      persistWorkspaceSelection();
      await refreshConversationLists();
      generationSubmitting.value = false;
      void pollGenerationTask(runId);
      return;
    }
    const run = generationRuns.get(runId);
    if (run) {
      const returnedImages = Array.isArray(data.images) ? data.images as ImageResult[] : [];
      run.images = returnedImages;
      retainMissingGenerationSlots(runId, returnedImages.length, run.imageCount, run.conversationId ?? undefined);
      generationVersion.value++;
    }
    if (activeGenerationRunId.value === runId) generated.value = data.images ?? [];
    await refreshConversationLists();
  } catch (exception) {
    if (!(exception instanceof DOMException && exception.name === "AbortError")) {
      const message = exception instanceof Error ? exception.message : "生成失败";
      failGenerationRun(runId, message);
      await refreshConversationLists();
    }
  } finally {
    generationSubmitting.value = false;
    const run = generationRuns.get(runId);
    if (run?.taskId === null && run.state === "running") {
      stopGenerationRun(runId);
      if (activeGenerationRunId.value === runId) activeGenerationRunId.value = null;
    }
  }
}

function handleGenerateClick() {
  void generateImage();
}

async function analyzeImage() {
  if (!referencePreviews.value.length) return;
  busy.value = "analyze";
  error.value = "";
  generated.value = [];
  activeHistoryId.value = null;
  let referenceFiles: File[];
  try {
    referenceFiles = await referenceFilesForRequest();
  } catch (exception) {
    error.value = exception instanceof Error ? exception.message : "无法读取参考图片";
    busy.value = "";
    return;
  }
  const form = new FormData();
  form.append("provider", provider.value);
  form.append("model", model.value);
  form.append("prompt", prompt.value || "请描述这张图片");
  if (activeApiKeyConfigId.value !== null) {
    form.append("api_key_config_id", String(activeApiKeyConfigId.value));
  }
  form.append("detail", selectedProviderType.value === "gpt" ? quality.value : "auto");
  if (selectedProjectId.value !== null) form.append("project_id", String(selectedProjectId.value));
  for (const referenceFile of referenceFiles) form.append("images", referenceFile);
  try {
    const response = await apiFetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      body: form,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(readableError(data, "分析失败"));
    prompt.value = promptWithAnalysis(prompt.value, data.text);
    await loadProjects();
  } catch (exception) {
    error.value = exception instanceof Error ? exception.message : "分析失败";
    await loadProjects(true);
  } finally {
    busy.value = "";
  }
}

function imageSource(item: ImageResult) {
  if (item.url) return resourceUrl(item.url);
  if (!item.base64_data) return "";
  const encoded = item.base64_data.trim();
  return encoded.startsWith("data:") ? encoded : `data:image/png;base64,${encoded}`;
}

function navigateToSkills() {
  window.history.pushState({}, "", "/skills");
  currentView.value = "skills";
}

function navigateToPrompts() {
  window.history.pushState({}, "", "/prompts");
  currentView.value = "prompts";
}

async function loadPromptCategorySuggestions() {
  try {
    const response = await apiFetch(`${API_BASE}/api/prompts`);
    const data = await parseJsonResponse(response);
    if (!response.ok || !Array.isArray(data)) return;
    promptCategorySuggestions.value = [...new Set(
      data.map((entry: { category?: string }) => String(entry.category ?? "").trim()).filter(Boolean),
    )].sort((left, right) => left.localeCompare(right, "zh-CN"));
  } catch {
    // Category suggestions are optional; free text entry remains available.
  }
}

function openPromptEditor(sourcePrompt = prompt.value, entry?: PromptEntry | null) {
  const text = sourcePrompt.trim();
  if (!text) {
    promptSaveStatus.value = "请先输入提示词";
    return;
  }
  promptEditorEntryId.value = entry?.id ?? null;
  promptEditorInitial.value = {
    name: entry?.name ?? "",
    prompt: text,
    category: entry?.category ?? "",
  };
  promptEditorOpen.value = true;
  promptSaveStatus.value = "";
  void loadPromptCategorySuggestions();
}

async function savePromptEntry(form: PromptForm) {
  try {
    const editingId = promptEditorEntryId.value;
    const response = await apiFetch(
      `${API_BASE}/api/prompts${editingId === null ? "" : `/${editingId}`}`,
      {
        method: editingId === null ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      },
    );
    const data = await parseJsonResponse(response);
    if (!response.ok) throw new Error(readableError(data, "提示词保存失败"));
    promptEditorOpen.value = false;
    promptEditorEntryId.value = null;
    promptSaveStatus.value = editingId === null ? "提示词已保存" : "提示词已更新";
    void loadPromptCategorySuggestions();
  } catch (exception) {
    promptSaveStatus.value = exception instanceof Error ? exception.message : "提示词保存失败";
  }
}

function applySavedPrompt(savedPrompt: string, name: string) {
  prompt.value = savedPrompt;
  promptSaveStatus.value = `已应用“${name}”`;
  navigateToWorkspace();
}

function openPromptPicker() {
  promptPickerOpen.value = true;
}

function closePromptPicker() {
  promptPickerOpen.value = false;
}

function applyPromptSelection(entry: PromptPickerEntry) {
  const current = prompt.value.trim();
  if (!current || current === entry.prompt.trim()) {
    prompt.value = entry.prompt;
    promptSaveStatus.value = `已导入“${entry.name}”`;
    closePromptPicker();
    return;
  }
  pendingPromptSelection.value = entry;
  closePromptPicker();
  promptPickerConfirmOpen.value = true;
}

function confirmPromptSelection() {
  if (!pendingPromptSelection.value) return;
  prompt.value = pendingPromptSelection.value.prompt;
  promptSaveStatus.value = `已导入“${pendingPromptSelection.value.name}”`;
  pendingPromptSelection.value = null;
  promptPickerConfirmOpen.value = false;
}

function cancelPromptSelection() {
  pendingPromptSelection.value = null;
  promptPickerConfirmOpen.value = false;
}

function managePromptsFromPicker() {
  closePromptPicker();
  navigateToPrompts();
}

const currentSkillWorkflow = computed<SkillWorkflow>(() => ({
  prompt_template: prompt.value.trim() || "请描述你想生成的画面",
  provider_type: selectedProviderType.value,
  model: model.value,
  quality: quality.value,
  size: size.value,
  resolution: resolution.value,
  image_count: multiViewEnabled.value ? Math.max(1, selectedMultiViewOptions.value.length) : imageCount.value,
  reference_requirements: [...new Set(referencePreviews.value.map((item) => item.category))],
  multi_view: {
    enabled: multiViewEnabled.value,
    target: multiViewTarget.value,
    preset_keys: [...selectedMultiViewKeys.value],
    custom_views: customMultiViews.value.map((item) => ({ ...item })),
  },
}));

function applySkillWorkflow(workflow: SkillWorkflow, title: string) {
  void (async () => {
    await restoreHistoryApiConfig({ provider: workflow.provider_type, model: workflow.model }, true);
    prompt.value = workflow.prompt_template;
    quality.value = workflow.quality || quality.value;
    size.value = supportedSizeFor(workflow.provider_type, workflow.model, workflow.size);
    resolution.value = supportedResolutionFor(workflow.provider_type, workflow.model, workflow.resolution);
    imageCount.value = Math.min(
      workflow.image_count || 1,
      (selectedCapability.value?.max_output_count ?? workflow.image_count ?? 1),
    );
    regularImageCount.value = imageCount.value;
    restoreMultiViewState(workflow.multi_view?.enabled ? [
        ...workflow.multi_view.preset_keys.map((key) => ({ key: `${workflow.multi_view.target}_${key}`, label: key, prompt: "" })),
        ...workflow.multi_view.custom_views.map((view) => ({ key: `${workflow.multi_view.target}_${view.key}`, label: view.label, prompt: "" })),
      ] : undefined);
    error.value = `已应用技能“${title}”，请补充提示词变量或参考图后生成`;
    navigateToWorkspace();
  })();
}

function thumbnailSource(item: ImageResult) {
  return item.thumbnail_url ? resourceUrl(item.thumbnail_url) : imageSource(item);
}

function handleThumbnailError(event: Event, item: ImageResult) {
  const image = event.currentTarget;
  const original = imageSource(item);
  if (image instanceof HTMLImageElement && original && image.getAttribute("src") !== original) {
    image.src = original;
  }
}

function openLightbox(item: ImageResult) {
  const source = imageSource(item);
  if (source) lightboxUrl.value = source;
}

function openReferenceLightbox(reference: ReferencePreview) {
  if (reference.url) lightboxUrl.value = reference.url;
}

function closeLightbox() {
  lightboxUrl.value = "";
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.key !== "Escape") return;
  if (promptPickerOpen.value) closePromptPicker();
  else if (promptPickerConfirmOpen.value) cancelPromptSelection();
  else if (openParameterMenu.value) closeParameterMenu();
  else if (lightboxUrl.value) closeLightbox();
}

function handleDocumentPointerDown(event: PointerEvent) {
  const target = event.target;
  if (target instanceof Element && !target.closest(".parameter-toolbar")) {
    closeParameterMenu();
  }
}

onMounted(async () => {
  window.addEventListener("keydown", handleGlobalKeydown);
  document.addEventListener("pointerdown", handleDocumentPointerDown);
  try {
    const response = await apiFetch(`${API_BASE}/api/auth/me`);
    if (!response.ok) { authView.value = "login"; return; }
    applyCurrentUser(await response.json());
    if (currentView.value === "admin" && !currentIsAdmin.value) navigateToWorkspace();
    authView.value = "workspace";
    await loadProviders();
    await loadRuntimeSettings();
    await loadProjects(true);
    if (currentView.value === "admin") await loadAdminUsers();
  } catch {
    error.value = "无法加载服务商，请先启动后端";
  }
});
function handlePopState() {
  currentView.value = resolveCurrentView();
  if (currentView.value === "admin" && !currentIsAdmin.value) {
    navigateToWorkspace();
    return;
  }
  if (currentView.value === "admin") void loadAdminUsers();
  if (currentView.value === "workspace" && activeGenerationRunId.value !== null) {
    void restoreGenerationRun(activeGenerationRunId.value);
  }
}
window.addEventListener("popstate", handlePopState);
onUnmounted(() => {
  finishWorkspaceResize();
  window.removeEventListener("keydown", handleGlobalKeydown);
  window.removeEventListener("popstate", handlePopState);
  document.removeEventListener("pointerdown", handleDocumentPointerDown);
  if (verificationCooldownTimer !== undefined) window.clearInterval(verificationCooldownTimer);
  if (adminSearchTimer !== undefined) window.clearTimeout(adminSearchTimer);
  for (const run of generationRuns.values()) {
    if (run.timer !== undefined) window.clearInterval(run.timer);
    run.controller.abort();
  }
  generationRuns.clear();
  historyDetailCache.clear();
  for (const image of historyImagePreloads.values()) image.src = "";
  historyImagePreloads.clear();
  clearReferencePreviews();
});
</script>

<template>
  <main class="studio-shell" :class="`background-${backgroundEffect}`">
    <FlowingGridBackground v-if="backgroundEffect === 'gravity-grid'" />
    <SnowfallBackground v-else />
    <section v-if="authView !== 'workspace'" class="auth-page">
      <div v-if="authView === 'checking'" class="auth-loading" aria-live="polite">正在检查登录状态…</div>
      <div v-else class="auth-layout">
        <aside class="auth-intro">
          <img class="auth-brand-mark" :src="pictoraMark" alt="Pictora 图标" />
          <p class="auth-eyebrow">画境 (Pictora)</p>
          <h1>把想法变成画面</h1>
          <p class="auth-intro-copy">生成的不仅是图片，而是画中意境。</p>
          <div class="auth-intro-rule" aria-hidden="true"></div>
          <p class="auth-intro-note">登录后即可继续使用你的项目与历史记录。</p>
        </aside>

        <form class="auth-form" @submit.prevent="authView === 'register' ? submitAuth('register') : submitAuth('login')">
          <div class="auth-form-heading">
            <div>
              <p class="auth-kicker">欢迎回来</p>
              <h2>{{ authView === 'register' ? '创建 Pictora 账号' : '登录 Pictora' }}</h2>
            </div>
            <span class="auth-step">{{ authView === 'register' ? '02' : '01' }}</span>
          </div>

          <div class="auth-mode" role="tablist" aria-label="认证方式">
            <button type="button" role="tab" :aria-selected="authView === 'login'" :class="{ active: authView === 'login' }" @click="authView = 'login'">登录</button>
            <button type="button" role="tab" :aria-selected="authView === 'register'" :class="{ active: authView === 'register' }" @click="authView = 'register'">注册</button>
          </div>

          <div class="auth-fields">
            <label v-if="authView === 'register'">用户名<input v-model="username" autocomplete="username" placeholder="输入用户名" required /></label>
            <label>{{ authView === 'register' ? '邮箱' : '邮箱或旧用户名' }}<input v-model="email" :type="authView === 'register' ? 'email' : 'text'" :autocomplete="authView === 'register' ? 'email' : 'username'" :placeholder="authView === 'register' ? 'name@gmail.com' : '邮箱或旧用户名'" required /></label>
            <label v-if="authView === 'register'">邮箱验证码<span class="verification-field"><input v-model="verificationCode" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}" placeholder="6 位验证码" required /><button type="button" class="secondary-action verification-action" :disabled="verificationSending || verificationCooldown > 0" @click="sendVerificationCode">{{ verificationSending ? '发送中' : verificationCooldown > 0 ? `${verificationCooldown} 秒` : '获取验证码' }}</button></span></label>
            <label>密码<input v-model="password" type="password" :autocomplete="authView === 'register' ? 'new-password' : 'current-password'" placeholder="至少 6 位字符" minlength="6" required /></label>
            <label v-if="authView === 'register'">确认密码<input v-model="passwordConfirmation" type="password" autocomplete="new-password" placeholder="再次输入密码" minlength="6" required /></label>
          </div>
          <p v-if="authError" class="error-message" role="alert">{{ authError }}</p>
          <button type="submit" class="primary-action auth-submit" :disabled="authSubmitting">{{ authSubmitting ? '提交中...' : authView === 'register' ? '注册并进入工作台' : '登录' }}</button>
          <p class="auth-footnote">{{ authView === 'register' ? '已有账号？' : '还没有账号？' }}<button type="button" class="auth-link" @click="authView = authView === 'register' ? 'login' : 'register'">{{ authView === 'register' ? '返回登录' : '立即注册' }}</button></p>
        </form>
      </div>
    </section>
    <template v-else>
    <header class="topbar">
      <div class="topbar-leading">
        <div class="brand">
          <img class="brand-mark" :src="pictoraMark" alt="Pictora 图标" />
          <div><strong>Pictora</strong><small>AI 创作工作台</small></div>
        </div>
      </div>
      <div class="topbar-actions">
        <span class="status-indicator" :class="{ configured: apiKeyConfigured }">
          <i></i>{{ apiKeyConfigured ? "API Key 已配置" : "请在设置页面配置 API Key" }}
        </span>
        <span class="user-chip" :title="currentEmail"><UserRound :size="15" /><span>{{ currentUsername }}</span></span>
        <button v-if="currentView === 'workspace'" type="button" class="secondary-action topbar-command" data-action="skills" title="技能" @click="navigateToSkills"><Sparkles :size="16" />技能</button>
        <button v-if="currentView === 'workspace'" type="button" class="secondary-action topbar-command" data-action="prompts" title="提示词管理" @click="navigateToPrompts"><BookmarkPlus :size="16" />提示词</button>
        <button v-if="currentView === 'workspace'" type="button" class="secondary-action topbar-command" data-action="settings" title="设置" @click="navigateToSettings"><Settings :size="16" />设置</button>
        <button v-if="currentIsAdmin && currentView !== 'admin'" type="button" class="secondary-action topbar-command" data-action="admin" title="用户管理" @click="navigateToAdmin"><ShieldCheck :size="16" />管理</button>
        <button v-if="currentView !== 'workspace'" type="button" class="secondary-action topbar-command" data-action="back-to-workspace" title="返回工作台" @click="navigateToWorkspace"><ArrowLeft :size="16" />返回工作台</button>
      </div>
    </header>

    <section v-if="currentView === 'settings'" class="settings-page">
      <header class="settings-page-heading"><span>Pictora</span><h1>设置</h1></header>
      <section class="settings-section settings-interface">
        <div class="settings-heading"><h1>接口配置</h1><div class="settings-heading-actions"><button type="button" class="secondary-action" data-action="add-api-key" @click="beginAddConfig">添加 API Key</button><a class="api-key-link" href="https://sub.beibeihai.xyz/home" target="_blank" rel="noopener noreferrer"><ExternalLink :size="16" />获取 API Key</a></div></div>
        <p>{{ apiKeyConfigured ? '已有可用配置' : '尚未配置 API Key' }}</p>
        <label v-if="legacySettingsMode">API Key<input v-model="settingsApiKey" data-field="api-key" type="password" autocomplete="off" @blur="saveSettingsApiKey" /></label>
        <div v-else class="api-config-list">
          <p v-if="apiKeyConfigs.length === 0" class="api-config-empty">暂无 API Key 配置</p>
          <div v-for="config in apiKeyConfigs" :key="config.id" class="api-config-row" :class="{ active: config.id === activeApiKeyConfigId }">
            <div class="api-config-identity"><strong>{{ config.alias }}</strong><span>{{ providerTypeLabel(config.provider_type) }}</span></div>
            <div class="api-config-actions"><span>{{ config.api_key_configured ? '已配置' : '未配置' }}</span><button type="button" class="secondary-action" data-action="test-api-key" @click="testConfig(config)">{{ testingConfigId === config.id ? '测试中...' : '测试' }}</button><button type="button" class="secondary-action" @click="editConfig(config)">编辑</button><button type="button" class="secondary-action" data-action="delete-api-key" @click="deleteConfig(config)">删除</button></div>
            <div v-if="apiKeyTestResults[config.id]" class="api-config-test-result">
              <p class="api-key-test-message" role="status">{{ apiKeyTestResults[config.id].message }}</p>
              <div v-if="apiKeyTestResults[config.id].models.length" class="api-key-models">
                <button
                  type="button"
                  class="api-key-models-toggle"
                  :aria-expanded="apiKeyModelListExpanded(config.id)"
                  :aria-controls="`api-key-model-list-${config.id}`"
                  @click="toggleApiKeyModelList(config.id)"
                >
                  <strong>可用模型（{{ apiKeyTestResults[config.id].models.length }}）</strong>
                  <ChevronDown v-if="apiKeyModelListExpanded(config.id)" :size="16" />
                  <ChevronRight v-else :size="16" />
                </button>
                <ul v-if="apiKeyModelListExpanded(config.id)" :id="`api-key-model-list-${config.id}`"><li v-for="availableModel in apiKeyTestResults[config.id].models" :key="availableModel.id">{{ availableModel.id }}</li></ul>
              </div>
            </div>
          </div>
          <form v-if="showConfigForm" class="api-config-form" @submit.prevent="saveConfig">
            <label>别名<input v-model="configForm.alias" data-field="config-alias" maxlength="80" required /></label>
            <label>API Key<input v-model="configForm.api_key" data-field="config-api-key" type="password" autocomplete="off" :placeholder="editingConfigId ? '留空以保留现有 Key' : ''" /></label>
            <fieldset class="config-provider-field" data-field="config-provider">
              <legend>类型</legend>
              <div class="config-provider-options" role="group" aria-label="API 类型">
                <button type="button" class="config-provider-option" data-provider-type="gpt" :aria-pressed="configForm.provider_type === 'gpt'" :class="{ active: configForm.provider_type === 'gpt' }" @click="configForm.provider_type = 'gpt'">OpenAI</button>
                <button type="button" class="config-provider-option" data-provider-type="gemini" :aria-pressed="configForm.provider_type === 'gemini'" :class="{ active: configForm.provider_type === 'gemini' }" @click="configForm.provider_type = 'gemini'">Gemini</button>
                <button type="button" class="config-provider-option" data-provider-type="grok" :aria-pressed="configForm.provider_type === 'grok'" :class="{ active: configForm.provider_type === 'grok' }" @click="configForm.provider_type = 'grok'">Grok</button>
              </div>
            </fieldset>
            <div class="api-config-form-actions"><button type="submit" class="primary-action">{{ editingConfigId ? '保存修改' : '添加配置' }}</button><button type="button" class="secondary-action" data-action="cancel-api-key-form" @click="resetConfigForm">取消</button><span v-if="settingsConfigError" class="settings-error">{{ settingsConfigError }}</span></div>
          </form>
        </div>
      </section>

      <div class="settings-preferences">
        <section class="settings-section settings-update" aria-labelledby="version-update-title">
          <div class="version-update-copy">
            <div class="version-update-heading"><RefreshCw :size="18" /><h2 id="version-update-title">版本更新</h2></div>
            <div class="version-meta">
              <span><small>当前版本</small><strong>{{ CLIENT_VERSION }}</strong></span>
              <span v-if="serverVersion"><small>服务器版本</small><strong>{{ serverVersion }}</strong></span>
            </div>
            <p v-if="versionStatusMessage" class="version-status" :class="updateStatus" role="status">{{ versionStatusMessage }}</p>
          </div>
          <button
            type="button"
            class="version-update-action"
            :class="updateStatus === 'available' ? 'primary-action' : 'secondary-action'"
            data-action="version-update"
            :disabled="updateStatus === 'checking'"
            :aria-label="updateStatus === 'current' ? '再次检查版本' : versionActionLabel"
            @click="handleVersionAction"
          >
            <LoaderCircle v-if="updateStatus === 'checking'" class="spin" :size="16" />
            <Check v-else-if="updateStatus === 'current'" :size="16" />
            <RefreshCw v-else :size="16" />
            {{ versionActionLabel }}
          </button>
        </section>

        <section class="settings-section settings-background" aria-labelledby="background-effect-title">
          <h2 id="background-effect-title">界面主题</h2>
          <div class="background-effect-options" role="group" aria-label="界面主题">
            <button
              type="button"
              class="background-effect-option"
              :class="{ active: backgroundEffect === 'gravity-grid' }"
              data-background-effect="gravity-grid"
              :aria-pressed="backgroundEffect === 'gravity-grid'"
              @click="selectBackgroundEffect('gravity-grid')"
            ><Grid3X3 :size="19" /><strong>暗黑引力</strong><Check v-if="backgroundEffect === 'gravity-grid'" :size="17" /></button>
            <button
              type="button"
              class="background-effect-option"
              :class="{ active: backgroundEffect === 'snowfall' }"
              data-background-effect="snowfall"
              :aria-pressed="backgroundEffect === 'snowfall'"
              @click="selectBackgroundEffect('snowfall')"
            ><Snowflake :size="19" /><strong>雾白飘雪</strong><Check v-if="backgroundEffect === 'snowfall'" :size="17" /></button>
          </div>
        </section>
      </div>

      <section class="settings-section community-section feedback-section settings-community settings-community-feedback">
        <div class="community-copy"><p class="settings-eyebrow">社区交流</p><h2>加入 Pictora 交流群</h2><p>交流使用技巧，反馈问题，获取最新功能信息。</p><dl><div><dt>群名称</dt><dd>小北AI交流群4</dd></div><div><dt>QQ群号</dt><dd>1043879357</dd></div></dl></div>
        <div class="community-feedback-panel">
          <div class="feedback-heading"><h2>留言</h2><p>告诉我们你的建议或遇到的问题。</p></div>
          <form class="feedback-form" @submit.prevent="submitFeedback">
            <label>联系方式<span class="optional-mark">选填</span><input v-model="feedbackContact" data-field="feedback-contact" maxlength="200" placeholder="微信、邮箱或其他联系方式" /></label>
            <label>留言<span class="required-mark">*必填</span><textarea v-model="feedbackMessage" data-field="feedback-message" rows="4" maxlength="2000" placeholder="请输入你的留言" required></textarea></label>
            <div class="feedback-actions"><button type="submit" class="primary-action" :disabled="feedbackSubmitting || !feedbackMessage.trim()">{{ feedbackSubmitting ? '提交中...' : '提交留言' }}</button><p v-if="feedbackStatus" class="feedback-status" role="status">{{ feedbackStatus }}</p></div>
          </form>
        </div>
      </section>

      <section class="settings-section security-section settings-security">
        <div class="account-profile">
          <div class="security-heading"><h2>账号资料</h2></div>
          <form class="profile-form" @submit.prevent="updateProfile">
            <label>用户名<input v-model="profileUsername" data-field="profile-username" autocomplete="username" maxlength="80" required /></label>
            <label>邮箱<input :value="currentEmail" data-field="profile-email" type="email" :placeholder="currentEmail ? '' : '未绑定邮箱'" readonly aria-readonly="true" /></label>
            <div class="profile-actions"><button type="submit" class="primary-action" data-action="save-profile" :disabled="profileSaving || !profileUsername.trim() || profileUsername.trim() === currentUsername">{{ profileSaving ? '保存中...' : '保存用户名' }}</button><p v-if="profileStatus" class="profile-status" role="status">{{ profileStatus }}</p></div>
          </form>
        </div>
        <div class="security-heading password-heading"><h2>修改密码</h2></div>
        <div class="security-grid">
          <form class="password-form" @submit.prevent="changePassword"><label>旧密码<input v-model="oldPassword" data-field="old-password" type="password" /></label><label>新密码<input v-model="newPassword" data-field="new-password" type="password" /></label><label>确认新密码<input v-model="newPasswordConfirmation" data-field="new-password-confirmation" type="password" /></label><p v-if="authError" class="error-message">{{ authError }}</p><button type="submit" class="primary-action" data-action="change-password" @click.prevent="changePassword">修改密码</button></form>
          <div class="logout-panel"><h3>退出登录</h3><p>结束当前账号会话，返回登录页面。</p><button type="button" class="secondary-action logout-action" @click="logout">退出登录</button></div>
        </div>
      </section>
      <ConfirmDialog
        :open="confirmAction === 'api-key'"
        title="删除 API Key 配置"
        :message="`确认删除 API Key 配置“${confirmConfig?.alias}”吗？`"
        :busy="actionBusy"
        @confirm="confirmDeletion"
        @cancel="cancelConfirm"
      />
    </section>
    <section v-else-if="currentView === 'admin'" class="admin-page">
      <header class="admin-page-heading">
        <div><span>Pictora</span><h1>用户管理</h1></div>
        <button type="button" class="secondary-action" :disabled="adminLoading" @click="loadAdminUsers()"><RefreshCw :class="{ spin: adminLoading }" :size="16" />刷新</button>
      </header>

      <div class="admin-metrics" aria-label="用户统计">
        <div><span>已验证用户</span><strong>{{ adminUserTotal }}</strong></div>
        <div><span>管理员</span><strong>{{ adminUserAdminTotal }}</strong></div>
        <div><span>累计任务</span><strong>{{ adminUsageTotal }}</strong></div>
      </div>

      <section class="admin-directory" aria-labelledby="admin-users-title">
        <div class="admin-section-heading">
          <div><h2 id="admin-users-title">用户</h2><span class="admin-timezone">时间均为北京时间</span></div>
          <input v-model="adminSearch" type="search" placeholder="搜索用户名或邮箱" aria-label="搜索用户" @input="scheduleAdminSearch" />
        </div>
        <p v-if="adminError" class="error-message" role="alert">{{ adminError }}</p>
        <div class="admin-table-wrap">
          <table class="admin-table admin-users-table">
            <thead><tr><th>用户</th><th>权限</th><th>密码</th><th>注册时间</th><th>最后登录</th><th>最后活动</th><th>任务</th><th>模型</th></tr></thead>
            <tbody>
              <tr v-for="user in adminUsers" :key="user.id" :class="{ selected: user.id === selectedAdminUserId }" tabindex="0" @click="selectAdminUser(user.id)" @keydown.enter="selectAdminUser(user.id)">
                <td><strong>{{ user.username }}</strong><span>{{ user.email }}</span></td>
                <td><span class="admin-role" :class="{ elevated: user.is_admin }">{{ user.is_admin ? '管理员' : '用户' }}</span></td>
                <td>{{ user.password_status }}</td>
                <td>{{ formatAdminDate(user.created_at) }}</td>
                <td>{{ formatAdminDate(user.last_login_at) }}</td>
                <td>{{ formatAdminDate(user.last_activity_at) }}</td>
                <td>{{ user.usage_count }}</td>
                <td><span class="admin-model-list">{{ user.models_used.join('、') || '-' }}</span></td>
              </tr>
              <tr v-if="!adminLoading && adminUsers.length === 0"><td colspan="8" class="admin-empty">没有匹配的用户</td></tr>
            </tbody>
          </table>
        </div>
        <nav v-if="adminResultTotal > adminPageSize" class="admin-pagination" aria-label="用户列表分页">
          <span>第 {{ adminPage }} / {{ adminPageCount }} 页，共 {{ adminResultTotal }} 位用户</span>
          <div>
            <button type="button" class="secondary-action icon-action" title="上一页" aria-label="上一页" :disabled="adminPage <= 1 || adminLoading" @click="changeAdminPage(adminPage - 1)"><ChevronLeft :size="17" /></button>
            <button type="button" class="secondary-action icon-action" title="下一页" aria-label="下一页" :disabled="adminPage >= adminPageCount || adminLoading" @click="changeAdminPage(adminPage + 1)"><ChevronRight :size="17" /></button>
          </div>
        </nav>
      </section>

      <section v-if="selectedAdminUser" class="admin-user-detail" aria-labelledby="admin-usage-title">
        <div class="admin-detail-heading">
          <div><span>当前用户</span><h2>{{ selectedAdminUser.username }}</h2><p>{{ selectedAdminUser.email }}</p></div>
          <form class="admin-password-reset" @submit.prevent="resetAdminUserPassword">
            <label>重置密码<input v-model="adminResetPassword" type="password" minlength="8" autocomplete="new-password" placeholder="至少 8 位" /></label>
            <button type="submit" class="secondary-action" :disabled="adminResetting"><KeyRound :size="16" />{{ adminResetting ? '重置中' : '重置' }}</button>
            <span v-if="adminResetStatus" role="status">{{ adminResetStatus }}</span>
          </form>
        </div>
        <div class="admin-user-facts">
          <span><small>生成</small><strong>{{ selectedAdminUser.generation_count }}</strong></span>
          <span><small>分析</small><strong>{{ selectedAdminUser.analysis_count }}</strong></span>
          <span><small>累计耗时</small><strong>{{ formatAdminDuration(selectedAdminUser.total_elapsed_ms) }}</strong></span>
          <span><small>最后使用</small><strong>{{ formatAdminDate(selectedAdminUser.last_used_at) }}</strong></span>
        </div>
        <div class="admin-table-wrap">
          <table class="admin-table admin-usage-table">
            <thead><tr><th id="admin-usage-title">时间</th><th>类型</th><th>状态</th><th>服务商</th><th>模型</th><th>清晰度</th><th>比例/尺寸</th><th>分辨率</th><th>图片数</th><th>耗时</th></tr></thead>
            <tbody>
              <tr v-for="record in adminUsage" :key="record.id">
                <td>{{ formatAdminDate(record.created_at) }}</td>
                <td>{{ record.kind === 'generate' ? '生成' : '分析' }}</td>
                <td><span class="admin-status" :class="record.status">{{ record.status === 'completed' ? '完成' : record.status === 'pending' ? '进行中' : '失败' }}</span></td>
                <td>{{ record.provider }}</td><td>{{ record.model }}</td><td>{{ record.detail }}</td>
                <td>{{ record.size || '-' }}</td><td>{{ record.resolution || '-' }}</td><td>{{ record.image_count }}</td><td>{{ formatAdminDuration(record.elapsed_ms) }}</td>
              </tr>
              <tr v-if="adminUsage.length === 0"><td colspan="10" class="admin-empty">暂无使用记录</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </section>
    <SkillsView
      v-else-if="currentView === 'skills'"
      :is-admin="currentIsAdmin"
      :username="currentUsername"
      :current-workflow="currentSkillWorkflow"
      :cover-source="generated[0] ? imageSource(generated[0]) : undefined"
      @apply="applySkillWorkflow"
      @back="navigateToWorkspace"
    />
    <PromptsView
      v-else-if="currentView === 'prompts'"
      :current-prompt="prompt"
      @apply="applySavedPrompt"
      @back="navigateToWorkspace"
    />
    <template v-else>
    <div class="studio-grid">
      <ProjectSidebar
        id="project-sidebar"
        :projects="projects"
        :selected-project-id="selectedProjectId"
        :running-generations="runningGenerations"
        :active-generation-run-id="activeGenerationRunId"
        :loading="!projects.length && !projectError"
        @select-project="selectProject"
        @new-conversation="startNewConversation"
        @create-project="createProject"
        @rename-project="renameProject"
        @delete-project="deleteProject"
        @delete-history="deleteHistory"
        @open-history="openHistory"
        @open-generation="restoreGenerationRun"
        @prefetch-history="prefetchHistory"
      />
      <section
        ref="workspacePanel"
        class="workspace-panel"
        :class="{
          'is-resizing': workspaceResizing,
          'is-composer-collapsed': workspaceComposerCollapsed,
        }"
        :style="{ '--workspace-result-ratio': `${workspaceResultRatio}%` }"
      >
        <div class="result-panel" :class="{ 'has-error': Boolean(error) }">
          <div class="result-heading">
            <div><span class="result-kicker"><Sparkles :size="13" />作品画布</span><h2>{{ activeHistoryId ? "历史结果" : "生成结果" }}</h2></div>
            <div class="result-heading-actions"><button v-if="activeHistoryId && prompt.trim()" type="button" class="secondary-action" data-action="save-history-prompt" @click="openPromptEditor(prompt)"><BookmarkPlus :size="15" />保存提示词</button><span v-if="busy === 'analyze'" class="working">处理中</span></div>
          </div>

          <p v-if="error" class="error-message generation-error result-error" role="alert">{{ error }}</p>

          <div v-if="visibleGenerationCards.length" class="image-grid">
            <article
              v-for="(card, index) in visibleGenerationCards"
              :key="card.key"
              class="image-card"
              :class="{
                'generation-progress-card': card.kind === 'run' && card.run.state === 'running',
                'generation-failure-card': card.kind === 'history-failure' || (card.kind === 'run' && card.run.state !== 'running'),
              }"
            >
              <template v-if="card.kind === 'image'">
                <div class="image-frame">
                  <button v-if="imageSource(card.image)" type="button" class="image-preview-trigger" :aria-label="`全屏查看${cardViewLabel(card) || `生成图片 ${index + 1}`}`" @click="openLightbox(card.image)">
                    <img :src="thumbnailSource(card.image)" :alt="cardViewLabel(card) || `生成图片 ${index + 1}`" decoding="async" @error="handleThumbnailError($event, card.image)" />
                  </button>
                  <div v-else class="missing-image">图片数据不可用</div>
                </div>
                <div class="image-meta">
                  <span>{{ cardViewLabel(card) || `图片 ${index + 1}` }}</span>
                  <div class="image-meta-actions">
                    <strong v-if="card.image.generation_time_ms != null">{{ formatDuration(card.image.generation_time_ms) }}</strong>
                    <button v-if="card.image.history_id != null && card.image.history_image_id != null" type="button" class="image-card-action edit-image-action" :disabled="modifyingImageIds.includes(card.image.history_image_id)" aria-label="修改图片" title="修改图片" @click="modifyGeneratedImage(card.image)">
                      <LoaderCircle v-if="modifyingImageIds.includes(card.image.history_image_id)" class="spin" :size="15" />
                      <Pencil v-else :size="15" />
                    </button>
                    <button v-if="card.image.history_id != null && card.image.history_image_id != null" type="button" class="image-card-action delete-image-action danger-action" :disabled="deletingImageIds.includes(card.image.history_image_id)" aria-label="删除图片" title="删除图片" @click="requestGeneratedImageDeletion(card.image, card.slotPosition)">
                      <LoaderCircle v-if="deletingImageIds.includes(card.image.history_image_id)" class="spin" :size="15" />
                      <Trash2 v-else :size="15" />
                    </button>
                    <a v-if="imageSource(card.image)" class="download" :href="imageSource(card.image)" download="genimage-result.png" aria-label="下载图片" title="下载图片"><Download :size="16" /></a>
                  </div>
                </div>
              </template>
              <template v-else-if="card.kind === 'run'">
                <div class="generation-progress-frame">
                  <div v-if="card.run.state === 'running'" class="generation-progress-running">
                    <div class="empty-shape is-generating" :style="{ '--generation-fill': `${generationFillPercent(card.run.elapsedMs)}%` }"><Sparkles class="empty-shape-icon" :size="24" /><span class="generation-water" aria-hidden="true"><Sparkles class="empty-shape-icon" :size="24" /></span></div>
                    <p v-if="card.run.error" class="generation-progress-error" role="alert">{{ card.run.error }}</p>
                  </div>
                  <div v-else class="generation-failure-state" :class="{ 'is-cancelled': card.run.state === 'cancelled' }"><CircleAlert :size="27" /><strong>{{ card.run.state === "cancelled" ? "生成已取消" : "生成失败" }}</strong><p :title="card.run.error">{{ card.run.error }}</p></div>
                </div>
                <div class="image-meta generation-progress-meta">
                  <span>{{ cardViewLabel(card) ? `${cardViewLabel(card)} · ${card.run.state === "running" ? "正在生成" : card.run.state === "cancelled" ? "已取消" : "生成失败"}` : card.run.state === "running" ? "正在生成" : card.run.state === "cancelled" ? "已取消" : "生成失败" }}</span>
                  <div class="image-meta-actions">
                    <strong>{{ formatDuration(card.run.elapsedMs) }}</strong>
                    <button v-if="card.run.state === 'running' && card.run.conversationId !== null && card.run.batchId !== null" type="button" class="image-card-action cancel-image-action" :disabled="cancellingSlotKeys.includes(`run-${card.runId}-${card.slotPosition}`)" aria-label="取消当前图片" title="取消当前图片" @click="cancelGenerationRunSlot(card.runId, card.slotPosition)"><LoaderCircle v-if="cancellingSlotKeys.includes(`run-${card.runId}-${card.slotPosition}`)" class="spin" :size="15" /><X v-else :size="15" /></button>
                    <button v-if="card.run.state !== 'running'" type="button" class="image-card-action delete-image-action danger-action" aria-label="删除图片" title="删除图片" @click="deleteGenerationRunSlot(card.runId, card.slotPosition)"><Trash2 :size="15" /></button>
                  </div>
                </div>
              </template>
              <template v-else>
                <div class="generation-progress-frame"><div class="generation-failure-state" :class="{ 'is-cancelled': card.group.state === 'cancelled' }"><CircleAlert :size="27" /><strong>{{ card.group.state === "cancelled" ? "生成已取消" : "生成失败" }}</strong><p :title="card.group.message">{{ card.group.message }}</p></div></div>
                <div class="image-meta generation-progress-meta">
                  <span>{{ cardViewLabel(card) ? `${cardViewLabel(card)} · ${card.group.state === "cancelled" ? "已取消" : "生成失败"}` : card.group.state === "cancelled" ? "已取消" : "生成失败" }}</span>
                  <div class="image-meta-actions">
                    <strong>{{ formatDuration(card.group.elapsedMs) }}</strong>
                    <button type="button" class="image-card-action delete-image-action danger-action" :disabled="deletingSlotKeys.includes(generationSlotKey(card.group.historyId, card.group.batchId, card.slotPosition))" aria-label="删除图片" title="删除图片" @click="deleteHistoryFailureSlot(card.group, card.slotPosition)"><LoaderCircle v-if="deletingSlotKeys.includes(generationSlotKey(card.group.historyId, card.group.batchId, card.slotPosition))" class="spin" :size="15" /><Trash2 v-else :size="15" /></button>
                  </div>
                </div>
              </template>
            </article>
          </div>
          <div v-else class="empty-wall">
            <div class="empty-shape">
              <Sparkles class="empty-shape-icon" :size="24" />
            </div>
            <template v-if="!error">
              <h3>等待生成结果</h3>
              <p>配置参数并在下方输入提示词。</p>
            </template>
          </div>
        </div>

        <div
          class="panel-resizer"
          role="separator"
          aria-label="调整作品画布与编辑区高度"
          aria-orientation="horizontal"
          aria-valuemin="25"
          aria-valuemax="75"
          :aria-valuenow="Math.round(workspaceResultRatio)"
          :aria-disabled="workspaceComposerCollapsed"
          :tabindex="workspaceComposerCollapsed ? -1 : 0"
          :title="workspaceComposerCollapsed ? undefined : '拖动调整上下区域，双击恢复默认比例'"
          @pointerdown="startWorkspaceResize"
          @keydown="handleWorkspaceResizeKeydown"
          @dblclick="resetWorkspaceResultRatio"
        >
          <span aria-hidden="true"></span>
          <button
            type="button"
            class="composer-collapse-toggle"
            :aria-label="workspaceComposerCollapsed ? '展开提示词编辑区' : '向下收起提示词编辑区'"
            :title="workspaceComposerCollapsed ? '展开提示词编辑区' : '收起提示词编辑区'"
            @pointerdown.stop
            @dblclick.stop
            @click.stop="toggleWorkspaceComposer"
          >
            <ChevronUp v-if="workspaceComposerCollapsed" :size="17" />
            <ChevronDown v-else :size="17" />
          </button>
        </div>

        <div v-show="!workspaceComposerCollapsed" class="workspace-composer-panel">
        <section class="composer-dock">
          <div class="composer-main">
            <div class="parameter-toolbar" aria-label="模型参数">
                <div class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="apiKey" :aria-expanded="openParameterMenu === 'apiKey'" @click="toggleParameterMenu('apiKey')">API Key <strong>{{ selectedApiKeyLabel }}</strong></button><div v-if="openParameterMenu === 'apiKey'" class="parameter-menu" data-parameter-menu="apiKey"><button v-for="option in apiKeyConfigs" :key="option.id" type="button" class="parameter-option" :class="{ 'is-selected': option.id === activeApiKeyConfigId }" :data-parameter-option="option.alias" @click="selectApiKeyConfig(option)"><span>{{ option.alias }}</span><Check v-if="option.id === activeApiKeyConfigId" :size="15" /></button></div></div>
                <div class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="model" :aria-expanded="openParameterMenu === 'model'" @click="toggleParameterMenu('model')">模型名称 <strong>{{ selectedModelLabel }}</strong></button><div v-if="openParameterMenu === 'model'" class="parameter-menu" data-parameter-menu="model"><button v-for="option in modelOptions" :key="option.id" type="button" class="parameter-option" :class="{ 'is-selected': option.id === model }" :data-parameter-option="option.id" @click="selectModel(option.id)"><span>{{ option.id }}</span><Check v-if="option.id === model" :size="15" /></button><span v-if="loadingConfigModels" class="parameter-option-description">获取模型列表中...</span></div></div>
                <div v-if="selectedCapability?.sizes.length" class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="size" :aria-expanded="openParameterMenu === 'size'" @click="toggleParameterMenu('size')">图片尺寸 <strong>{{ selectedGptSizeLabel }}</strong></button><div v-if="openParameterMenu === 'size'" class="parameter-menu" data-parameter-menu="size"><button v-for="option in gptSizeOptions" :key="option.value" type="button" class="parameter-option" :class="{ 'is-selected': option.value === size }" :data-parameter-option="option.value" @click="selectSize(option.value)"><span><strong>{{ option.label }}</strong><small>{{ option.value }}</small></span><Check v-if="option.value === size" :size="15" /></button></div></div>
                <div v-if="selectedCapability?.aspect_ratios.length" class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="size" :aria-expanded="openParameterMenu === 'size'" @click="toggleParameterMenu('size')">图片比例 <strong>{{ size }}</strong></button><div v-if="openParameterMenu === 'size'" class="parameter-menu" data-parameter-menu="size"><button v-for="option in nativeAspectRatioOptions" :key="option" type="button" class="parameter-option" :class="{ 'is-selected': option === size }" :data-parameter-option="option" @click="selectSize(option)"><span><strong>{{ option }}</strong></span><Check v-if="option === size" :size="15" /></button></div></div>
                <div v-if="selectedCapability?.resolutions.length" class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="resolution" :aria-expanded="openParameterMenu === 'resolution'" @click="toggleParameterMenu('resolution')">分辨率 <strong>{{ resolution }}</strong></button><div v-if="openParameterMenu === 'resolution'" class="parameter-menu" data-parameter-menu="resolution"><button v-for="option in resolutionOptions" :key="option" type="button" class="parameter-option" :class="{ 'is-selected': option === resolution }" :data-parameter-option="option" @click="selectResolution(option)"><span>{{ option }}</span><Check v-if="option === resolution" :size="15" /></button></div></div>
                <div v-if="selectedCapability?.qualities.length" class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="quality" :aria-expanded="openParameterMenu === 'quality'" @click="toggleParameterMenu('quality')">生成质量 <strong>{{ qualityOptions.find((option) => option.value === quality)?.label }}</strong></button><div v-if="openParameterMenu === 'quality'" class="parameter-menu" data-parameter-menu="quality"><button v-for="option in qualityOptions" :key="option.value" type="button" class="parameter-option" :class="{ 'is-selected': option.value === quality }" :data-parameter-option="option.value" @click="selectQuality(option.value)"><span>{{ option.label }}</span><Check v-if="option.value === quality" :size="15" /></button></div></div>
                <div class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="count" :disabled="multiViewEnabled" :aria-expanded="openParameterMenu === 'count'" @click="toggleParameterMenu('count')">{{ multiViewEnabled ? "输出数量" : "生成数量" }} <strong>{{ multiViewEnabled ? selectedMultiViewOptions.length : imageCount }} 张</strong></button><div v-if="openParameterMenu === 'count'" class="parameter-menu" data-parameter-menu="count"><button v-for="option in imageCountOptions" :key="option" type="button" class="parameter-option" :class="{ 'is-selected': option === imageCount }" :data-parameter-option="option" @click="selectImageCount(option)"><span>{{ option }} 张</span><Check v-if="option === imageCount" :size="15" /></button></div></div>
                <div class="multi-view-control" :class="{ 'is-enabled': multiViewEnabled }">
                  <button type="button" class="multi-view-toggle" role="switch" :aria-checked="multiViewEnabled" @click="toggleMultiView">
                    <span><Grid3X3 :size="15" />多视角</span>
                    <span class="switch-track" aria-hidden="true"><span></span></span>
                  </button>
                  <div v-if="multiViewEnabled" class="multi-view-panel">
                    <div v-if="hasPersonReferences && hasObjectReferences" class="multi-view-target" aria-label="多视角主体">
                      <button type="button" :class="{ active: multiViewTarget === 'person' }" :aria-pressed="multiViewTarget === 'person'" @click="multiViewTarget = 'person'">人物</button>
                      <button type="button" :class="{ active: multiViewTarget === 'object' }" :aria-pressed="multiViewTarget === 'object'" @click="multiViewTarget = 'object'">物品</button>
                    </div>
                    <div class="multi-view-presets" aria-label="选择视角">
                      <button v-for="view in MULTI_VIEW_PRESETS" :key="view.key" type="button" :class="{ active: selectedMultiViewKeys.includes(view.key) }" :aria-pressed="selectedMultiViewKeys.includes(view.key)" @click="toggleMultiViewPreset(view.key)">{{ view.label }}</button>
                    </div>
                    <div v-if="customMultiViews.length" class="custom-view-list" aria-label="自定义视角">
                      <span v-for="view in customMultiViews" :key="view.key">{{ view.label }}<button type="button" :aria-label="`移除自定义视角 ${view.label}`" :title="`移除 ${view.label}`" @click="removeCustomMultiView(view.key)"><X :size="12" /></button></span>
                    </div>
                    <div class="custom-view-input">
                      <input v-model="customMultiViewInput" type="text" maxlength="40" placeholder="自定义视角" aria-label="自定义视角" @keydown.enter.prevent="addCustomMultiView" />
                      <button type="button" aria-label="添加自定义视角" title="添加自定义视角" @click="addCustomMultiView"><Plus :size="15" /></button>
                    </div>
                    <p v-if="multiViewInputError || multiViewValidationMessage" class="multi-view-error" role="status">{{ multiViewInputError || multiViewValidationMessage }}</p>
                  </div>
                </div>
            </div>
            <div class="prompt-column">
              <div class="prompt-row"><div class="prompt-row-heading"><span>提示词</span><button type="button" class="text-action" data-action="choose-prompt" @click="openPromptPicker"><BookmarkPlus :size="15" />选择提示词</button></div><label><textarea v-model="prompt" placeholder="描述主体、环境、构图、镜头、光线、材质与风格..."></textarea></label></div>
              <div class="prompt-save-row"><button type="button" class="text-action" data-action="save-current-prompt" :disabled="!prompt.trim()" @click="openPromptEditor(prompt)"><BookmarkPlus :size="15" />保存到提示词管理</button><span v-if="promptSaveStatus" class="prompt-save-status" role="status">{{ promptSaveStatus }}</span></div>
              <div class="composer-actions"><button type="button" class="secondary-action analyze-action" :disabled="!canAnalyze" @click="analyzeImage"><LoaderCircle v-if="busy === 'analyze'" class="spin" :size="17" /><ImagePlus v-else :size="17" />分析图片</button><button type="button" class="primary-action" :disabled="busy === 'analyze' || !canGenerate" @click="handleGenerateClick"><LoaderCircle v-if="generationSubmitting" class="spin" :size="17" /><Sparkles v-else :size="17" />{{ multiViewEnabled ? `生成 ${selectedMultiViewOptions.length} 个视角` : "生成图片" }}</button></div>
            </div>
            <div class="reference-row" :class="{ 'has-references': referencePreviews.length }" aria-label="参考图片分类">
              <section v-for="category in REFERENCE_CATEGORIES" :key="category.id" class="reference-module">
                <div
                  class="upload-zone"
                  :class="{ 'is-dragging': referenceDragActiveCategory === category.id, 'has-previews': referencesForCategory(category.id).length }"
                  @dragenter.prevent="handleReferenceDragEnter(category.id)"
                  @dragleave.prevent="handleReferenceDragLeave(category.id)"
                  @dragover.prevent="handleReferenceDragOver"
                  @drop.prevent="handleReferenceDrop(category.id, $event)"
                >
                  <input :id="category.id === 'person' ? 'image-input' : 'image-input-' + category.id" type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple :disabled="referencePreviews.length >= maxReferenceImages" @change="handleReferenceInput(category.id, $event)" />
                  <label :for="category.id === 'person' ? 'image-input' : 'image-input-' + category.id" :aria-label="`${referencesForCategory(category.id).length ? '继续添加' : '添加'}${category.label}参考图`">
                    <span class="upload-zone-icon"><Upload :size="20" /></span>
                    <span class="upload-zone-copy"><strong>{{ referencesForCategory(category.id).length ? `继续添加${category.label}参考图` : `添加${category.label}参考图` }}</strong><small>{{ referencePreviews.length >= maxReferenceImages ? "已达到总数量上限" : "点击选择或拖动图片到这里" }}</small></span>
                  </label>
                  <div v-if="referencesForCategory(category.id).length" class="reference-preview-list" role="list" :aria-label="`${category.label}参考图片`">
                    <article v-for="reference in referencesForCategory(category.id)" :key="reference.key" class="reference-thumbnail" role="listitem">
                      <button type="button" class="reference-preview-trigger" :aria-label="`放大查看${category.label}参考图片`" @click="openReferenceLightbox(reference)">
                        <img :src="reference.url" :alt="`${category.label}参考图片`" />
                      </button>
                      <span :title="reference.name">{{ reference.name }}</span>
                      <button type="button" class="reference-remove" :aria-label="`移除参考图片 ${referenceOrdinal(reference.key)}`" title="移除参考图片" @click="removeReference(reference.key)"><X :size="14" /></button>
                    </article>
                  </div>
                </div>
              </section>
            </div>
          </div>
        </section>
        </div>
      </section>
    </div>

    <!--
      <div v-if="historyOpen" class="drawer-layer" @click.self="closeHistory">
        <aside class="history-drawer" role="dialog" aria-modal="true" aria-label="历史记录">
          <div class="history-drawer-header">
            <div><span>历史记录</span><strong>{{ history.length }} 条</strong></div>
            <button type="button" class="history-drawer-close" aria-label="关闭历史记录" title="关闭" @click="closeHistory"><X :size="20" /></button>
          </div>
          <div v-if="history.length" class="history-list">
            <button v-for="item in history" :key="item.id" type="button" class="history-item" :class="{ active: activeHistoryId === item.id, failed: item.status === 'failed' }" :data-history-id="item.id" @click="openHistory(item.id)">
              <span>{{ item.prompt }}</span>
              <small>{{ item.model }} · {{ formatHistoryTime(item.created_at) }}</small>
            </button>
          </div>
          <p v-else-if="!historyError" class="history-empty">暂无历史记录</p>
          <p v-if="historyError" class="history-error">{{ historyError }}</p>
        </aside>
      </div>
    -->

    <div v-if="lightboxUrl" class="image-lightbox" role="dialog" aria-modal="true" aria-label="图片全屏预览" @click.self="closeLightbox">
      <button type="button" class="lightbox-close" aria-label="关闭全屏预览" title="关闭" @click="closeLightbox"><X :size="22" /></button>
      <img :src="lightboxUrl" alt="图片全屏预览" />
    </div>
    <PromptPickerPopover :open="promptPickerOpen" :current-prompt="prompt" @select="applyPromptSelection" @close="closePromptPicker" @manage="managePromptsFromPicker" />
    <ConfirmDialog :open="promptPickerConfirmOpen" title="覆盖当前提示词" :message="`当前提示词已有内容，确认用“${pendingPromptSelection?.name ?? ''}”替换吗？`" confirm-label="覆盖" @confirm="confirmPromptSelection" @cancel="cancelPromptSelection" />
    <PromptEditorDialog :open="promptEditorOpen" :initial="promptEditorInitial" :category-suggestions="promptCategorySuggestions" :title="promptEditorEntryId === null ? '保存提示词' : '编辑提示词'" @submit="savePromptEntry" @cancel="promptEditorOpen = false" />
    <ProjectDialog
      :open="projectDialogMode !== null"
      :title="projectDialogMode === 'rename' ? '重命名项目' : '新建项目'"
      :initial-name="projectDialogProject?.name"
      @submit="submitProjectDialog"
      @cancel="cancelProjectDialog"
    />
    <ConfirmDialog
      :open="confirmAction !== null"
      :title="confirmAction === 'project' ? '删除项目' : confirmAction === 'history' ? '删除历史记录' : confirmAction === 'image' ? '删除图片' : '删除 API Key 配置'"
      :message="confirmAction === 'project' ? `确认删除项目“${confirmProject?.name}”及其 ${confirmProject?.history_count ?? 0} 条历史记录吗？` : confirmAction === 'history' ? `确认删除选中的 ${confirmHistoryIds.length} 条历史记录吗？` : confirmAction === 'image' ? '确认删除这张图片吗？删除后无法恢复。' : `确认删除 API Key 配置“${confirmConfig?.alias}”吗？`"
      :busy="actionBusy"
      @confirm="confirmDeletion"
      @cancel="cancelConfirm"
    />
    </template>
    </template>
  </main>
</template>
