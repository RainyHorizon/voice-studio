import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AudioLines,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  FlaskConical,
  Clock3,
  Copy,
  Code2,
  Download,
  Eye,
  EyeOff,
  FileAudio,
  FileText,
  FolderOpen,
  Gauge,
  HardDrive,
  KeyRound,
  Library,
  ListChecks,
  Mic2,
  Pause,
  Pencil,
  Plus,
  Play,
  Radio,
  RefreshCw,
  RotateCcw,
  Save,
  Settings2,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  Volume2,
  WandSparkles,
  X,
} from "lucide-react";

type Voice = {
  id: string;
  provider: string;
  model_id: string;
  display_name: string;
  public_name: string;
  voice_type: string;
  status: string;
  languages: string[];
  preview_url?: string | null;
  design_prompt?: string;
};
type Model = {
  provider: string;
  model_id: string;
  gateway_id: string;
  display_name: string;
  quality: string;
  latency: string;
  supports_clone: boolean;
  mode: "demo" | "provider";
  operations: string[];
  design_prompt_max?: number | null;
  design_preview_min?: number | null;
  design_preview_max?: number | null;
};
type CloneConfig = {
  provider: string;
  model_id: string;
  display_name: string;
  public_name: string;
};
type DesignConfig = {
  provider: string;
  model_id: string;
  prompt: string;
  preview_text: string;
  display_name: string;
  public_name: string;
};
type ImportVoiceConfig = CloneConfig & {
  provider_voice_id: string;
  languages: string[];
};
type CloudVoice = {
  provider?: string;
  provider_voice_id: string;
  model_id: string;
  display_name: string;
  language: string;
  created_at: string;
  compatible: boolean;
  compatibility_message: string;
  imported: boolean;
};
type Job = {
  id: string;
  model: string;
  voice: string;
  input_chars: number;
  status: string;
  duration_ms: number;
  created_at: string;
  source: string;
  input_text?: string;
  created_date?: string;
  audio_available?: boolean;
  audio_url?: string | null;
  text_url?: string | null;
  audio_cleaned_at?: string | null;
  audio_cleanup_reason?: string | null;
};
type StoragePolicy = {
  automatic_enabled: boolean;
  retention_days: number;
  capacity_limit_bytes: number;
  interval: "daily" | "weekly";
  cleanup_scope: "audio_only" | "jobs";
  updated_at: string;
};
type StorageUsage = {
  job_count: number;
  audio_count: number;
  audio_bytes: number;
  directory_file_count: number;
  directory_bytes: number;
  unmanaged_bytes: number;
  missing_audio_count: number;
  oldest_audio_at?: string | null;
  capacity_ratio: number;
};
type CleanupRun = {
  id: string;
  trigger: "manual" | "automatic";
  status: string;
  files_removed: number;
  jobs_removed: number;
  jobs_preserved: number;
  bytes_freed: number;
  completed_at: string;
  message: string;
};
type StorageStatus = {
  policy: StoragePolicy;
  usage: StorageUsage;
  next_cleanup_at?: string | null;
  cleanup_history: CleanupRun[];
  storage_path: string;
};
type CleanupPreview = {
  file_count: number;
  job_count: number;
  jobs_preserved: number;
  bytes_before: number;
  bytes_to_free: number;
  bytes_after: number;
  retention_cutoff: string;
  cleanup_scope: "audio_only" | "jobs";
};
type Gateway = {
  enabled: boolean;
  base_url: string;
  key: string;
  mode: string;
  note: string;
  key_hint?: string;
  key_source?: string;
  managed?: boolean;
};
type LatencyStats = { p50: number | null; p95: number | null; samples: number };
type GatewayStatsBucket = {
  name: string;
  requests: number;
  completed: number;
  failed: number;
  cancelled: number;
  success_rate: number;
  first_chunk_latency: LatencyStats;
  total_latency: LatencyStats;
};
type GatewayStats = {
  window: string;
  provider: string | null;
  sample_count: number;
  total_requests: number;
  completed_requests: number;
  failed_requests: number;
  cancelled_requests: number;
  success_rate: number;
  first_chunk_latency: LatencyStats;
  total_latency: LatencyStats;
  by_provider: GatewayStatsBucket[];
  by_model: GatewayStatsBucket[];
  errors: Array<{ code: string; count: number; last_seen_at: string }>;
};
type ProviderAccount = {
  id: string;
  provider: string;
  display_name: string;
  account_ref?: string;
  region?: string;
  endpoint?: string;
  status: string;
  secret_hint: string;
  verification_scope: string;
  verification_message?: string;
  last_verified_at?: string;
  project_name?: string;
  openapi_access_key_hint?: string;
  has_openapi_secret?: boolean;
};
type ProviderSpec = {
  display_name: string;
  secret_label: string;
  default_endpoint: string;
  endpoint_note: string;
  verification: string;
};
type DiagnosticCheck = {
  id: string;
  label: string;
  status: "ok" | "warning" | "error";
  version: string;
  detail: string;
};
type SystemDiagnostics = {
  status: "ok" | "warning" | "error";
  platform: string;
  base_url: string;
  port: number;
  checks: DiagnosticCheck[];
  required_failures: number;
  demo: { model: string; voice: string; available: boolean };
};
const providerMeta: Record<
  string,
  { label: string; mark: string; tone: string }
> = {
  demo: { label: "离线测试", mark: "D", tone: "gray" },
  dashscope: { label: "通义千问", mark: "Q", tone: "gold" },
  volcengine: { label: "火山引擎", mark: "V", tone: "red" },
  minimax: { label: "MiniMax", mark: "M", tone: "mint" },
  mimo: { label: "小米 MiMo", mark: "米", tone: "blue" },
};
const credentialProviderIds = ["dashscope", "volcengine", "minimax", "mimo"];
const sample =
  "夜色落在城市边缘，远处的灯一盏一盏亮起来。把这段文字交给不同的声音，听见同一句话里的不同质感。";
const voiceMatchesModel = (voice?: Voice, model?: Model) =>
  Boolean(
    voice &&
      model &&
      voice.provider === model.provider &&
      (model.mode === "demo" ||
        model.provider === "minimax" ||
        voice.model_id === model.model_id),
  );
async function responseError(response: Response) {
  const text = await response.text();
  try {
    const body = JSON.parse(text);
    return body.error?.message || body.detail?.message || body.detail || text;
  } catch {
    return text || "请求失败 " + response.status;
  }
}
async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(await responseError(response));
  return response.json();
}

export default function App() {
  const [active, setActive] = useState("synthesize");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() =>
    window.localStorage.getItem("voice-studio.sidebar-collapsed") === "true",
  );
  const [voices, setVoices] = useState<Voice[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [text, setText] = useState(sample);
  const [model, setModel] = useState("");
  const [voice, setVoice] = useState("");
  const [speed, setSpeed] = useState(1);
  const [format, setFormat] = useState("wav");
  const [instructions, setInstructions] = useState("");
  const [audioUrl, setAudioUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [gateway, setGateway] = useState<Gateway | null>(null);
  const selectedModel = useMemo(
    () => models.find((item) => item.gateway_id === model),
    [models, model],
  );
  const selectedVoice = useMemo(
    () => voices.find((item) => item.public_name === voice),
    [voices, voice],
  );
  useEffect(() => {
    window.localStorage.setItem(
      "voice-studio.sidebar-collapsed",
      String(sidebarCollapsed),
    );
  }, [sidebarCollapsed]);
  useEffect(() => {
    Promise.all([
      api<Voice[]>("/api/voices"),
      api<Model[]>("/api/models"),
      api<Job[]>("/api/jobs?limit=500"),
      api<Gateway>("/api/gateway"),
    ])
      .then(([v, m, j, g]) => {
        const realVoices = v.filter((item) => item.provider !== "demo");
        const realModels = m.filter((item) => item.provider !== "demo");
        setVoices(realVoices);
        setModels(realModels);
        setModel((current) =>
          realModels.some((item) => item.gateway_id === current)
            ? current
            : realModels.find((item) => item.operations.includes("synthesis"))?.gateway_id || "",
        );
        setVoice((current) =>
          realVoices.some((item) => item.public_name === current) ? current : "",
        );
        setJobs(j);
        setGateway(g);
      })
      .catch(() => setNotice("后端尚未启动，请运行 start.ps1"));
  }, []);
  useEffect(() => {
    const firstCompatible = voices.find((item) =>
      voiceMatchesModel(item, selectedModel),
    );
    if (firstCompatible && !voiceMatchesModel(selectedVoice, selectedModel))
      setVoice(firstCompatible.public_name);
  }, [selectedModel, selectedVoice, voices]);
  const refreshJobs = () =>
    api<Job[]>("/api/jobs?limit=500")
      .then(setJobs)
      .catch(() => undefined);
  const synthesize = async () => {
    if (!text.trim()) return setNotice("请先输入要合成的文本");
    setBusy(true);
    setNotice(
      selectedModel?.mode === "provider"
        ? "正在调用厂商接口生成音频..."
        : "正在生成演示音频...",
    );
    try {
      const response = await fetch("/v1/audio/speech", {
        method: "POST",
        headers: {
          Authorization: "Bearer " + (gateway?.key || "vs_demo_local_key"),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model,
          voice,
          input: text,
          response_format: format,
          speed,
          instructions:
            selectedModel?.model_id === "qwen3-tts-instruct-flash" ||
            selectedModel?.model_id === "seed-tts-2.0"
              ? instructions || undefined
              : undefined,
        }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const blob = await response.blob();
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      setAudioUrl(URL.createObjectURL(blob));
      setNotice("已生成，可试听或下载");
      await refreshJobs();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "生成失败");
    } finally {
      setBusy(false);
    }
  };
  const importVoice = async (config: ImportVoiceConfig) => {
    const created = await api<{ voice: Voice; message: string }>(
      "/api/voices/import",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      },
    );
    setVoices((current) => [created.voice, ...current]);
    setNotice(created.message);
  };
  const importVoices = async (configs: ImportVoiceConfig[]) => {
    const created = await api<{ voices: Voice[]; message: string }>(
      "/api/voices/import/batch",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voices: configs }),
      },
    );
    setVoices((current) => [...created.voices, ...current]);
    setNotice(created.message);
  };
  const removeVoice = async (item: Voice) => {
    if (
      !window.confirm(
        `从 Voice Studio 移除“${item.display_name}”？\n\n这不会删除厂商控制台里的远端音色；本地参考音频（如有）也会一并删除。`,
      )
    )
      return;
    try {
      const result = await api<{ message: string }>("/api/voices/" + item.id, {
        method: "DELETE",
      });
      setVoices((current) =>
        current.filter((voiceItem) => voiceItem.id !== item.id),
      );
      if (voice === item.public_name) setVoice("");
      setNotice(result.message);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "删除失败");
    }
  };
  const renameVoice = async (item: Voice, displayName: string) => {
    const result = await api<{ voice: Voice; message: string }>("/api/voices/" + item.id, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: displayName }),
    });
    setVoices((current) => current.map((voiceItem) => voiceItem.id === item.id ? result.voice : voiceItem));
    setNotice(result.message);
  };
  const cloneVoice = async (config: CloneConfig, file: File) => {
    if (!file) return setNotice("请选择一段参考音频");
    const query = new URLSearchParams({
      provider_name: config.provider,
      model_id: config.model_id,
      display_name: config.display_name,
      public_name: config.public_name,
    });
    const form = new FormData();
    form.append("audio", file);
    try {
      const created = await api<{ voice: Voice; message: string }>(
        "/api/voices/clone?" + query.toString(),
        { method: "POST", body: form },
      );
      setVoices((current) => [created.voice, ...current]);
      setModel(created.voice.provider + "/" + created.voice.model_id);
      setVoice(created.voice.public_name);
      setNotice(created.message);
      setActive("synthesize");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "克隆失败");
    }
  };
  const designVoice = async (config: DesignConfig) => {
    const created = await api<{ voice: Voice; message: string }>("/api/voices/design", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
    setVoices((current) => [created.voice, ...current]);
    const compatibleModel = models.find(
      (item) =>
        item.provider === created.voice.provider &&
        item.operations.includes("synthesis") &&
        (item.provider === "minimax" || item.model_id === created.voice.model_id),
    );
    if (compatibleModel) setModel(compatibleModel.gateway_id);
    setVoice(created.voice.public_name);
    setNotice(created.message);
    return created.voice;
  };
  const useVoice = (item: Voice) => {
    const compatibleModel = models.find(
      (modelItem) =>
        modelItem.operations.includes("synthesis") &&
        modelItem.provider === item.provider &&
        (modelItem.mode === "demo" ||
          modelItem.provider === "minimax" ||
          modelItem.model_id === item.model_id),
    );
    if (!compatibleModel) {
      setNotice(`没有找到与“${item.display_name}”兼容的语音合成模型`);
      return;
    }
    setModel(compatibleModel.gateway_id);
    setVoice(item.public_name);
    setNotice(`已选择音色“${item.display_name}”`);
    setActive("synthesize");
  };
  const nav = [
    { id: "synthesize", label: "语音合成", icon: AudioLines },
    { id: "voices", label: "音色库", icon: Library },
    { id: "clone", label: "语音克隆", icon: Mic2 },
    { id: "design", label: "语音设计", icon: WandSparkles },
    { id: "gateway", label: "API 网关", icon: Code2 },
    { id: "history", label: "任务历史", icon: Clock3 },
    { id: "settings", label: "设置", icon: Settings2 },
  ];
  return (
    <div className={sidebarCollapsed ? "app-shell sidebar-collapsed" : "app-shell"}>
      <aside className="sidebar" aria-label="主导航">
        <div className="brand">
          <div className="brand-orbit">
            <AudioLines size={18} />
          </div>
          <div>
            <strong>VOICE / STUDIO</strong>
          </div>
          <button
            className="sidebar-toggle"
            type="button"
            onClick={() => setSidebarCollapsed((value) => !value)}
            title={sidebarCollapsed ? "展开侧边栏" : "折叠侧边栏"}
            aria-label={sidebarCollapsed ? "展开侧边栏" : "折叠侧边栏"}
          >
            {sidebarCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>
        <nav>
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={active === item.id ? "nav-item active" : "nav-item"}
                onClick={() => setActive(item.id)}
                key={item.id}
                title={sidebarCollapsed ? item.label : undefined}
                aria-label={item.label}
              >
                <Icon size={17} />
                <span>{item.label}</span>
                {active === item.id && (
                  <ChevronRight size={15} className="nav-arrow" />
                )}
              </button>
            );
          })}
        </nav>
      </aside>
      <main className="main-area">
        <header className="topbar visually-hidden">
          <h1>{titleFor(active)}</h1>
        </header>
        {notice && (
          <div className="notice">
            <Activity size={15} />
            {notice}
            <button onClick={() => setNotice("")}>
              <X size={14} />
            </button>
          </div>
        )}
        {active === "synthesize" && (
          <Synthesis
            text={text}
            setText={setText}
            model={model}
            setModel={setModel}
            models={models}
            selectedModel={selectedModel}
            voice={voice}
            setVoice={setVoice}
            voices={voices}
            speed={speed}
            setSpeed={setSpeed}
            format={format}
            setFormat={setFormat}
            instructions={instructions}
            setInstructions={setInstructions}
            audioUrl={audioUrl}
            selectedVoice={selectedVoice}
            busy={busy}
            synthesize={synthesize}
            setActive={setActive}
          />
        )}
        {active === "voices" && (
          <VoiceLibrary
            voices={voices}
            models={models}
            onClone={() => setActive("clone")}
            onImport={importVoice}
            onBatchImport={importVoices}
            onRemove={removeVoice}
            onRename={renameVoice}
            onUse={useVoice}
          />
        )}
        {active === "clone" && (
          <ClonePanel models={models} onClone={cloneVoice} onNotice={setNotice} />
        )}
        {active === "design" && (
          <VoiceDesignPanel models={models} onDesign={designVoice} />
        )}
        {active === "gateway" && (
          <GatewayPanel gateway={gateway} models={models} voices={voices} />
        )}
        {active === "history" && <History jobs={jobs} voices={voices} onRefresh={refreshJobs} />}
        {active === "settings" && <Settings models={models} onJobsChanged={refreshJobs} />}
      </main>
    </div>
  );
}

function titleFor(active: string) {
  return (
    {
      synthesize: "语音合成",
      voices: "音色库",
      clone: "语音克隆",
      design: "语音设计",
      gateway: "OpenAI 兼容网关",
      history: "任务历史",
      settings: "设置",
    } as Record<string, string>
  )[active];
}

function WorkspaceHero({
  title,
  accent,
  description,
  className = "",
}: {
  title: string;
  accent: string;
  description?: string;
  className?: string;
}) {
  return (
    <div className={`workspace-hero${className ? ` ${className}` : ""}`}>
      <h2>
        {title}
        <br />
        <em>{accent}</em>
      </h2>
      {description && <p>{description}</p>}
    </div>
  );
}

type ProviderSelectorOption = {
  id: string;
  label: string;
  mark: string;
  tone: string;
  detail: string;
  indicator?: "active" | "saved" | "idle";
};

function ProviderSelector({
  options,
  value,
  onChange,
  label,
  className = "",
}: {
  options: ProviderSelectorOption[];
  value: string;
  onChange: (value: string) => void;
  label: string;
  className?: string;
}) {
  return (
    <div className={`provider-selector${className ? ` ${className}` : ""}`} role="tablist" aria-label={label}>
      {options.map((option) => (
        <button
          className={value === option.id ? "provider-choice selected" : "provider-choice"}
          type="button"
          role="tab"
          aria-selected={value === option.id}
          onClick={() => onChange(option.id)}
          key={option.id}
        >
          <span className={`provider-mark ${option.tone}`}>{option.mark}</span>
          <span className="provider-choice-copy">
            <strong>{option.label}</strong>
            <small>{option.detail}</small>
          </span>
          {option.indicator && (
            <span className={`provider-choice-indicator ${option.indicator}`} aria-hidden="true" />
          )}
        </button>
      ))}
    </div>
  );
}

function Synthesis(props: {
  text: string;
  setText: (value: string) => void;
  model: string;
  setModel: (value: string) => void;
  models: Model[];
  selectedModel?: Model;
  voice: string;
  setVoice: (value: string) => void;
  voices: Voice[];
  speed: number;
  setSpeed: (value: number) => void;
  format: string;
  setFormat: (value: string) => void;
  instructions: string;
  setInstructions: (value: string) => void;
  audioUrl: string;
  selectedVoice?: Voice;
  busy: boolean;
  synthesize: () => void;
  setActive: (value: string) => void;
}) {
  const p = props;
  const synthesisModels = p.models.filter((item) =>
    item.operations.includes("synthesis"),
  );
  const selectedProvider =
    p.selectedModel?.provider || synthesisModels[0]?.provider || "";
  const providerModels = synthesisModels.filter(
    (item) => item.provider === selectedProvider,
  );
  const compatibleVoices = p.voices.filter((item) =>
    voiceMatchesModel(item, p.selectedModel),
  );
  const selectedVoiceValue = compatibleVoices.some(
    (item) => item.public_name === p.voice,
  )
    ? p.voice
    : "";
  const chooseProvider = (provider: string) => {
    const first = synthesisModels.find((item) => item.provider === provider);
    if (first) p.setModel(first.gateway_id);
  };
  const speedPosition = p.speed <= 1
    ? ((p.speed - 0.5) / 0.5) * 50
    : 50 + ((p.speed - 1) / 1) * 50;
  const changeSpeed = (position: number) => {
    const speed = position <= 50
      ? 0.5 + (position / 50) * 0.5
      : 1 + ((position - 50) / 50);
    p.setSpeed(Math.round(speed * 10) / 10);
  };

  return (
    <section className="synthesis-workspace">
      <WorkspaceHero
        title="把文字变成"
        accent="可听见的质感。"
        description="输入一段文字，选择合适的厂商、模型与音色，生成自然流畅的语音。"
      />
      <div className="synthesis-layout">
        <div className="editor-column">
        <div className="section-heading">
          <div>
            <h2>输入一段文字</h2>
          </div>
          <span className="char-count">
            {p.text.length.toLocaleString()} / 10,000
          </span>
        </div>
        <div className="script-editor">
          <textarea
            value={p.text}
            onChange={(e) => p.setText(e.target.value)}
            spellCheck={false}
          />
          <div className="editor-footer">
            <span>支持中文、英文与混合文本</span>
            <button className="ghost-button" onClick={() => p.setText(sample)}>
              填入示例
            </button>
          </div>
        </div>
        <div className="mini-stats">
          <div>
            <span>预估时长</span>
            <strong>{Math.max(1, Math.round(p.text.length * 0.05))}s</strong>
          </div>
          <div>
            <span>调用方式</span>
            <strong>厂商 API</strong>
          </div>
          <div>
            <span>输出</span>
            <strong>{p.format.toUpperCase()}</strong>
          </div>
        </div>
      </div>
      <section className="synthesis-settings" aria-labelledby="synthesis-settings-title">
        <h3 id="synthesis-settings-title"><Settings2 size={18} />设置</h3>
        <div className="synthesis-settings-grid">
          <label>服务来源<select value={selectedProvider} onChange={(event) => chooseProvider(event.target.value)}>
            {credentialProviderIds.filter((id) => synthesisModels.some((item) => item.provider === id)).map((id) => <option value={id} key={id}>{providerMeta[id].label}</option>)}
          </select></label>
          <div className="synthesis-model-field">
            <label>模型<select value={p.model} onChange={(event) => p.setModel(event.target.value)}>
              {providerModels.map((item) => <option value={item.gateway_id} key={item.gateway_id}>{item.display_name}</option>)}
            </select></label>
            {p.selectedModel && <div className="model-meta"><span className={`provider-mark ${providerMeta[p.selectedModel.provider]?.tone}`}>{providerMeta[p.selectedModel.provider]?.mark}</span><div><strong>{p.selectedModel.quality}质感</strong><small>{p.selectedModel.latency}响应 · 厂商接口</small></div></div>}
          </div>
          <div className="synthesis-voice-field">
            <label>音色<select value={selectedVoiceValue} onChange={(event) => p.setVoice(event.target.value)} disabled={!compatibleVoices.length}>
              {!compatibleVoices.length && <option value="">请先创建或导入兼容音色</option>}
              {compatibleVoices.map((item) => <option value={item.public_name} key={item.id}>{item.display_name} · {item.public_name}</option>)}
            </select></label>
            <button className="inline-action" type="button" onClick={() => p.setActive("clone")}><Plus size={15} />创建或克隆音色</button>
          </div>
          {(p.selectedModel?.model_id === "qwen3-tts-instruct-flash" || p.selectedModel?.model_id === "seed-tts-2.0") && (
            <label className="synthesis-instruction-field">表达指令<input value={p.instructions} onChange={(event) => p.setInstructions(event.target.value)} placeholder="例如：温暖、克制，结尾轻微上扬" /></label>
          )}
        </div>
        <div className="synthesis-tuning-grid">
          <div className="synthesis-speed-setting">
            <div className="range-label"><label>语速</label><output>{p.speed.toFixed(1)}×</output></div>
            <input type="range" min="0" max="100" step="1" value={speedPosition} aria-valuetext={`${p.speed.toFixed(1)} 倍`} onChange={(event) => changeSpeed(Number(event.target.value))} />
            <div className="range-scale"><span>慢</span><span>自然</span><span>快</span></div>
          </div>
          <div className="synthesis-format-setting">
            <label>输出格式</label>
            <div className="segmented">{["wav", "mp3"].map((item) => <button className={p.format === item ? "selected" : ""} type="button" onClick={() => p.setFormat(item)} key={item}>{item.toUpperCase()}</button>)}</div>
          </div>
        </div>
        <div className="control-note"><Gauge size={16} /><span>当前模型会调用已保存的厂商凭据，结果来自对应厂商的语音服务。</span></div>
      </section>
      <div className="generate-row">
        <button className="primary-button" onClick={p.synthesize} disabled={p.busy || !selectedVoiceValue}><Sparkles size={17} />{p.busy ? "生成中..." : "生成语音"}</button>
      </div>
      {p.audioUrl && (
        <div className="player latest-player">
          <div className="player-icon"><Volume2 size={20} /></div>
          <div className="player-main"><div className="player-title"><strong>刚刚生成</strong><span>{p.selectedVoice?.display_name || p.voice} · {p.format.toUpperCase()}</span></div><p className="player-text">{p.text}</p><audio controls src={p.audioUrl} /></div>
          <a className="download-button" href={p.audioUrl} download={"voice-studio." + p.format} title="下载"><Download size={17} /></a>
        </div>
      )}
      </div>
    </section>
  );
}

function HistoryAudioButton({ src, label, compact = false }: { src?: string | null; label: string; compact?: boolean }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const toggle = async () => {
    const audio = audioRef.current;
    if (!audio || !src) return;
    if (audio.paused) {
      await audio.play();
      setPlaying(true);
    } else {
      audio.pause();
      setPlaying(false);
    }
  };
  return (
    <>
      <button className={`history-play${compact ? " compact" : ""}`} onClick={() => void toggle()} disabled={!src} title={src ? label : "声音文件不可用"} aria-label={src ? label : "声音文件不可用"}>
        {playing ? <Pause size={compact ? 15 : 18} fill="currentColor" /> : <Play size={compact ? 15 : 18} fill="currentColor" />}
      </button>
      {src && <audio ref={audioRef} src={src} preload="none" onEnded={() => setPlaying(false)} />}
    </>
  );
}

function VoiceLibrary({
  voices,
  models,
  onClone,
  onImport,
  onBatchImport,
  onRemove,
  onRename,
  onUse,
}: {
  voices: Voice[];
  models: Model[];
  onClone: () => void;
  onImport: (config: ImportVoiceConfig) => Promise<void>;
  onBatchImport: (configs: ImportVoiceConfig[]) => Promise<void>;
  onRemove: (voice: Voice) => Promise<void>;
  onRename: (voice: Voice, displayName: string) => Promise<void>;
  onUse: (voice: Voice) => void;
}) {
  const [provider, setProvider] = useState("all");
  const [scope, setScope] = useState<"all" | "mine">("all");
  const [showImport, setShowImport] = useState(false);
  const [renameTarget, setRenameTarget] = useState<Voice | null>(null);
  const scoped = scope === "mine"
    ? voices.filter((item) => ["cloned", "design", "imported"].includes(item.voice_type))
    : voices;
  const filtered = provider === "all"
    ? scoped
    : scoped.filter((item) => item.provider === provider);
  const counts = Object.fromEntries(
    credentialProviderIds.map((id) => [
      id,
      scoped.filter((item) => item.provider === id).length,
    ]),
  );
  return (
    <section className="page-section voice-library">
      <div className="page-toolbar">
        <div>
          <WorkspaceHero
            title="让每一个声音"
            accent="都有自己的位置。"
            description="浏览预置、克隆、导入和设计音色，并按来源快速筛选。"
          />
        </div>
        <div className="toolbar-actions">
          <button
            className="secondary-button"
            onClick={() => setShowImport(true)}
          >
            <Plus size={16} />
            导入 Voice ID
          </button>
          <button className="primary-button compact" onClick={onClone}>
            <Mic2 size={16} />
            开始克隆
          </button>
        </div>
      </div>
      <div className="voice-scope-tabs" role="tablist" aria-label="音色范围">
        <button className={scope === "all" ? "selected" : ""} onClick={() => setScope("all")}>全部音色</button>
        <button className={scope === "mine" ? "selected" : ""} onClick={() => setScope("mine")}>我的音色</button>
      </div>
      <ProviderSelector
        className="voice-provider-selector"
        label="按厂商筛选音色"
        value={provider}
        onChange={setProvider}
        options={[
          { id: "all", label: "全部厂商", mark: "全", tone: "gray", detail: `${scoped.length} 个音色` },
          ...credentialProviderIds.map((id) => ({
            id,
            label: providerMeta[id].label,
            mark: providerMeta[id].mark,
            tone: providerMeta[id].tone,
            detail: `${counts[id] || 0} 个音色`,
          })),
        ]}
      />
      <div className="voice-table">
        <div className="table-head">
          <span>音色</span>
          <span>来源 / 模型</span>
          <span>类型</span>
          <span>语言</span>
          <span />
        </div>
        {filtered.length ? (
          filtered.map((item) => (
            <div className="voice-row" key={item.id}>
              <div className="voice-name">
                <div className="voice-wave">
                  <span />
                  <span />
                  <span />
                  <span />
                  <span />
                </div>
                <div>
                  <strong>{item.display_name}</strong>
                </div>
              </div>
              <div>
                <strong>
                  {providerMeta[item.provider]?.label || item.provider}
                </strong>
                <small>{item.model_id}</small>
              </div>
              <span className="type-text">
                {item.voice_type === "cloned"
                  ? "克隆"
                  : item.voice_type === "imported"
                    ? "导入"
                    : item.voice_type === "design"
                      ? "设计"
                    : "预置"}
              </span>
              <span>{item.languages.join(" · ")}</span>
              <div className="voice-actions">
                <button className="voice-use-button" onClick={() => onUse(item)}>使用</button>
                {item.voice_type !== "preset" ? <button
                  className="icon-button rename-voice"
                  title="重命名"
                  aria-label={`重命名 ${item.display_name}`}
                  onClick={() => setRenameTarget(item)}
                >
                  <Pencil size={16} />
                </button> : <span className="voice-action-placeholder" aria-hidden="true" />}
                <button
                  className="icon-button delete-voice"
                  title="从音色库移除"
                  aria-label={`从音色库移除 ${item.display_name}`}
                  onClick={() => onRemove(item)}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))
        ) : (
          <div className="empty-state">
            <Library size={21} />
            <span>当前来源还没有可用音色</span>
          </div>
        )}
      </div>
      {showImport && (
        <ImportVoiceDialog
          models={models}
          onClose={() => setShowImport(false)}
          onImport={async (config) => {
            await onImport(config);
            setShowImport(false);
            setProvider(config.provider);
          }}
          onBatchImport={async (configs) => {
            await onBatchImport(configs);
            setShowImport(false);
            setProvider(configs[0]?.provider || "all");
          }}
        />
      )}
      {renameTarget && (
        <RenameVoiceDialog
          voice={renameTarget}
          onClose={() => setRenameTarget(null)}
          onRename={async (displayName) => {
            await onRename(renameTarget, displayName);
            setRenameTarget(null);
          }}
        />
      )}
    </section>
  );
}

function RenameVoiceDialog({
  voice,
  onClose,
  onRename,
}: {
  voice: Voice;
  onClose: () => void;
  onRename: (displayName: string) => Promise<void>;
}) {
  const [displayName, setDisplayName] = useState(voice.display_name);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");
  const submit = async () => {
    const value = displayName.trim();
    if (!value || value === voice.display_name) return;
    setWorking(true);
    setMessage("");
    try {
      await onRename(value);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "重命名失败");
    } finally {
      setWorking(false);
    }
  };
  return (
    <div className="modal-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target && !working) onClose(); }}>
      <div className="voice-modal rename-voice-modal" role="dialog" aria-modal="true" aria-labelledby="rename-voice-title">
        <div className="modal-head">
          <div><h3 id="rename-voice-title">重命名音色</h3></div>
          <button className="icon-button" type="button" onClick={onClose} disabled={working} title="关闭" aria-label="关闭"><X size={18} /></button>
        </div>
        <div className="modal-form">
          <label htmlFor="rename-voice-name">显示名称</label>
          <input id="rename-voice-name" autoFocus maxLength={100} value={displayName} onChange={(event) => setDisplayName(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void submit(); }} />
          <div className="rename-api-id"><span>兼容别名</span><code>{voice.public_name}</code></div>
          <p className="modal-note"><ShieldCheck size={15} />重命名只改变界面中显示的名称，现有 API 调用、任务记录和厂商 Voice ID 不受影响。</p>
          {message && <div className="form-message">{message}</div>}
        </div>
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose} disabled={working}>取消</button>
          <button className="primary-button compact" type="button" onClick={() => void submit()} disabled={working || !displayName.trim() || displayName.trim() === voice.display_name}><Save size={16} />{working ? "正在保存..." : "保存名称"}</button>
        </div>
      </div>
    </div>
  );
}

function ImportVoiceDialog({
  models,
  onClose,
  onImport,
  onBatchImport,
}: {
  models: Model[];
  onClose: () => void;
  onImport: (config: ImportVoiceConfig) => Promise<void>;
  onBatchImport: (configs: ImportVoiceConfig[]) => Promise<void>;
}) {
  const importModels = models.filter(
    (item) =>
      item.supports_clone &&
      item.operations.includes("clone") &&
      ["dashscope", "volcengine", "minimax"].includes(item.provider),
  );
  const syncProviders = ["dashscope", "volcengine", "minimax"].filter((id) =>
    importModels.some((item) => item.provider === id),
  );
  const initialProvider = syncProviders[0] || importModels[0]?.provider || "";
  const [mode, setMode] = useState<"sync" | "manual">("sync");
  const [provider, setProvider] = useState(initialProvider);
  const [modelId, setModelId] = useState(
    importModels.find((item) => item.provider === initialProvider)?.model_id ||
      "",
  );
  const [voiceId, setVoiceId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [publicName, setPublicName] = useState("");
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");
  const [cloudVoices, setCloudVoices] = useState<CloudVoice[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [edits, setEdits] = useState<
    Record<string, { display_name: string; public_name: string }>
  >({});
  const providerModels = importModels.filter(
    (item) => item.provider === provider,
  );
  const defaultNames = (item: CloudVoice, index: number) => {
    const providerName = providerMeta[item.provider || provider]?.label || item.provider || provider;
    const displayName = item.display_name?.trim() || `${providerName}复刻音色 ${String(index + 1).padStart(2, "0")}`;
    const shortId = item.provider_voice_id.replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase().slice(-24);
    return {
      display_name: displayName,
      public_name: `${item.provider}-${shortId || `voice-${index + 1}`}`.slice(0, 48),
    };
  };
  const chooseProvider = (next: string) => {
    setProvider(next);
    setModelId(
      importModels.find((item) => item.provider === next)?.model_id || "",
    );
    setCloudVoices([]);
    setSelected([]);
    setEdits({});
    setMessage("");
  };
  const chooseMode = (next: "sync" | "manual") => {
    setMode(next);
    if (next === "sync" && !syncProviders.includes(provider))
      chooseProvider(syncProviders[0] || "");
    setMessage("");
  };
  const loadCloudVoices = async () => {
    if (!syncProviders.includes(provider)) return;
    setWorking(true);
    setMessage("");
    try {
      const result = await api<{ voices: CloudVoice[] }>(
        `/api/voices/cloud/${provider}`,
      );
      setCloudVoices(result.voices);
      setSelected([]);
      setEdits(
        Object.fromEntries(
          result.voices.map((item, index) => [
            item.provider_voice_id,
            defaultNames(item, index),
          ]),
        ),
      );
      if (!result.voices.length)
        setMessage("厂商账号中没有可同步的克隆音色。");
    } catch (error) {
      setCloudVoices([]);
      setMessage(error instanceof Error ? error.message : "读取云端音色失败");
    } finally {
      setWorking(false);
    }
  };
  const submit = async () => {
    if (
      !voiceId.trim() ||
      !displayName.trim() ||
      !publicName.trim() ||
      !modelId
    )
      return;
    setWorking(true);
    setMessage("");
    try {
      await onImport({
        provider,
        model_id: modelId,
        provider_voice_id: voiceId.trim(),
        display_name: displayName.trim(),
        public_name: publicName.trim(),
        languages: ["zh-CN"],
      });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "导入失败");
    } finally {
      setWorking(false);
    }
  };
  const submitBatch = async () => {
    const items = cloudVoices.filter((item) =>
      selected.includes(item.provider_voice_id),
    );
    if (!items.length) return;
    const configs = items.map((item) => ({
      provider,
      model_id: provider === "minimax" ? modelId : item.model_id,
      provider_voice_id: item.provider_voice_id,
      display_name: edits[item.provider_voice_id]?.display_name.trim() || item.display_name,
      public_name: edits[item.provider_voice_id]?.public_name.trim() || "",
      languages: [item.language === "zh" ? "zh-CN" : item.language || "zh-CN"],
    }));
    if (configs.some((item) => !item.display_name || !item.public_name)) {
      setMessage("已选择音色的显示名称和兼容别名不能为空。");
      return;
    }
    setWorking(true);
    setMessage("");
    try {
      await onBatchImport(configs);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "批量导入失败");
    } finally {
      setWorking(false);
    }
  };
  const selectable = cloudVoices.filter(
    (item) => item.compatible && !item.imported,
  );
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className={"voice-modal " + (mode === "sync" ? "sync-modal" : "")}
        role="dialog"
        aria-modal="true"
        aria-labelledby="import-title"
      >
        <div className="modal-head">
          <div>
            <h3 id="import-title">导入已有厂商音色</h3>
          </div>
          <button className="icon-button" title="关闭" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <div className="modal-form">
          <div className="import-mode" role="tablist" aria-label="导入方式">
            <button
              className={mode === "sync" ? "selected" : ""}
              onClick={() => chooseMode("sync")}
              role="tab"
              aria-selected={mode === "sync"}
            >
              云端同步
            </button>
            <button
              className={mode === "manual" ? "selected" : ""}
              onClick={() => chooseMode("manual")}
              role="tab"
              aria-selected={mode === "manual"}
            >
              手工输入 ID
            </button>
          </div>
          <div className="form-grid">
            <div>
              <label>厂商</label>
              <select
                value={provider}
                onChange={(event) => chooseProvider(event.target.value)}
              >
                {(mode === "sync" ? syncProviders : credentialProviderIds)
                  .filter((id) =>
                    importModels.some((item) => item.provider === id),
                  )
                  .map((id) => (
                    <option value={id} key={id}>
                      {providerMeta[id].label}
                    </option>
                  ))}
              </select>
            </div>
            <div>
              <label>目标模型</label>
              <select
                value={modelId}
                onChange={(event) => setModelId(event.target.value)}
                disabled={mode === "sync" && provider !== "minimax"}
              >
                {providerModels.map((item) => (
                  <option value={item.model_id} key={item.gateway_id}>
                    {item.display_name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {mode === "sync" ? (
            <>
              <div className="sync-toolbar">
                <div>
                  <strong>云端克隆音色</strong>
                  <span>{cloudVoices.length ? `${selectable.length} 个可导入 · 已选 ${selected.length}` : "尚未读取"}</span>
                </div>
                <button
                  className="secondary-button"
                  onClick={loadCloudVoices}
                  disabled={working}
                >
                  <RefreshCw size={14} className={working ? "spinning" : ""} />
                  {working ? "正在读取" : "读取云端音色"}
                </button>
              </div>
              <p className="import-naming-note">
                默认显示名称沿用厂商音色名称；兼容别名按“厂商 + Voice ID”生成，可在勾选后修改。
              </p>
              {cloudVoices.length > 0 && (
                <div className="cloud-voice-list">
                  <label className="cloud-select-all">
                    <input
                      type="checkbox"
                      checked={selectable.length > 0 && selected.length === selectable.length}
                      onChange={(event) =>
                        setSelected(
                          event.target.checked
                            ? selectable.map((item) => item.provider_voice_id)
                            : [],
                        )
                      }
                    />
                    <span>选择全部可导入音色</span>
                    <small>{selected.length ? `已选 ${selected.length} 个` : ""}</small>
                  </label>
                  {cloudVoices.map((item) => {
                    const disabled = item.imported || !item.compatible;
                    const checked = selected.includes(item.provider_voice_id);
                    return (
                      <div
                        className={"cloud-voice-row " + (disabled ? "disabled" : "")}
                        key={`${item.model_id}:${item.provider_voice_id}`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={disabled}
                          onChange={(event) =>
                            setSelected((current) =>
                              event.target.checked
                                ? [...current, item.provider_voice_id]
                                : current.filter((id) => id !== item.provider_voice_id),
                            )
                          }
                          aria-label={`选择 ${item.display_name}`}
                        />
                        <div className="cloud-voice-main">
                          <div className="cloud-voice-meta">
                            <div>
                              <strong>{item.display_name}</strong>
                              <code>{item.provider_voice_id}</code>
                            </div>
                            <span className={item.imported ? "is-imported" : !item.compatible ? "is-incompatible" : ""}>
                              {item.imported ? "已导入" : !item.compatible ? "模型不兼容" : "可导入"}
                            </span>
                          </div>
                          <small>{item.compatibility_message || (provider === "minimax" ? "可用于全部 MiniMax Speech 模型" : item.model_id)}</small>
                          {checked && (
                            <div className="cloud-voice-fields">
                              <label>导入后显示名称<input
                                value={edits[item.provider_voice_id]?.display_name || ""}
                                onChange={(event) =>
                                  setEdits((current) => ({
                                    ...current,
                                    [item.provider_voice_id]: {
                                      ...current[item.provider_voice_id],
                                      display_name: event.target.value,
                                    },
                                  }))
                                }
                                placeholder="显示名称"
                              /></label>
                              <label>OpenAI 兼容别名<input
                                value={edits[item.provider_voice_id]?.public_name || ""}
                                onChange={(event) =>
                                  setEdits((current) => ({
                                    ...current,
                                    [item.provider_voice_id]: {
                                      ...current[item.provider_voice_id],
                                      public_name: event.target.value,
                                    },
                                  }))
                                }
                                placeholder="兼容别名"
                              /></label>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              <p className="modal-note">
                <ShieldCheck size={15} />
                此操作只读取并登记云端音色，不会创建、删除音色或生成收费音频。
              </p>
            </>
          ) : (
            <>
              <label>{provider === "volcengine" ? "火山音色 ID / speaker_id" : "厂商 Voice ID"}</label>
              <input
                value={voiceId}
                onChange={(event) => setVoiceId(event.target.value)}
                placeholder={provider === "volcengine" ? "例如：S_xxxxx 或 custom_zh_xxx" : "粘贴控制台中的完整 Voice ID"}
                autoFocus
              />
              <div className="form-grid">
                <div>
                  <label>显示名称</label>
                  <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="例如：我的旁白音色" />
                </div>
                <div>
                  <label>兼容别名</label>
                  <input value={publicName} onChange={(event) => setPublicName(event.target.value)} placeholder="例如：my-volc-voice" />
                </div>
              </div>
              {provider === "volcengine" && (
                <p className="modal-note"><ShieldCheck size={15} />保存前会向火山引擎查询音色状态。批量同步还需配置火山 OpenAPI AK/SK 与项目名称。</p>
              )}
              {provider === "minimax" && (
                <p className="modal-note"><ShieldCheck size={15} />MiniMax Voice ID 将直接导入，首次合成时由厂商接口验证其可用性。</p>
              )}
            </>
          )}
          {message && <div className="form-message">{message}</div>}
        </div>
        <div className="modal-actions">
          <button className="secondary-button" onClick={onClose}>
            取消
          </button>
          <button
            className="primary-button compact"
            onClick={mode === "sync" ? submitBatch : submit}
            disabled={
              working ||
              (mode === "sync"
                ? selected.length === 0
                : !voiceId.trim() || !displayName.trim() || !publicName.trim())
            }
          >
            <Save size={15} />
            {mode === "sync"
              ? working
                ? "正在导入..."
                : `导入所选音色${selected.length ? ` (${selected.length})` : ""}`
              : working
              ? provider === "minimax"
                ? "正在导入..."
                : "正在验证..."
              : provider === "minimax"
                ? "直接导入"
                : "验证并导入"}
          </button>
        </div>
      </div>
    </div>
  );
}

function VoiceDesignPanel({
  models,
  onDesign,
}: {
  models: Model[];
  onDesign: (config: DesignConfig) => Promise<Voice>;
}) {
  const designModels = useMemo(() => models.filter((item) => item.operations.includes("design")), [models]);
  const [provider, setProvider] = useState("mimo");
  const [modelId, setModelId] = useState("mimo-v2.5-tts-voicedesign");
  const [prompt, setPrompt] = useState("年轻女性，声音清亮柔和，语速稍快，带有自然上扬的活泼语调，适合科技产品介绍。");
  const [previewText, setPreviewText] = useState("大家好，欢迎来到今天的声音实验室。让我们用一段自然的问候，听听这个全新的声音。 ");
  const [displayName, setDisplayName] = useState("我的设计音色");
  const [publicName, setPublicName] = useState("design-" + Date.now().toString().slice(-6));
  const [working, setWorking] = useState(false);
  const [previewVoice, setPreviewVoice] = useState<Voice | null>(null);
  const providerModels = designModels.filter((item) => item.provider === provider);
  const selected = designModels.find((item) => item.provider === provider && item.model_id === modelId);
  const promptLimit = selected?.design_prompt_max ?? 2000;
  const previewMin = selected?.design_preview_min ?? 1;
  const previewLimit = selected?.design_preview_max ?? 2000;
  const promptInvalid = prompt.length > promptLimit;
  const previewInvalid = previewText.length < previewMin || previewText.length > previewLimit;
  const designProviderIds = credentialProviderIds.filter((id) =>
    designModels.some((item) => item.provider === id),
  );

  useEffect(() => {
    if (selected) return;
    const first = providerModels[0] || designModels[0];
    if (first) {
      setProvider(first.provider);
      setModelId(first.model_id);
    }
  }, [designModels, providerModels, selected]);

  const chooseProvider = (nextProvider: string) => {
    setProvider(nextProvider);
    const first = designModels.find((item) => item.provider === nextProvider);
    if (first) setModelId(first.model_id);
    setPreviewVoice(null);
  };
  const submit = async () => {
    if (!selected || !prompt.trim() || !previewText.trim() || promptInvalid || previewInvalid || !displayName.trim() || !publicName.trim()) return;
    setWorking(true);
    try {
      const voice = await onDesign({
        provider,
        model_id: modelId,
        prompt: prompt.trim(),
        preview_text: previewText.trim(),
        display_name: displayName.trim(),
        public_name: publicName.trim(),
      });
      setPreviewVoice(voice);
    } finally {
      setWorking(false);
    }
  };

  return (
    <section className="page-section design-page">
      <div className="design-hero">
        <div>
          <h2>先写下声音的性格，<br /><em>再让它开口。</em></h2>
          <p>不需要参考音频。用自然语言描述年龄、质感、语速和情绪，创建一枚可以复用的设计音色。</p>
        </div>
      </div>
      <div className="design-layout">
        <div className="design-form">
          <h3 className="design-section-title">选择设计引擎</h3>
          <div className="design-engine-grid">
            <ProviderSelector
              className="design-provider-selector"
              label="声音设计厂商"
              value={provider}
              onChange={chooseProvider}
              options={designProviderIds.map((id) => ({
                id,
                label: providerMeta[id].label,
                mark: providerMeta[id].mark,
                tone: providerMeta[id].tone,
                detail: `${designModels.filter((item) => item.provider === id).length} 个设计模型`,
              }))}
            />
            <div className="design-model-field">
              <label htmlFor="design-model">设计模型</label>
              <select
                id="design-model"
                translate="no"
                value={modelId}
                onChange={(event) => setModelId(event.target.value)}
              >
                {providerModels.map((item) => <option value={item.model_id} key={item.gateway_id}>{item.display_name}</option>)}
              </select>
            </div>
          </div>
          <h3 className="design-section-title design-section-spaced">描述你想要的声音</h3>
          <div className="design-copy-grid">
            <div className="design-copy-field">
              <label htmlFor="design-prompt">声音描述</label>
              <div className="design-textarea-wrap">
                <textarea id="design-prompt" className="design-prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} aria-invalid={promptInvalid} />
                <div className={promptInvalid ? "design-count invalid" : "design-count"}>{prompt.length} / {promptLimit.toLocaleString()}</div>
              </div>
            </div>
            <div className="design-copy-field">
              <label htmlFor="design-preview-text">试听文本</label>
              <div className="design-textarea-wrap">
                <textarea id="design-preview-text" className="design-preview-text" value={previewText} onChange={(event) => setPreviewText(event.target.value)} aria-invalid={previewInvalid} />
                <div className={previewInvalid ? "design-count invalid" : "design-count"}>{previewText.length} / {previewLimit.toLocaleString()}{previewMin > 1 ? `，至少 ${previewMin}` : ""}</div>
              </div>
            </div>
          </div>
          <div className="design-action-grid">
            <div className="form-grid design-names"><div><label>显示名称</label><input value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></div><div><label>兼容别名</label><input value={publicName} onChange={(event) => setPublicName(event.target.value)} /></div></div>
            <button className="primary-button design-submit" onClick={() => void submit()} disabled={working || !selected || !prompt.trim() || !previewText.trim() || promptInvalid || previewInvalid || !displayName.trim() || !publicName.trim()}><WandSparkles size={17} />{working ? "正在设计..." : "创建并试听音色"}</button>
          </div>
          {previewVoice && (
            <div className="design-preview-result" aria-live="polite">
              <div className="design-preview-icon"><Volume2 size={20} /></div>
              <div className="design-preview-main">
                <span>试听结果</span>
                <strong>{previewVoice.display_name}</strong>
                <small>{previewVoice.provider === "mimo" ? "请求级设计模板" : "已保存到音色库"} · {previewVoice.public_name}</small>
                {previewVoice.preview_url && <audio controls src={previewVoice.preview_url} />}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function ClonePanel({
  models,
  onClone,
  onNotice,
}: {
  models: Model[];
  onClone: (config: CloneConfig, file: File) => Promise<void>;
  onNotice: (message: string) => void;
}) {
  const cloneModels = useMemo(
    () =>
      models.filter(
        (item) => item.supports_clone && item.operations.includes("clone"),
      ),
    [models],
  );
  const [provider, setProvider] = useState("mimo");
  const [modelId, setModelId] = useState("mimo-v2.5-tts-voiceclone");
  const [displayName, setDisplayName] = useState("我的克隆音色");
  const [publicName, setPublicName] = useState(
    "clone-" + Date.now().toString().slice(-6),
  );
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [working, setWorking] = useState(false);
  const providerModels = cloneModels.filter(
    (item) => item.provider === provider,
  );
  const selected = cloneModels.find(
    (item) => item.provider === provider && item.model_id === modelId,
  );
  const isQwenClone = selected?.provider === "dashscope";
  const isVolcengineClone = selected?.provider === "volcengine";
  const isMiniMaxClone = selected?.provider === "minimax";

  useEffect(() => {
    if (selected) return;
    const first = providerModels[0] || cloneModels[0];
    if (first) {
      setProvider(first.provider);
      setModelId(first.model_id);
    }
  }, [cloneModels, providerModels, selected]);

  const chooseProvider = (nextProvider: string) => {
    setProvider(nextProvider);
    const first = cloneModels.find((item) => item.provider === nextProvider);
    if (first) setModelId(first.model_id);
  };
  const acceptedExtensions = isVolcengineClone
    ? [".wav", ".mp3", ".ogg", ".m4a", ".aac", ".pcm"]
    : [".wav", ".mp3", ".m4a"];
  const acceptAudioFile = (file: File | undefined) => {
    if (!file) return;
    const extension = file.name.includes(".")
      ? file.name.slice(file.name.lastIndexOf(".")).toLowerCase()
      : "";
    if (!file.type.startsWith("audio/") && !acceptedExtensions.includes(extension)) {
      onNotice("请选择 WAV、MP3、M4A 等支持的音频文件");
      return;
    }
    setSelectedFile(file);
    setFileName(file.name);
    onNotice("");
  };
  const handleDrop = (event: React.DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
    acceptAudioFile(event.dataTransfer.files?.[0]);
  };
  const submit = async () => {
    if (
      !selected ||
      !displayName.trim() ||
      !publicName.trim() ||
      !selectedFile
    )
      return;
    setWorking(true);
    try {
      await onClone({
        provider,
        model_id: modelId,
        display_name: displayName.trim(),
        public_name: publicName.trim(),
      }, selectedFile);
    } finally {
      setWorking(false);
    }
  };

  return (
    <section className="page-section clone-page">
      <WorkspaceHero
        title="让一个真实的声音"
        accent="留下它的纹理。"
        description="上传参考音频，选择目标厂商和模型，创建一个可以在语音合成中复用的声音。"
      />
      <div className="clone-form">
        <div className="clone-workspace-grid">
          <label
            className={`upload-zone${isDragging ? " is-dragging" : ""}`}
            onDragEnter={(event) => {
              event.preventDefault();
              event.stopPropagation();
              setIsDragging(true);
            }}
            onDragOver={(event) => {
              event.preventDefault();
              event.stopPropagation();
              event.dataTransfer.dropEffect = "copy";
              setIsDragging(true);
            }}
            onDragLeave={(event) => {
              event.preventDefault();
              event.stopPropagation();
              setIsDragging(false);
            }}
            onDrop={handleDrop}
          >
            <input
              type="file"
              accept={
                isVolcengineClone
                  ? ".wav,.mp3,.ogg,.m4a,.aac,.pcm,audio/*"
                  : ".wav,.mp3,.m4a,audio/wav,audio/mpeg,audio/mp4"
              }
              onChange={(event) => acceptAudioFile(event.target.files?.[0])}
            />
            <FileAudio size={25} />
            <strong>{fileName || "拖入参考音频，或点击选择"}</strong>
            <span>
              {isQwenClone
                ? "WAV 16-bit / MP3 / M4A · 推荐 10–20 秒 · 不超过 10 MB"
                : isVolcengineClone
                  ? "WAV / MP3 / OGG / M4A / AAC / PCM · 不超过 10 MB"
                  : isMiniMaxClone
                    ? "WAV / MP3 / M4A · 10 秒至 5 分钟 · 不超过 20 MB"
                    : "WAV / MP3 / M4A · 建议 10–30 秒 · 不超过 20 MB"}
            </span>
            <span className="upload-link">
              <Upload size={14} />
              {fileName ? "重新选择" : "选择文件"}
            </span>
          </label>
          <div className="clone-settings-panel">
            <div className="clone-settings-fields">
              <div className="clone-field">
                <label htmlFor="clone-provider">目标厂商</label>
                <select
                  id="clone-provider"
                  value={provider}
                  onChange={(event) => chooseProvider(event.target.value)}
                >
                  {credentialProviderIds
                    .filter((id) =>
                      cloneModels.some((item) => item.provider === id),
                    )
                    .map((id) => (
                      <option value={id} key={id}>
                        {providerMeta[id].label}
                      </option>
                    ))}
                </select>
              </div>
              <div className="clone-field">
                <label htmlFor="clone-model">目标模型</label>
                <select
                  id="clone-model"
                  translate="no"
                  value={modelId}
                  onChange={(event) => setModelId(event.target.value)}
                >
                  {providerModels.map((item) => (
                    <option value={item.model_id} key={item.gateway_id}>
                      {item.display_name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="clone-field">
                <label htmlFor="clone-display-name">显示名称</label>
                <input
                  id="clone-display-name"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                />
              </div>
              <div className="clone-field">
                <label htmlFor="clone-public-name">兼容别名</label>
                <input
                  id="clone-public-name"
                  value={publicName}
                  onChange={(event) => setPublicName(event.target.value)}
                />
              </div>
            </div>
            <button
              className="primary-button full"
              onClick={submit}
              disabled={
                working ||
                !selected ||
                !selectedFile ||
                !displayName.trim() ||
                !publicName.trim()
              }
            >
              <Mic2 size={17} />
              {working ? "处理中..." : "创建参考音色"}
            </button>
            <p className="form-footnote">
              <Radio size={14} />
              {isQwenClone
                ? "创建时会上传样本并取得远端 Voice ID；后续合成只发送 Voice ID。"
                : isVolcengineClone
                  ? "创建时上传样本并取得远端音色 ID；首次正式合成可能触发厂商音色槽位计费。"
                  : isMiniMaxClone
                    ? "创建时上传样本并取得远端 Voice ID；7 天内未正式使用的音色可能被厂商删除。"
                    : "该模型会在每次生成语音时向厂商发送本地参考音频。"}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

type GatewayTestResult = {
  status: "idle" | "running" | "success" | "error" | "cancelled";
  message?: string;
  statusCode?: number;
  latency?: number;
  contentType?: string;
  size?: number;
  jobId?: string;
  chunks?: number;
  firstChunkLatency?: number;
  nativeStreaming?: boolean;
  format?: string;
};

function GatewayPanel({
  gateway,
  models,
  voices,
}: {
  gateway: Gateway | null;
  models: Model[];
  voices: Voice[];
}) {
  const [current, setCurrent] = useState(gateway);
  const [visibleKey, setVisibleKey] = useState(false);
  const [copied, setCopied] = useState("");
  const [rotating, setRotating] = useState(false);
  const [testModel, setTestModel] = useState("");
  const [testVoice, setTestVoice] = useState("");
  const [testText, setTestText] = useState("你好，这是一段 Voice Studio 网关测试语音。 ");
  const [testFormat, setTestFormat] = useState("mp3");
  const [catalogTest, setCatalogTest] = useState<GatewayTestResult>({ status: "idle" });
  const [speechTest, setSpeechTest] = useState<GatewayTestResult>({ status: "idle" });
  const [streamTest, setStreamTest] = useState<GatewayTestResult>({ status: "idle" });
  const [testAudioUrl, setTestAudioUrl] = useState("");
  const [streamAudioUrl, setStreamAudioUrl] = useState("");
  const streamAbortRef = useRef<AbortController | null>(null);
  const [exampleTab, setExampleTab] = useState("powershell");
  const [stats, setStats] = useState<GatewayStats | null>(null);
  const [statsWindow, setStatsWindow] = useState("7d");
  const [statsProvider, setStatsProvider] = useState("");
  const [statsLoading, setStatsLoading] = useState(false);
  const [gatewayView, setGatewayView] = useState<"docs" | "test" | "stats">("docs");
  const [openEndpoint, setOpenEndpoint] = useState("");
  useEffect(() => setCurrent(gateway), [gateway]);
  const activeGateway = current || gateway;
  const base = activeGateway?.base_url || "http://127.0.0.1:8765/v1";
  const key = activeGateway?.key || "";
  const synthesisModels = models.filter((item) => item.operations.includes("synthesis"));
  const selectedTestModel = synthesisModels.find((item) => item.gateway_id === testModel);
  const compatibleVoices = voices.filter((item) => voiceMatchesModel(item, selectedTestModel));
  const streamFormat = selectedTestModel?.provider === "mimo" ? "pcm" : "mp3";

  const refreshStats = async () => {
    setStatsLoading(true);
    try {
      const query = new URLSearchParams({ window: statsWindow });
      if (statsProvider) query.set("provider", statsProvider);
      setStats(await api<GatewayStats>(`/api/gateway/stats?${query.toString()}`));
    } finally {
      setStatsLoading(false);
    }
  };

  useEffect(() => {
    if (!testModel && synthesisModels[0]) setTestModel(synthesisModels[0].gateway_id);
  }, [testModel, synthesisModels]);
  useEffect(() => {
    if (!compatibleVoices.some((item) => item.public_name === testVoice)) {
      setTestVoice(compatibleVoices[0]?.public_name || "alloy");
    }
  }, [compatibleVoices, testVoice]);
  useEffect(() => () => {
    if (testAudioUrl) URL.revokeObjectURL(testAudioUrl);
  }, [testAudioUrl]);
  useEffect(() => () => {
    streamAbortRef.current?.abort();
    if (streamAudioUrl) URL.revokeObjectURL(streamAudioUrl);
  }, [streamAudioUrl]);
  useEffect(() => {
    refreshStats().catch(() => undefined);
  }, [statsWindow, statsProvider]);

  const endpoint = (path: string) => `${base.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
  const formatBytes = (size?: number) => {
    if (!size) return "-";
    return size < 1024 ? `${size} B` : `${(size / 1024).toFixed(1)} KB`;
  };
  const copy = async (label: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(label);
      window.setTimeout(() => setCopied(""), 1800);
    } catch {
      setCopied("复制失败");
    }
  };
  const rotate = async () => {
    if (!activeGateway?.managed || !window.confirm("轮换后旧网关 Key 会立即失效，确定继续吗？")) return;
    setRotating(true);
    try {
      const result = await api<{ key: string; key_hint: string; key_source: string; managed: boolean }>("/api/gateway/rotate", { method: "POST" });
      setCurrent({ ...activeGateway, key: result.key, key_hint: result.key_hint, key_source: result.key_source, managed: result.managed });
      setVisibleKey(true);
      setCopied("已生成新 Key");
    } catch (error) {
      setCopied(error instanceof Error ? error.message : "轮换失败");
    } finally {
      setRotating(false);
    }
  };
  const payload = {
    model: testModel || "tts-default",
    voice: testVoice || "alloy",
    input: testText,
    response_format: testFormat,
  };
  const ps = [
    '$headers = @{ Authorization = "Bearer ' + key + '" }',
    "$body = @" + "{ model = \"" + payload.model + "\"; voice = \"" + payload.voice + "\"; input = " + JSON.stringify(payload.input) + "; response_format = \"" + payload.response_format + "\" } | ConvertTo-Json",
    `Invoke-WebRequest "${endpoint("audio/speech")}" -Headers $headers -Method Post -ContentType "application/json" -Body $body -OutFile voice.${testFormat}`,
  ].join("\n");
  const curl = `curl "${endpoint("audio/speech")}" -H "Authorization: Bearer ${key}" -H "Content-Type: application/json" -d '${JSON.stringify(payload)}' --output voice.${testFormat}`;
  const python = `from pathlib import Path\nfrom openai import OpenAI\n\nclient = OpenAI(api_key=${JSON.stringify(key)}, base_url=${JSON.stringify(base)})\nwith client.audio.speech.with_streaming_response.create(\n    model=${JSON.stringify(payload.model)},\n    voice=${JSON.stringify(payload.voice)},\n    input=${JSON.stringify(payload.input)},\n    response_format=${JSON.stringify(payload.response_format)},\n) as response:\n    response.stream_to_file(Path("voice.${testFormat}"))`;
  const javascript = `import OpenAI from "openai";\nimport { writeFile } from "node:fs/promises";\n\nconst client = new OpenAI({ apiKey: ${JSON.stringify(key)}, baseURL: ${JSON.stringify(base)} });\nconst audio = await client.audio.speech.create(${JSON.stringify(payload, null, 2)});\nawait writeFile("voice.${testFormat}", Buffer.from(await audio.arrayBuffer()));`;
  const stream = `# SSE 流式网关（每个 audio 事件是一段 Base64 音频）\ncurl.exe -N "${endpoint("audio/speech/stream")}" -H "Authorization: Bearer ${key}" -H "Content-Type: application/json" -d '${JSON.stringify({ ...payload, chunk_size: 4096 })}'`;
  const examples: Record<string, string> = { powershell: ps, curl, python, javascript, stream };

  const testModels = async () => {
    setCatalogTest({ status: "running" });
    const started = performance.now();
    try {
      const response = await fetch(endpoint("models"), { headers: { Authorization: "Bearer " + key } });
      if (!response.ok) throw new Error(await responseError(response));
      const result = await response.json() as { data?: Array<{ id: string }> };
      setCatalogTest({ status: "success", statusCode: response.status, latency: Math.round(performance.now() - started), message: `${result.data?.length || 0} 个模型可用` });
    } catch (error) {
      setCatalogTest({ status: "error", latency: Math.round(performance.now() - started), message: error instanceof Error ? error.message : "模型发现失败" });
    }
  };

  const testSpeech = async () => {
    if (!key) return setSpeechTest({ status: "error", message: "尚未读取网关 Key" });
    if (!testText.trim()) return setSpeechTest({ status: "error", message: "请输入测试文本" });
    if (!compatibleVoices.length) return setSpeechTest({ status: "error", message: "当前模型没有兼容音色，请先在音色库导入或克隆音色" });
    setStreamTest({ status: "idle" });
    setSpeechTest({ status: "running" });
    const started = performance.now();
    try {
      const response = await fetch(endpoint("audio/speech"), {
        method: "POST",
        headers: { Authorization: "Bearer " + key, "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const blob = await response.blob();
      if (testAudioUrl) URL.revokeObjectURL(testAudioUrl);
      const url = URL.createObjectURL(blob);
      setTestAudioUrl(url);
      setSpeechTest({
        status: "success",
        statusCode: response.status,
        latency: Math.round(performance.now() - started),
        contentType: response.headers.get("content-type") || blob.type,
        size: blob.size,
        jobId: response.headers.get("x-voice-studio-job") || undefined,
        message: "音频已返回",
      });
      refreshStats().catch(() => undefined);
    } catch (error) {
      setSpeechTest({ status: "error", latency: Math.round(performance.now() - started), message: error instanceof Error ? error.message : "语音测试失败" });
    }
  };

  const testStream = async () => {
    if (!key) return setStreamTest({ status: "error", message: "尚未读取网关 Key" });
    if (!testText.trim()) return setStreamTest({ status: "error", message: "请输入测试文本" });
    if (!compatibleVoices.length) return setStreamTest({ status: "error", message: "当前模型没有兼容音色，请先在音色库导入或克隆音色" });
    streamAbortRef.current?.abort();
    const controller = new AbortController();
    streamAbortRef.current = controller;
    setSpeechTest({ status: "idle" });
    setStreamTest({ status: "running" });
    const started = performance.now();
    const audioParts: BlobPart[] = [];
    let chunkCount = 0;
    let totalBytes = 0;
    let firstChunkLatency: number | undefined;
    let nativeStreaming = false;
    let jobId = "";
    let receivedFormat = streamFormat;
    try {
      const response = await fetch(endpoint("audio/speech/stream"), {
        method: "POST",
        headers: { Authorization: "Bearer " + key, "Content-Type": "application/json" },
        body: JSON.stringify({ ...payload, response_format: streamFormat, chunk_size: 4096 }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(await responseError(response));
      if (!response.body) throw new Error("网关没有返回可读取的流");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const consume = (block: string) => {
        let event = "message";
        const dataLines: string[] = [];
        for (const line of block.split(/\r?\n/)) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
        }
        if (!dataLines.length) return;
        const data = JSON.parse(dataLines.join("\n")) as { audio?: string; job_id?: string; format?: string; native_streaming?: boolean; error?: { message?: string } };
        if (event === "error") throw new Error(data.error?.message || "流式语音生成失败");
        if (event === "audio" && data.audio) {
          if (firstChunkLatency === undefined) firstChunkLatency = Math.round(performance.now() - started);
          const binary = atob(data.audio);
          const bytes = new Uint8Array(binary.length);
          for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
          audioParts.push(bytes as unknown as BlobPart);
          chunkCount += 1;
          totalBytes += bytes.byteLength;
        }
        if (event === "done") {
          jobId = data.job_id || jobId;
          nativeStreaming = Boolean(data.native_streaming);
          if (data.format) receivedFormat = data.format;
        }
      };
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() || "";
        blocks.forEach(consume);
        if (done) break;
      }
      if (buffer.trim()) consume(buffer);
      if (!audioParts.length) throw new Error("流式响应没有音频分片");
      if (streamAudioUrl) URL.revokeObjectURL(streamAudioUrl);
      const blob = new Blob(audioParts, { type: receivedFormat === "mp3" ? "audio/mpeg" : "application/octet-stream" });
      setStreamAudioUrl(URL.createObjectURL(blob));
      setStreamTest({
        status: "success",
        statusCode: response.status,
        latency: Math.round(performance.now() - started),
        contentType: response.headers.get("content-type") || "text/event-stream",
        size: blob.size,
        jobId: jobId || response.headers.get("x-voice-studio-job") || undefined,
        chunks: chunkCount,
        firstChunkLatency,
        nativeStreaming,
        format: receivedFormat,
        message: nativeStreaming ? "已收到厂商原生音频分片" : "已收到网关兼容音频分片",
      });
      refreshStats().catch(() => undefined);
    } catch (error) {
      if (controller.signal.aborted) {
        setStreamTest({
          status: "cancelled",
          latency: Math.round(performance.now() - started),
          firstChunkLatency,
          chunks: chunkCount,
          size: totalBytes,
          message: chunkCount ? `已中止，取消前收到 ${chunkCount} 个分片` : "已中止，尚未收到音频分片",
        });
        window.setTimeout(() => refreshStats().catch(() => undefined), 250);
      } else {
        setStreamTest({ status: "error", latency: Math.round(performance.now() - started), message: error instanceof Error ? error.message : "流式语音测试失败" });
      }
    } finally {
      if (streamAbortRef.current === controller) streamAbortRef.current = null;
    }
  };

  const cancelStream = () => {
    streamAbortRef.current?.abort();
  };

  const statusLabel = (result: GatewayTestResult) => {
    if (result.status === "running") return "请求中";
    if (result.status === "success") return "通过";
    if (result.status === "error") return "失败";
    if (result.status === "cancelled") return "已取消";
    return "未测试";
  };
  const catalogLabel = catalogTest.status === "success"
    ? `${catalogTest.message} · ${catalogTest.latency}ms`
    : catalogTest.status === "error"
      ? catalogTest.message || "模型发现失败"
      : catalogTest.status === "running"
        ? "正在请求 /v1/models..."
        : "尚未检查模型目录";
  const displayedTest = streamTest.status !== "idle" ? streamTest : speechTest;
  const formatLatency = (value: number | null) => value === null ? "--" : `${value}ms`;
  const statsProviderLabel = (id: string) => providerMeta[id]?.label || id;
  const endpointDocs = [
    {
      id: "models",
      method: "GET",
      path: "/v1/models",
      description: "列出四家厂商当前可用的语音模型。",
      request: "无请求体。使用 Bearer 网关 Key 鉴权。",
      response: "OpenAI 模型列表，模型 ID 可直接用于语音生成请求。",
      note: "适合在客户端启动时发现模型并刷新模型选择器。",
      example: `curl "${endpoint("models")}" -H "Authorization: Bearer $VOICE_STUDIO_API_KEY"`,
    },
    {
      id: "speech",
      method: "POST",
      path: "/v1/audio/speech",
      description: "使用 OpenAI 兼容格式生成完整音频文件。",
      request: "JSON：model、voice、input、response_format，可选 speed 与 instructions。",
      response: "返回 MP3、WAV、OPUS、AAC、FLAC 或 PCM 音频数据。",
      note: "模型与音色必须来自同一厂商并处于兼容作用域。",
      example: `curl "${endpoint("audio/speech")}" \\\n  -H "Authorization: Bearer $VOICE_STUDIO_API_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify(payload)}' --output voice.${testFormat}`,
    },
    {
      id: "stream",
      method: "POST",
      path: "/v1/audio/speech/stream",
      description: "通过 SSE 持续返回 Base64 编码的音频分片。",
      request: "与非流式接口相同，可额外传入 chunk_size 控制兼容分片大小。",
      response: "依次返回 audio、done 或 error 事件；done 中包含任务与上游流式状态。",
      note: "MiMo 当前返回 PCM，其他支持模型优先使用厂商原生 MP3 流。",
      example: `curl.exe -N "${endpoint("audio/speech/stream")}" \\\n  -H "Authorization: Bearer $VOICE_STUDIO_API_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify({ ...payload, chunk_size: 4096 })}'`,
    },
  ];
  return (
    <section className="page-section gateway-page">
      <div className="gateway-header">
        <WorkspaceHero
          title="把 Voice Studio"
          accent="接入你的应用。"
          description="使用 OpenAI 兼容接口调用四家语音模型。外部应用只需要 Base URL 和网关 Key，厂商凭据始终留在本机后端。"
        />
      </div>

      <section className="gateway-overview-grid" aria-label="网关凭据与快速开始">
        <div className="gateway-overview-primary">
          <div className="gateway-current-key">
            <div className="gateway-key-heading">
              <h3>当前网关 Key</h3>
              <span className="gateway-key-state"><span className="live-dot" />有效</span>
            </div>
            <div className="gateway-key-value">
              <code>{visibleKey ? key : (activeGateway?.key_hint || "未读取")}</code>
              <button className="icon-button" onClick={() => setVisibleKey((value) => !value)} title={visibleKey ? "隐藏网关 Key" : "显示网关 Key"} aria-label={visibleKey ? "隐藏网关 Key" : "显示网关 Key"}>
                {visibleKey ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
              <button className="icon-button" onClick={() => copy("网关 Key", key)} title="复制网关 Key" aria-label="复制网关 Key"><Copy size={16} /></button>
            </div>
            <div className="gateway-key-footer">
              <span>来源：{activeGateway?.key_source || "本地配置"}</span>
              <button className="secondary-button" disabled={!activeGateway?.managed || rotating} onClick={rotate}>
                <RotateCcw size={14} className={rotating ? "spinning" : ""} />
                {rotating ? "正在轮换" : "轮换网关 Key"}
              </button>
            </div>
            {copied && <div className="copy-feedback"><Check size={14} />{copied}</div>}
          </div>
          <div className="gateway-quickstart-card">
            <div className="gateway-quickstart-title">
              <span><Code2 size={18} />快速开始</span>
              <button className="quickstart-copy" onClick={() => copy("连接信息", `${base}\nBearer ${key}`)} title="复制连接信息"><Copy size={15} />复制</button>
            </div>
            <div className="gateway-quickstart-grid">
              <div><span>Base URL</span><code>{base}</code></div>
              <div><span>鉴权方式</span><code>Bearer $VOICE_STUDIO_API_KEY</code></div>
            </div>
            <p>把 Base URL 填入支持 OpenAI 的客户端，并将当前网关 Key 作为 API Key。</p>
          </div>
        </div>
        <div className="gateway-overview-secondary">
          <div className="gateway-credential-intro">
            <h3>网关访问凭据</h3>
            <p>这枚密钥用于本机应用访问统一语音网关，不会替代已保存的厂商 API Key。</p>
            <div className="gateway-credential-facts">
              <div><span>监听范围</span><strong>仅本机</strong></div>
              <div><span>管理方式</span><strong>{activeGateway?.managed ? "应用托管" : "环境变量"}</strong></div>
            </div>
          </div>
          <aside className="gateway-quickstart-aside">
            <div className="gateway-security-message">
              <ShieldCheck size={21} />
              <p>网关 Key 只应保存在受信任的本机应用中，不要放入公开网页、日志或源码仓库。</p>
            </div>
            <div className="gateway-error-format">
              <Code2 size={19} />
              <strong>错误格式</strong>
              <p>失败响应包含稳定错误码与可读消息。</p>
              <code>{'{"detail":{"code":"INVALID_API_KEY","message":"..."}}'}</code>
            </div>
          </aside>
        </div>
      </section>

      <div className="gateway-view-tabs" role="tablist" aria-label="网关页面">
        <button role="tab" aria-selected={gatewayView === "docs"} className={gatewayView === "docs" ? "selected" : ""} onClick={() => setGatewayView("docs")}><Code2 size={16} />接入文档</button>
        <button role="tab" aria-selected={gatewayView === "test"} className={gatewayView === "test" ? "selected" : ""} onClick={() => setGatewayView("test")}><FlaskConical size={16} />接口测试</button>
        <button role="tab" aria-selected={gatewayView === "stats"} className={gatewayView === "stats" ? "selected" : ""} onClick={() => setGatewayView("stats")}><Gauge size={16} />运行统计</button>
      </div>

      {gatewayView === "docs" && (
        <section className="gateway-docs" role="tabpanel">
          <div className="gateway-docs-heading">
            <h3>OpenAI 兼容接口</h3>
            <span>{endpointDocs.length} 个端点</span>
          </div>
          {endpointDocs.map((item) => {
            const expanded = openEndpoint === item.id;
            return (
              <article className={expanded ? "gateway-endpoint expanded" : "gateway-endpoint"} key={item.id}>
                <button className="gateway-endpoint-trigger" aria-expanded={expanded} onClick={() => setOpenEndpoint(expanded ? "" : item.id)}>
                  <span className={item.method === "GET" ? "gateway-method get" : "gateway-method post"}>{item.method}</span>
                  <code>{item.path}</code>
                  <span className="gateway-endpoint-summary">{item.description}</span>
                  <ChevronRight size={17} />
                </button>
                {expanded && (
                  <div className="gateway-endpoint-body">
                    <div className="gateway-endpoint-details">
                      <div><span>请求</span><p>{item.request}</p></div>
                      <div><span>响应</span><p>{item.response}</p></div>
                      <div><span>注意</span><p>{item.note}</p></div>
                    </div>
                    <div className="gateway-doc-code">
                      <div><span>cURL</span><button className="quickstart-copy" onClick={() => copy(`${item.method} ${item.path}`, item.example)}><Copy size={14} />复制</button></div>
                      <pre>{item.example}</pre>
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </section>
      )}

      {gatewayView === "stats" && <section className="gateway-observability" role="tabpanel">
        <div className="observability-head">
          <div>
            <h3>运行统计</h3>
            <p>仅统计本版本启用记录后的网关语音请求，不混入旧任务数据。</p>
          </div>
          <div className="observability-controls">
            <div className="segmented compact-segmented">
              {[['24h', '24 小时'], ['7d', '7 天'], ['30d', '30 天'], ['all', '全部']].map(([id, label]) => (
                <button className={statsWindow === id ? "selected" : ""} onClick={() => setStatsWindow(id)} key={id}>{label}</button>
              ))}
            </div>
            <select value={statsProvider} onChange={(event) => setStatsProvider(event.target.value)} aria-label="筛选统计来源">
              <option value="">全部来源</option>
              {credentialProviderIds.map((id) => <option value={id} key={id}>{providerMeta[id].label}</option>)}
            </select>
            <button className="icon-button" onClick={() => refreshStats()} title="刷新统计" disabled={statsLoading}>
              <RefreshCw size={15} className={statsLoading ? "spinning" : ""} />
            </button>
          </div>
        </div>
        {!stats && statsLoading ? (
          <div className="stats-empty"><RefreshCw size={17} className="spinning" />正在读取网关统计...</div>
        ) : stats && stats.total_requests > 0 ? (
          <>
            <div className="gateway-stat-strip">
              <div><span>请求</span><strong>{stats.total_requests}</strong><small>{stats.completed_requests} 成功 · {stats.failed_requests} 失败</small></div>
              <div><span>成功率</span><strong>{stats.success_rate}%</strong><small>{stats.sample_count} 个已记录样本</small></div>
              <div><span>首片 P50 / P95</span><strong>{formatLatency(stats.first_chunk_latency.p50)} <i>/</i> {formatLatency(stats.first_chunk_latency.p95)}</strong><small>{stats.first_chunk_latency.samples} 个流式样本</small></div>
              <div><span>总耗时 P50 / P95</span><strong>{formatLatency(stats.total_latency.p50)} <i>/</i> {formatLatency(stats.total_latency.p95)}</strong><small>{stats.total_latency.samples} 个耗时样本</small></div>
              <div><span>取消</span><strong>{stats.cancelled_requests}</strong><small>客户端主动中断</small></div>
            </div>
            <div className="observability-detail">
              <div className="stats-table">
                <div className="stats-table-head"><span>维度</span><span>请求</span><span>成功率</span><span>首片 P95</span><span>总耗时 P95</span></div>
                {stats.by_provider.map((item) => (
                  <div className="stats-table-row provider-row" key={`provider-${item.name}`}>
                    <span><b>{statsProviderLabel(item.name)}</b><small>来源</small></span><code>{item.requests}</code><code>{item.success_rate}%</code><code>{formatLatency(item.first_chunk_latency.p95)}</code><code>{formatLatency(item.total_latency.p95)}</code>
                  </div>
                ))}
                {stats.by_model.slice(0, 8).map((item) => (
                  <div className="stats-table-row" key={`model-${item.name}`}>
                    <span><b>{item.name.split('/').pop()}</b><small>{statsProviderLabel(item.name.split('/')[0])} · 模型</small></span><code>{item.requests}</code><code>{item.success_rate}%</code><code>{formatLatency(item.first_chunk_latency.p95)}</code><code>{formatLatency(item.total_latency.p95)}</code>
                  </div>
                ))}
              </div>
              <div className="error-summary">
                <div className="error-summary-head"><Activity size={15} /><span>错误聚合</span></div>
                {stats.errors.length ? stats.errors.slice(0, 6).map((item) => (
                  <div className="error-summary-row" key={item.code}><code>{item.code}</code><strong>{item.count}</strong></div>
                )) : <div className="error-summary-empty"><Check size={16} />当前范围没有失败请求</div>}
              </div>
            </div>
          </>
        ) : (
          <div className="stats-empty"><Gauge size={18} /><span>当前范围还没有网关语音请求。完成一次接口测试后会开始显示统计。</span></div>
        )}
      </section>}
      {gatewayView === "test" && <div className="gateway-testbench" role="tabpanel">
        <div className="testbench-header">
          <div>
            <h3>接口测试台</h3>
            <p>先测试模型发现，再用一小段文字确认网关、音色和厂商凭据都能正常工作。</p>
          </div>
          <div className="testbench-actions">
            <span className={"catalog-result " + catalogTest.status}>{catalogLabel}</span>
            <button className="secondary-button" onClick={testModels} disabled={catalogTest.status === "running" || !key}>
              <FlaskConical size={15} className={catalogTest.status === "running" ? "spinning" : ""} />
              {catalogTest.status === "running" ? "测试中..." : "测试模型接口"}
            </button>
          </div>
        </div>
        <div className="testbench-grid">
          <div className="test-request">
            <div className="test-field-row">
              <label>模型<select value={testModel} onChange={(event) => setTestModel(event.target.value)}>
                {credentialProviderIds.map((provider) => {
                  const items = synthesisModels.filter((item) => item.provider === provider);
                  if (!items.length) return null;
                  return <optgroup label={providerMeta[provider].label} key={provider}>{items.map((item) => <option value={item.gateway_id} key={item.gateway_id}>{item.display_name}</option>)}</optgroup>;
                })}
              </select></label>
              <label>音色<select value={testVoice} onChange={(event) => setTestVoice(event.target.value)} disabled={!compatibleVoices.length}>
                {!compatibleVoices.length && <option value="alloy">alloy（请先导入兼容音色）</option>}
                {compatibleVoices.map((item) => <option value={item.public_name} key={item.id}>{item.display_name} · {item.public_name}</option>)}
              </select></label>
            </div>
            <label className="test-field">测试文本<textarea value={testText} onChange={(event) => setTestText(event.target.value)} maxLength={500} /></label>
            <div className="test-controls">
              <div><span>格式</span><div className="segmented">{["mp3", "wav"].map((item) => <button className={testFormat === item ? "selected" : ""} onClick={() => setTestFormat(item)} key={item}>{item.toUpperCase()}</button>)}</div></div>
              <button className="primary-button compact" onClick={testSpeech} disabled={speechTest.status === "running" || streamTest.status === "running" || !key || !testModel || !compatibleVoices.length}><Play size={15} />{speechTest.status === "running" ? "生成中..." : "测试语音接口"}</button>
              {streamTest.status === "running"
                ? <button className="secondary-button compact" onClick={cancelStream}><X size={15} />取消流式</button>
                : <button className="secondary-button compact" onClick={testStream} disabled={speechTest.status === "running" || !key || !testModel || !compatibleVoices.length}><Radio size={15} />测试流式{selectedTestModel?.provider === "mimo" ? " · PCM" : ""}</button>}
            </div>
            {selectedTestModel && <div className="test-model-note"><span className={"provider-mark " + providerMeta[selectedTestModel.provider]?.tone}>{providerMeta[selectedTestModel.provider]?.mark}</span><span><strong>{selectedTestModel.display_name}</strong><small>厂商接口 · {compatibleVoices.length} 个兼容音色</small></span></div>}
          </div>
          <div className="test-result">
            <div className="result-head"><span>响应结果</span><span className={"test-status " + displayedTest.status}><span className="status-dot" />{statusLabel(displayedTest)}</span></div>
            {speechTest.status === "idle" && streamTest.status === "idle" && <div className="test-empty"><Radio size={18} /><span>生成一段测试音频后，响应信息会显示在这里。</span></div>}
            {speechTest.status === "running" && <div className="test-empty"><RefreshCw size={18} className="spinning" /><span>正在请求 /v1/audio/speech...</span></div>}
            {speechTest.status === "error" && <div className="test-error"><CircleHelp size={17} /><span>{speechTest.message}</span></div>}
            {speechTest.status === "success" && <>
              <div className="result-metrics"><div><span>HTTP</span><strong>{speechTest.statusCode}</strong></div><div><span>延迟</span><strong>{speechTest.latency}ms</strong></div><div><span>大小</span><strong>{formatBytes(speechTest.size)}</strong></div></div>
              {testAudioUrl && <div className="test-player"><Volume2 size={16} /><audio controls src={testAudioUrl} /><a className="download-button" href={testAudioUrl} download={`gateway-test.${testFormat}`} title="下载测试音频"><Download size={16} /></a></div>}
              <div className="result-detail"><span>Content-Type</span><code>{speechTest.contentType}</code>{speechTest.jobId && <><span>Job</span><code>{speechTest.jobId}</code></>}</div>
            </>}
            {streamTest.status === "running" && <div className="test-empty stream-live"><RefreshCw size={18} className="spinning" /><span>正在读取 /v1/audio/speech/stream...</span></div>}
            {streamTest.status === "error" && <div className="test-error"><CircleHelp size={17} /><span>{streamTest.message}</span></div>}
            {streamTest.status === "cancelled" && <>
              <div className="test-cancelled"><X size={17} /><span>{streamTest.message}</span></div>
              <div className="result-metrics stream-metrics"><div><span>首片</span><strong>{streamTest.firstChunkLatency === undefined ? "--" : `${streamTest.firstChunkLatency}ms`}</strong></div><div><span>取消耗时</span><strong>{streamTest.latency}ms</strong></div><div><span>已收分片</span><strong>{streamTest.chunks || 0}</strong></div><div><span>已收大小</span><strong>{formatBytes(streamTest.size)}</strong></div></div>
            </>}
            {streamTest.status === "success" && <>
              <div className="result-metrics stream-metrics"><div><span>首片</span><strong>{streamTest.firstChunkLatency}ms</strong></div><div><span>总耗时</span><strong>{streamTest.latency}ms</strong></div><div><span>分片</span><strong>{streamTest.chunks}</strong></div><div><span>大小</span><strong>{formatBytes(streamTest.size)}</strong></div></div>
              {streamAudioUrl && <div className="test-player">{streamTest.format === "pcm" ? <><Volume2 size={16} /><span className="test-audio-note">PCM 原始数据（24kHz / 16-bit / 单声道）</span></> : <><Volume2 size={16} /><audio controls src={streamAudioUrl} /></>}<a className="download-button" href={streamAudioUrl} download={`gateway-stream.${streamTest.format || "mp3"}`} title="下载流式音频"><Download size={16} /></a></div>}
              <div className="result-detail"><span>状态</span><code>{streamTest.message}</code><span>格式</span><code>{streamTest.format || "mp3"}</code><span>HTTP</span><code>{streamTest.statusCode}</code>{streamTest.nativeStreaming !== undefined && <><span>上游</span><code>{streamTest.nativeStreaming ? "原生分片" : "网关兼容分片"}</code></>}{streamTest.jobId && <><span>Job</span><code>{streamTest.jobId}</code></>}</div>
            </>}
          </div>
        </div>
        <div className="gateway-examples">
          <div className="examples-head"><strong>当前请求示例</strong><button className="inline-copy" onClick={() => copy(exampleTab, examples[exampleTab])} title="复制当前示例"><Copy size={14} /></button></div>
          <div className="example-tabs">{[["powershell", "PowerShell"], ["curl", "curl"], ["python", "Python"], ["javascript", "JavaScript"], ["stream", "SSE 流式"]].map(([id, label]) => <button className={exampleTab === id ? "selected" : ""} onClick={() => setExampleTab(id)} key={id}>{label}</button>)}</div>
          <pre>{examples[exampleTab]}</pre>
        </div>
      </div>}
    </section>
  );
}

function formatBytes(bytes: number) {
  if (bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes < 1024 * 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
  return `${(bytes / 1024 / 1024 / 1024 / 1024).toFixed(2)} TB`;
}

type HistoryFilter =
  | { kind: "all" }
  | { kind: "today" }
  | { kind: "yesterday" }
  | { kind: "recent"; days: 7 }
  | { kind: "day"; date: string };

function localDateKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function dateFromKey(key: string) {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(year, month - 1, day, 12);
}

function shiftedDateKey(days: number) {
  const date = new Date();
  date.setHours(12, 0, 0, 0);
  date.setDate(date.getDate() + days);
  return localDateKey(date);
}

function jobDateKey(job: Job) {
  return job.created_date || localDateKey(new Date(job.created_at));
}

function historyFilterLabel(filter: HistoryFilter) {
  if (filter.kind === "today") return "今天";
  if (filter.kind === "yesterday") return "昨天";
  if (filter.kind === "recent") return "最近 7 天";
  if (filter.kind === "day") {
    return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric" }).format(dateFromKey(filter.date));
  }
  return "全部日期";
}

function HistoryDateMenu({ filter, onChange }: { filter: HistoryFilter; onChange: (filter: HistoryFilter) => void }) {
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(() => {
    const source = filter.kind === "day" ? dateFromKey(filter.date) : new Date();
    return new Date(source.getFullYear(), source.getMonth(), 1, 12);
  });
  const containerRef = useRef<HTMLDivElement>(null);
  const todayKey = localDateKey(new Date());
  const selectedKey = filter.kind === "day" ? filter.date : "";
  const firstDay = new Date(month.getFullYear(), month.getMonth(), 1, 12);
  const mondayOffset = (firstDay.getDay() + 6) % 7;
  const calendarDays = Array.from({ length: 42 }, (_, index) => {
    const date = new Date(month.getFullYear(), month.getMonth(), 1 - mondayOffset + index, 12);
    return date;
  });

  useEffect(() => {
    if (!open) return;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const choose = (next: HistoryFilter) => {
    onChange(next);
    setOpen(false);
  };
  const toggle = () => {
    if (!open) {
      const source = filter.kind === "day" ? dateFromKey(filter.date) : new Date();
      setMonth(new Date(source.getFullYear(), source.getMonth(), 1, 12));
    }
    setOpen((current) => !current);
  };
  const presetSelected = (kind: HistoryFilter["kind"]) => filter.kind === kind;

  return (
    <div className="history-date-menu" ref={containerRef}>
      <button className={filter.kind === "all" ? "history-date-trigger" : "history-date-trigger active"} type="button" onClick={toggle} aria-haspopup="dialog" aria-expanded={open}>
        <CalendarDays size={18} />
        <span>{historyFilterLabel(filter)}</span>
        <ChevronDown size={16} />
      </button>
      {open && (
        <div className="history-calendar-popover" role="dialog" aria-label="筛选任务日期">
          <div className="history-date-presets">
            {([
              ["all", "全部日期"],
              ["today", "今天"],
              ["yesterday", "昨天"],
              ["recent", "最近 7 天"],
            ] as const).map(([kind, label]) => (
              <button className={presetSelected(kind) ? "selected" : ""} type="button" onClick={() => choose(kind === "recent" ? { kind, days: 7 } : { kind })} key={kind}>
                <span>{label}</span>
                {presetSelected(kind) && <Check size={15} />}
              </button>
            ))}
          </div>
          <div className="history-calendar">
            <div className="history-calendar-head">
              <strong>{new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long" }).format(month)}</strong>
              <div>
                <button type="button" onClick={() => setMonth((current) => new Date(current.getFullYear(), current.getMonth() - 1, 1, 12))} title="上个月" aria-label="上个月"><ChevronLeft size={18} /></button>
                <button type="button" onClick={() => setMonth((current) => new Date(current.getFullYear(), current.getMonth() + 1, 1, 12))} title="下个月" aria-label="下个月"><ChevronRight size={18} /></button>
              </div>
            </div>
            <div className="history-calendar-weekdays" aria-hidden="true">
              {["一", "二", "三", "四", "五", "六", "日"].map((day) => <span key={day}>{day}</span>)}
            </div>
            <div className="history-calendar-days">
              {calendarDays.map((date) => {
                const key = localDateKey(date);
                const classes = [
                  date.getMonth() !== month.getMonth() ? "outside" : "",
                  key === todayKey ? "today" : "",
                  key === selectedKey ? "selected" : "",
                ].filter(Boolean).join(" ");
                return <button className={classes} type="button" onClick={() => choose({ kind: "day", date: key })} aria-label={key} aria-pressed={key === selectedKey} key={key}>{date.getDate()}</button>;
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function matchesHistoryFilter(job: Job, filter: HistoryFilter) {
  const key = jobDateKey(job);
  if (filter.kind === "today") return key === shiftedDateKey(0);
  if (filter.kind === "yesterday") return key === shiftedDateKey(-1);
  if (filter.kind === "recent") return key >= shiftedDateKey(-(filter.days - 1)) && key <= shiftedDateKey(0);
  if (filter.kind === "day") return key === filter.date;
  return true;
}

function historyGroupLabel(key: string) {
  if (key === shiftedDateKey(0)) return "今天";
  if (key === shiftedDateKey(-1)) return "昨天";
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric" }).format(dateFromKey(key));
}

function History({ jobs, voices, onRefresh }: { jobs: Job[]; voices: Voice[]; onRefresh: () => Promise<void> }) {
  const [dateFilter, setDateFilter] = useState<HistoryFilter>({ kind: "all" });
  const [batchMode, setBatchMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");
  const voiceNames = useMemo(
    () => new Map(voices.map((voice) => [voice.public_name, voice.display_name])),
    [voices],
  );
  const filtered = useMemo(() => jobs.filter((job) => matchesHistoryFilter(job, dateFilter)), [jobs, dateFilter]);
  const groups = useMemo(() => {
    const grouped = new Map<string, Job[]>();
    filtered.forEach((job) => {
      const key = jobDateKey(job);
      grouped.set(key, [...(grouped.get(key) || []), job]);
    });
    return [...grouped.entries()].sort(([left], [right]) => right.localeCompare(left));
  }, [filtered]);
  const visibleIds = filtered.map((job) => job.id);
  const selectedJobs = filtered.filter((job) => selectedIds.has(job.id));
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));

  useEffect(() => {
    setSelectedIds((current) => new Set([...current].filter((id) => jobs.some((job) => job.id === id))));
  }, [jobs]);

  const changeFilter = (next: HistoryFilter) => {
    setDateFilter(next);
    setSelectedIds(new Set());
    setMessage("");
  };
  const toggleBatchMode = () => {
    setBatchMode((current) => {
      if (current) setSelectedIds(new Set());
      return !current;
    });
    setMessage("");
  };
  const toggleAll = () => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allVisibleSelected) visibleIds.forEach((id) => next.delete(id));
      else visibleIds.forEach((id) => next.add(id));
      return next;
    });
  };
  const toggleJob = (id: string) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const downloadZip = async () => {
    const exportIds = selectedJobs.map((job) => job.id);
    if (!exportIds.length) return setMessage("请先选择要导出的任务");
    setWorking(true);
    setMessage("正在整理 ZIP 文件...");
    try {
      const response = await fetch("/api/jobs/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_ids: exportIds }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "voice-studio-selected-jobs.zip";
      anchor.click();
      URL.revokeObjectURL(url);
      setMessage("ZIP 已开始下载");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "导出失败");
    } finally {
      setWorking(false);
    }
  };
  const deleteSelected = async () => {
    const ids = selectedJobs.map((job) => job.id);
    if (!ids.length) return setMessage("请先选择要删除的任务");
    if (!window.confirm(`确定删除选中的 ${ids.length} 条任务及对应音频吗？此操作不可撤销。`)) return;
    setWorking(true);
    try {
      const result = await api<{ message: string; freed_bytes: number }>("/api/jobs/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_ids: ids }),
      });
      setSelectedIds(new Set());
      setBatchMode(false);
      setMessage(`${result.message}，释放 ${formatBytes(result.freed_bytes)}`);
      await onRefresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "删除失败");
    } finally {
      setWorking(false);
    }
  };
  const deleteOne = async (job: Job) => {
    if (!window.confirm(`确定删除这条任务及对应音频吗？此操作不可撤销。`)) return;
    setWorking(true);
    try {
      const result = await api<{ message: string; freed_bytes: number }>(`/api/jobs/${job.id}`, { method: "DELETE" });
      setSelectedIds((current) => new Set([...current].filter((id) => id !== job.id)));
      setMessage(`${result.message}，释放 ${formatBytes(result.freed_bytes)}`);
      await onRefresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "删除失败");
    } finally {
      setWorking(false);
    }
  };
  const refresh = async () => {
    setWorking(true);
    try {
      await onRefresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "刷新失败");
    } finally {
      setWorking(false);
    }
  };

  return (
    <section className="page-section history-page">
      <WorkspaceHero
        title="每一次生成"
        accent="都留下可追溯的声音。"
        description="按日期浏览生成任务，试听、下载文字记录与音频，或批量整理历史文件。"
      />
      <div className="history-command-bar">
        <HistoryDateMenu filter={dateFilter} onChange={changeFilter} />
        <div className="history-command-actions">
          <button className={batchMode ? "secondary-button active" : "secondary-button"} type="button" onClick={toggleBatchMode}>
            <ListChecks size={17} />
            {batchMode ? "退出批量管理" : "批量管理"}
          </button>
          <button className={working ? "icon-button history-refresh working" : "icon-button history-refresh"} type="button" onClick={() => void refresh()} disabled={working} title="刷新任务历史" aria-label="刷新任务历史"><RefreshCw size={18} /></button>
        </div>
      </div>
      {batchMode && (
        <div className="history-selection-bar">
          <div className="history-selection-summary">
            <span>已选择 <strong>{selectedJobs.length}</strong> 条</span>
            <button className="inline-action" type="button" onClick={toggleAll} disabled={!visibleIds.length}>{allVisibleSelected ? "取消全选" : "全选"}</button>
          </div>
          <div className="history-selection-actions">
            <button className="secondary-button" type="button" onClick={() => void downloadZip()} disabled={working || !selectedJobs.length}><Download size={16} />下载 ZIP</button>
            <button className="danger-button" type="button" onClick={() => void deleteSelected()} disabled={working || !selectedJobs.length}><Trash2 size={16} />删除</button>
          </div>
        </div>
      )}
      {message && <div className="history-message"><Activity size={14} />{message}</div>}
      {groups.length === 0 ? (
        <div className="empty-state history-empty"><Clock3 size={22} /><span>{dateFilter.kind === "all" ? "还没有任务，去语音合成生成第一条语音。" : "这个日期范围内没有任务记录。"}</span></div>
      ) : (
        <div className="history-groups">
          {groups.map(([date, dateJobs]) => (
            <section className="history-date-group" key={date}>
              <h2>{historyGroupLabel(date)}</h2>
              <div className="history-list">
                {dateJobs.map((job) => {
                  const voiceName = voiceNames.get(job.voice) || job.voice;
                  return <article className={batchMode ? `history-row batch-selecting${selectedIds.has(job.id) ? " selected" : ""}` : "history-row"} key={job.id}>
                    {batchMode && <label className="history-checkbox"><input type="checkbox" checked={selectedIds.has(job.id)} onChange={() => toggleJob(job.id)} aria-label={`选择任务 ${job.id}`} /></label>}
                    <HistoryAudioButton src={job.audio_url} label="播放这条语音" />
                    <div className="history-main">
                      <strong title={job.input_text || `${voiceName} · ${job.model}`}>{job.input_text || `${voiceName} · ${job.model}`}</strong>
                      <span>{voiceName} · {job.model}</span>
                      {job.input_text && <details className="history-record"><summary>查看文字记录</summary><p>{job.input_text}</p></details>}
                    </div>
                    {!batchMode && <div className="history-actions">
                      <a className={job.text_url ? "history-action" : "history-action disabled"} href={job.text_url || undefined} title={job.text_url ? "下载文字记录" : "没有可下载的文字记录"} aria-label="下载文字记录"><FileText size={16} /></a>
                      <a className={job.audio_url ? "history-action" : "history-action disabled"} href={job.audio_url || undefined} title={job.audio_url ? "下载声音文件" : "声音文件不可用"} aria-label="下载声音文件"><Download size={16} /></a>
                      <button className="history-action danger-action" onClick={() => void deleteOne(job)} title="删除任务" aria-label="删除任务"><Trash2 size={16} /></button>
                    </div>}
                  </article>;
                })}
              </div>
            </section>
          ))}
        </div>
      )}
    </section>
  );
}

function Settings({ models, onJobsChanged }: { models: Model[]; onJobsChanged: () => Promise<void> }) {
  const [section, setSection] = useState<"providers" | "storage" | "environment">("providers");
  return (
    <section className="page-section settings-shell">
      <WorkspaceHero
        title="把每个厂商"
        accent="放进同一个工作台。"
        description="统一管理厂商凭据、生成文件存储策略和本机运行环境。"
      />
      <div className="settings-navigation" role="tablist" aria-label="设置分类">
        <button className={section === "providers" ? "selected" : ""} type="button" role="tab" aria-selected={section === "providers"} onClick={() => setSection("providers")}><KeyRound size={18} />厂商账号</button>
        <button className={section === "storage" ? "selected" : ""} type="button" role="tab" aria-selected={section === "storage"} onClick={() => setSection("storage")}><HardDrive size={18} />存储与清理</button>
        <button className={section === "environment" ? "selected" : ""} type="button" role="tab" aria-selected={section === "environment"} onClick={() => setSection("environment")}><ShieldCheck size={18} />运行环境</button>
      </div>
      {section === "providers" && <ProviderSettings models={models} />}
      {section === "storage" && <StorageSettings onJobsChanged={onJobsChanged} />}
      {section === "environment" && <EnvironmentSettings />}
    </section>
  );
}

function EnvironmentSettings() {
  const [diagnostics, setDiagnostics] = useState<SystemDiagnostics | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      setDiagnostics(await api<SystemDiagnostics>("/api/system/diagnostics"));
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "无法读取环境诊断");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { void load(); }, []);

  if (loading && !diagnostics) {
    return <div className="environment-loading"><RefreshCw size={18} className="spinning" />正在检查运行环境...</div>;
  }
  return (
    <div className="environment-settings-page">
      <div className="environment-heading">
        <div>
          <h2>运行环境</h2>
          <p>检查语音生成、音频转换和凭据保存所需的本机组件。</p>
        </div>
        <button className="secondary-button" type="button" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={16} className={loading ? "spinning" : ""} />重新检查
        </button>
      </div>
      {diagnostics && <>
        <div className={"environment-summary " + diagnostics.status}>
          <span className="environment-summary-icon">
            {diagnostics.status === "error" ? <X size={21} /> : diagnostics.status === "warning" ? <CircleHelp size={21} /> : <Check size={21} />}
          </span>
          <div>
            <strong>{diagnostics.status === "error" ? `${diagnostics.required_failures} 项需要处理` : diagnostics.status === "warning" ? "核心环境可用" : "运行环境正常"}</strong>
            <span>{diagnostics.base_url} · {diagnostics.platform} 本地服务</span>
          </div>
        </div>
        <div className="environment-checks">
          {diagnostics.checks.map((item) => (
            <div className="environment-check-row" key={item.id}>
              <span className={"environment-check-state " + item.status}>
                {item.status === "ok" ? <Check size={16} /> : item.status === "warning" ? <CircleHelp size={16} /> : <X size={16} />}
              </span>
              <div className="environment-check-main"><strong>{item.label}</strong><span>{item.detail}</span></div>
              <code>{item.version || (item.status === "warning" ? "可选" : "未通过")}</code>
            </div>
          ))}
        </div>
      </>}
      {message && <div className="environment-message"><Activity size={15} />{message}</div>}
    </div>
  );
}

type StoragePolicyDraft = {
  automatic_enabled: boolean;
  retention_days: number;
  capacity_gb: number;
  interval: "daily" | "weekly";
  cleanup_scope: "audio_only" | "jobs";
};

const GIBIBYTE = 1024 * 1024 * 1024;

function storageDraft(policy: StoragePolicy): StoragePolicyDraft {
  return {
    automatic_enabled: policy.automatic_enabled,
    retention_days: policy.retention_days,
    capacity_gb: Number((policy.capacity_limit_bytes / GIBIBYTE).toFixed(2)),
    interval: policy.interval,
    cleanup_scope: policy.cleanup_scope,
  };
}

function StorageSettings({ onJobsChanged }: { onJobsChanged: () => Promise<void> }) {
  const [status, setStatus] = useState<StorageStatus | null>(null);
  const [draft, setDraft] = useState<StoragePolicyDraft | null>(null);
  const [preview, setPreview] = useState<CleanupPreview | null>(null);
  const [working, setWorking] = useState<"" | "loading" | "saving" | "preview" | "cleanup" | "directory">("loading");
  const [message, setMessage] = useState("");

  const load = async () => {
    setWorking("loading");
    try {
      const next = await api<StorageStatus>("/api/storage");
      setStatus(next);
      setDraft(storageDraft(next.policy));
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "无法读取存储状态");
    } finally {
      setWorking("");
    }
  };
  useEffect(() => { void load(); }, []);

  const dirty = Boolean(status && draft && (
    draft.automatic_enabled !== status.policy.automatic_enabled ||
    draft.retention_days !== status.policy.retention_days ||
    Math.round(draft.capacity_gb * GIBIBYTE) !== status.policy.capacity_limit_bytes ||
    draft.interval !== status.policy.interval ||
    draft.cleanup_scope !== status.policy.cleanup_scope
  ));

  const persistDraft = async (showMessage = true) => {
    if (!draft) throw new Error("存储策略尚未加载");
    if (!Number.isFinite(draft.retention_days) || draft.retention_days < 1) throw new Error("自动保留天数不能少于 1 天");
    if (!Number.isFinite(draft.capacity_gb) || draft.capacity_gb < 0.1) throw new Error("容量上限不能少于 0.1 GB");
    const next = await api<StorageStatus>("/api/storage/policy", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        automatic_enabled: draft.automatic_enabled,
        retention_days: Math.round(draft.retention_days),
        capacity_limit_bytes: Math.round(draft.capacity_gb * GIBIBYTE),
        interval: draft.interval,
        cleanup_scope: draft.cleanup_scope,
      }),
    });
    setStatus(next);
    setDraft(storageDraft(next.policy));
    if (showMessage) setMessage("存储策略已保存");
    return next;
  };

  const save = async () => {
    setWorking("saving");
    setMessage("");
    try {
      await persistDraft();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败");
    } finally {
      setWorking("");
    }
  };

  const showCleanupPreview = async () => {
    setWorking("preview");
    setMessage("");
    try {
      if (dirty) await persistDraft(false);
      setPreview(await api<CleanupPreview>("/api/storage/cleanup/preview", { method: "POST" }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "无法计算清理范围");
    } finally {
      setWorking("");
    }
  };

  const cleanNow = async () => {
    setWorking("cleanup");
    try {
      const response = await api<{ result: CleanupRun; storage: StorageStatus }>("/api/storage/cleanup", { method: "POST" });
      setStatus(response.storage);
      setDraft(storageDraft(response.storage.policy));
      setPreview(null);
      setMessage(response.result.files_removed || response.result.jobs_removed
        ? `${response.result.message}，释放 ${formatBytes(response.result.bytes_freed)}`
        : response.result.message);
      await onJobsChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "清理失败");
    } finally {
      setWorking("");
    }
  };

  const openDirectory = async () => {
    setWorking("directory");
    try {
      const result = await api<{ opened: boolean; path: string; message?: string }>("/api/storage/open-directory", { method: "POST" });
      setMessage(result.opened ? "已打开音频存储目录" : `${result.message || "请手动打开音频存储目录"} 路径：${result.path}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "无法打开存储目录");
    } finally {
      setWorking("");
    }
  };

  if (!status || !draft) {
    return <div className="storage-loading"><RefreshCw className={working === "loading" ? "spinning" : ""} size={20} /><span>{message || "正在读取存储状态..."}</span>{message && <button className="secondary-button" type="button" onClick={() => void load()}>重试</button>}</div>;
  }

  const usagePercent = Math.min(100, Math.max(0, status.usage.capacity_ratio * 100));
  const latest = status.cleanup_history[0];
  return (
    <div className="storage-settings-page">
      <header className="storage-heading">
        <div><h2>生成文件存储</h2><p>控制任务音频的保留时间和磁盘占用。音色库、API 凭据与语音克隆素材不会被自动清理。</p></div>
        <button className="secondary-button" type="button" onClick={() => void openDirectory()} disabled={Boolean(working)}><FolderOpen size={17} />打开目录</button>
      </header>

      <section className="storage-overview" aria-label="存储空间概览">
        <div className="storage-usage-head">
          <div className="storage-usage-title"><HardDrive size={22} /><span>当前占用</span></div>
          <strong>{formatBytes(status.usage.audio_bytes)} <span>/ {formatBytes(status.policy.capacity_limit_bytes)}</span></strong>
        </div>
        <div className="storage-progress" aria-label={`已使用 ${usagePercent.toFixed(0)}%`}><span style={{ width: `${usagePercent}%` }} /></div>
        <div className="storage-stats">
          <div><strong>{status.usage.audio_count}</strong><span>个音频</span></div>
          <div><strong>{status.usage.job_count}</strong><span>条任务记录</span></div>
          <div><strong>{status.usage.oldest_audio_at ? new Date(status.usage.oldest_audio_at).toLocaleDateString() : "--"}</strong><span>最早音频</span></div>
        </div>
      </section>

      <section className="storage-policy-section">
        <div className="storage-policy-row storage-policy-master">
          <div><strong>自动清理</strong><span>{draft.automatic_enabled ? (status.cleanup_history.some((run) => run.trigger === "automatic") && status.next_cleanup_at ? `下次检查 ${new Date(status.next_cleanup_at).toLocaleString()}` : "等待首次自动检查") : "关闭后仍可使用立即清理"}</span></div>
          <button className={draft.automatic_enabled ? "toggle-switch active" : "toggle-switch"} type="button" role="switch" aria-checked={draft.automatic_enabled} onClick={() => setDraft({ ...draft, automatic_enabled: !draft.automatic_enabled })}><span /></button>
        </div>

        <div className="storage-policy-grid">
          <div className="storage-setting-block">
            <label htmlFor="retention-days">自动保留天数</label>
            <div className="number-with-unit"><input id="retention-days" type="number" min="1" max="3650" value={draft.retention_days} onChange={(event) => setDraft({ ...draft, retention_days: Number(event.target.value) })} /><span>天</span></div>
            <p>超过保留时间的音频会进入清理范围。</p>
          </div>
          <div className="storage-setting-block">
            <label htmlFor="capacity-limit">容量上限</label>
            <div className="number-with-unit"><input id="capacity-limit" type="number" min="0.1" max="10240" step="0.1" value={draft.capacity_gb} onChange={(event) => setDraft({ ...draft, capacity_gb: Number(event.target.value) })} /><span>GB</span></div>
            <p>超出上限后优先清理最旧的音频。</p>
          </div>
          <div className="storage-setting-block">
            <label>检查频率</label>
            <div className="storage-segmented"><button className={draft.interval === "daily" ? "selected" : ""} type="button" onClick={() => setDraft({ ...draft, interval: "daily" })}>每天</button><button className={draft.interval === "weekly" ? "selected" : ""} type="button" onClick={() => setDraft({ ...draft, interval: "weekly" })}>每周</button></div>
            <p>程序启动时也会检查是否到期。</p>
          </div>
          <div className="storage-setting-block">
            <label>清理范围</label>
            <div className="storage-segmented storage-scope"><button className={draft.cleanup_scope === "audio_only" ? "selected" : ""} type="button" onClick={() => setDraft({ ...draft, cleanup_scope: "audio_only" })}>只清理音频</button><button className={draft.cleanup_scope === "jobs" ? "selected danger" : ""} type="button" onClick={() => setDraft({ ...draft, cleanup_scope: "jobs" })}>音频和任务记录</button></div>
            <p>{draft.cleanup_scope === "audio_only" ? "文字和生成参数会继续保留。" : "到期任务将从任务历史中永久删除。"}</p>
          </div>
        </div>
      </section>

      {draft.cleanup_scope === "jobs" && <div className="storage-danger-note"><ShieldCheck size={18} /><span>当前策略会永久删除任务记录。建议先使用批量导出备份重要内容。</span></div>}
      {message && <div className="form-message storage-message"><Activity size={15} />{message}</div>}

      <div className="storage-actions">
        <div>{latest ? <>最近清理：{new Date(latest.completed_at).toLocaleString()} · 释放 {formatBytes(latest.bytes_freed)}</> : "尚未执行过清理"}</div>
        <button className="secondary-button" type="button" onClick={() => void showCleanupPreview()} disabled={Boolean(working)}><Trash2 size={17} />{working === "preview" ? "正在计算..." : "立即清理"}</button>
        <button className="primary-button compact" type="button" onClick={() => void save()} disabled={Boolean(working) || !dirty}><Save size={17} />{working === "saving" ? "保存中..." : "保存设置"}</button>
      </div>

      <section className="cleanup-history-section">
        <div className="cleanup-history-heading"><h3>清理记录</h3><button className="icon-button" type="button" onClick={() => void load()} disabled={Boolean(working)} title="刷新存储状态" aria-label="刷新存储状态"><RefreshCw size={17} /></button></div>
        {status.cleanup_history.length ? <div className="cleanup-history-list">{status.cleanup_history.map((run) => <div className="cleanup-history-row" key={run.id}><span>{new Date(run.completed_at).toLocaleString()}</span><strong>{run.trigger === "automatic" ? "自动清理" : "手动清理"}</strong><span>{run.files_removed} 个音频</span><span>{formatBytes(run.bytes_freed)}</span><span className={run.status === "completed" ? "cleanup-success" : "cleanup-partial"}>{run.status === "completed" ? "完成" : "部分失败"}</span></div>)}</div> : <div className="cleanup-history-empty">清理执行后，结果会记录在这里。</div>}
      </section>

      {preview && <div className="storage-modal-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target && working !== "cleanup") setPreview(null); }}><div className="storage-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="cleanup-confirm-title"><div className="storage-confirm-icon"><Trash2 size={22} /></div><h3 id="cleanup-confirm-title">确认本次清理</h3><div className="storage-preview-metrics"><div><span>音频文件</span><strong>{preview.file_count} 个</strong></div><div><span>预计释放</span><strong>{formatBytes(preview.bytes_to_free)}</strong></div><div><span>{preview.cleanup_scope === "jobs" ? "删除记录" : "保留记录"}</span><strong>{preview.cleanup_scope === "jobs" ? `${preview.job_count} 条` : `${preview.jobs_preserved} 条`}</strong></div></div><p>{preview.file_count || preview.job_count ? (preview.cleanup_scope === "jobs" ? "音频和对应任务记录将永久删除，此操作无法撤销。" : "音频清理后无法恢复，文字记录和生成参数会继续保留。") : "当前没有符合存储策略的文件。"}</p><div className="storage-confirm-actions"><button className="secondary-button" type="button" onClick={() => setPreview(null)} disabled={working === "cleanup"}>取消</button><button className={preview.cleanup_scope === "jobs" ? "danger-button" : "primary-button compact"} type="button" onClick={() => void cleanNow()} disabled={working === "cleanup" || (!preview.file_count && !preview.job_count)}>{working === "cleanup" ? "正在清理..." : "确认清理"}</button></div></div></div>}
    </div>
  );
}

function ProviderSettings({ models }: { models: Model[] }) {
  const [specs, setSpecs] = useState<Record<string, ProviderSpec>>({});
  const [accounts, setAccounts] = useState<ProviderAccount[]>([]);
  const [provider, setProvider] = useState("dashscope");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showKey, setShowKey] = useState(false);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");
  const [form, setForm] = useState({
    display_name: "",
    api_key: "",
    endpoint: "",
    openapi_access_key: "",
    openapi_secret_key: "",
    project_name: "",
  });
  const spec = specs[provider];

  const loadAccounts = () =>
    api<ProviderAccount[]>("/api/provider-accounts").then(setAccounts);
  useEffect(() => {
    Promise.all([
      api<Record<string, ProviderSpec>>("/api/provider-specs"),
      api<ProviderAccount[]>("/api/provider-accounts"),
    ])
      .then(([nextSpecs, nextAccounts]) => {
        setSpecs(nextSpecs);
        setAccounts(nextAccounts);
      })
      .catch(() => setMessage("无法读取厂商配置"));
  }, []);
  useEffect(() => {
    if (!spec) return;
    const account = accounts.find((item) => item.provider === provider);
    setEditingId(account?.id || null);
    setForm({
      display_name: account?.display_name || spec.display_name + " 默认账号",
      api_key: "",
      endpoint: account?.endpoint || spec.default_endpoint,
      openapi_access_key: "",
      openapi_secret_key: "",
      project_name: account?.project_name || "",
    });
    setShowKey(false);
  }, [provider, accounts, spec]);

  const chooseAccount = (account?: ProviderAccount) => {
    setEditingId(account?.id || null);
    setForm({
      display_name:
        account?.display_name || (spec?.display_name || "") + " 新账号",
      api_key: "",
      endpoint: account?.endpoint || spec?.default_endpoint || "",
      openapi_access_key: "",
      openapi_secret_key: "",
      project_name: "",
    });
    setMessage("");
  };
  const save = async () => {
    if (!form.display_name.trim() || (!editingId && !form.api_key.trim())) {
      setMessage("请填写账号名称和 API Key");
      return;
    }
    setWorking(true);
    setMessage("");
    try {
      const url = editingId
        ? "/api/provider-accounts/" + editingId
        : "/api/provider-accounts";
      const method = editingId ? "PUT" : "POST";
      const saved = await api<ProviderAccount>(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider,
          ...form,
          api_key: form.api_key || null,
        }),
      });
      await loadAccounts();
      setEditingId(saved.id);
      setForm((current) => ({ ...current, api_key: "" }));
      setMessage("凭据已写入系统密钥环");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败");
    } finally {
      setWorking(false);
    }
  };
  const verify = async () => {
    if (!editingId) return;
    setWorking(true);
    setMessage("正在检查凭据...");
    try {
      const checked = await api<ProviderAccount>(
        "/api/provider-accounts/" + editingId + "/test",
        { method: "POST" },
      );
      await loadAccounts();
      setMessage(checked.verification_message || "检查完成");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "检查失败");
    } finally {
      setWorking(false);
    }
  };
  const remove = async () => {
    if (
      !editingId ||
      !window.confirm("删除这个账号及其系统密钥环中的凭据？")
    )
      return;
    setWorking(true);
    try {
      await api("/api/provider-accounts/" + editingId, { method: "DELETE" });
      await loadAccounts();
      setMessage("账号与本机凭据已删除");
    } catch {
      setMessage("删除失败");
    } finally {
      setWorking(false);
    }
  };
  const providerAccounts = accounts.filter(
    (item) => item.provider === provider,
  );
  const current = accounts.find((item) => item.id === editingId);

  return (
    <div className="settings-page">
      <div>
        <h2>厂商账号与 API 凭据</h2>
        <p className="settings-lead">
          API Key 直接写入系统密钥环。页面和 SQLite
          只保存脱敏后缀与 Endpoint，不会回显完整密钥。
        </p>
      </div>
      <div className="credential-layout">
        <div className="provider-rail">
          <ProviderSelector
            className="settings-provider-selector"
            label="厂商账号"
            value={provider}
            onChange={setProvider}
            options={credentialProviderIds.map((id) => {
              const count = accounts.filter((item) => item.provider === id).length;
              const active = accounts.some((item) => item.provider === id && item.status === "active");
              return {
                id,
                label: providerMeta[id].label,
                mark: providerMeta[id].mark,
                tone: providerMeta[id].tone,
                detail: `${models.filter((item) => item.provider === id).length} 个模型 · ${count ? `${count} 个账号` : "未配置"}`,
                indicator: active ? "active" as const : count ? "saved" as const : "idle" as const,
              };
            })}
          />
          <div className="security-note">
            <ShieldCheck size={16} />
            <span>
              密钥由当前系统用户的密钥环加密保存，其他系统账号无法直接读取。
            </span>
          </div>
        </div>
        <div className="credential-editor">
          <div className="editor-title">
            <div>
              <h3>{spec?.display_name || provider}</h3>
            </div>
            <div className="credential-status">
              {current ? (
                <>
                  <span className={"status-chip " + current.status}>
                    {current.status === "active"
                      ? "已鉴权"
                      : current.status === "error"
                        ? "检查失败"
                        : "已保存"}
                  </span>
                  <code>{current.secret_hint}</code>
                </>
              ) : (
                <span className="status-chip empty">尚未配置</span>
              )}
            </div>
          </div>
          {providerAccounts.length > 0 && (
            <div className="account-switcher">
              {providerAccounts.map((account) => (
                <button
                  className={editingId === account.id ? "selected" : ""}
                  onClick={() => chooseAccount(account)}
                  key={account.id}
                >
                  {account.display_name}
                </button>
              ))}
              <button
                className={!editingId ? "selected add" : "add"}
                onClick={() => chooseAccount()}
              >
                <Plus size={13} />
                新账号
              </button>
            </div>
          )}
          <div className="credential-form">
            <div className="field full">
              <label>配置名称</label>
              <input
                value={form.display_name}
                onChange={(event) =>
                  setForm({ ...form, display_name: event.target.value })
                }
                placeholder="例如：个人账号"
              />
            </div>
            <div className="field full">
              <label>Endpoint</label>
              <input
                value={form.endpoint}
                onChange={(event) =>
                  setForm({ ...form, endpoint: event.target.value })
                }
                placeholder={spec?.default_endpoint}
              />
              <small>{spec?.endpoint_note}，通常无需修改。</small>
            </div>
            <div className="field full">
              <label>{spec?.secret_label || "API Key"}</label>
              <div className="secret-input">
                <input
                  type={showKey ? "text" : "password"}
                  value={form.api_key}
                  onChange={(event) =>
                    setForm({ ...form, api_key: event.target.value })
                  }
                  autoComplete="new-password"
                  placeholder={
                    current
                      ? "留空则继续使用 " + current.secret_hint
                      : "粘贴后将直接写入系统密钥环"
                  }
                />
                <button
                  onClick={() => setShowKey(!showKey)}
                  title={showKey ? "隐藏密钥" : "显示密钥"}
                >
                  {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {provider === "dashscope" && (
                <small>
                  语音模型需要标准 sk- Key；sk-sp- Token Plan Key 不支持 TTS。
                </small>
              )}
            </div>
            {provider === "volcengine" && (
              <>
                <div className="field full">
                  <label>OpenAPI Access Key ID（IAM AK）</label>
                  <input
                    value={form.openapi_access_key}
                    onChange={(event) => setForm({ ...form, openapi_access_key: event.target.value })}
                    placeholder={current?.openapi_access_key_hint ? "留空则继续使用 " + current.openapi_access_key_hint : "填写 IAM 中生成的 Access Key ID，不是 Access Token"}
                    autoComplete="off"
                  />
                </div>
                <div className="field full">
                  <label>OpenAPI Secret Access Key（IAM SK）</label>
                  <div className="secret-input">
                    <input
                      type={showKey ? "text" : "password"}
                      value={form.openapi_secret_key}
                      onChange={(event) => setForm({ ...form, openapi_secret_key: event.target.value })}
                      placeholder={current?.has_openapi_secret ? "留空则继续使用已保存的 Secret" : "填写 IAM 中生成的 Secret Access Key"}
                      autoComplete="new-password"
                    />
                  </div>
                </div>
                <div className="field full">
                  <label>项目名称（ProjectName）</label>
                  <input
                    value={form.project_name}
                    onChange={(event) => setForm({ ...form, project_name: event.target.value })}
                    placeholder="例如：default"
                  />
                  <small>批量同步接口按项目查询音色；填写声音复刻项目名称。旧版控制台的 APP ID、Access Token、Secret Key 不属于这里的 OpenAPI AK/SK。</small>
                </div>
              </>
            )}
          </div>
          {current?.verification_message && (
            <div className={"verification-message " + current.status}>
              <Activity size={15} />
              <span>
                {current.verification_message}
                {current.last_verified_at && (
                  <small>
                    {new Date(current.last_verified_at).toLocaleString()}
                  </small>
                )}
              </span>
            </div>
          )}
          {message && <div className="form-message">{message}</div>}
          <div className="credential-actions">
            {editingId && (
              <button
                className="danger-button"
                onClick={remove}
                disabled={working}
                title="删除账号"
              >
                <Trash2 size={16} />
              </button>
            )}
            <div className="action-spacer" />
            <button
              className="secondary-button"
              onClick={verify}
              disabled={!editingId || working}
            >
              <Activity size={16} />
              {provider === "dashscope" ||
              provider === "mimo" ||
              provider === "volcengine" ||
              provider === "minimax"
                ? "验证鉴权"
                : "检查保存"}
            </button>
            <button
              className="primary-button compact"
              onClick={save}
              disabled={working}
            >
              <Save size={16} />
              {working ? "处理中..." : editingId ? "保存修改" : "保存账号"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
