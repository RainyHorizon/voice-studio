import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AudioLines,
  Check,
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
  Gauge,
  KeyRound,
  Library,
  Mic2,
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
const providerMeta: Record<
  string,
  { label: string; mark: string; tone: string }
> = {
  dashscope: { label: "通义千问", mark: "Q", tone: "gold" },
  volcengine: { label: "火山引擎", mark: "V", tone: "red" },
  minimax: { label: "MiniMax", mark: "M", tone: "mint" },
  mimo: { label: "小米 MiMo", mark: "米", tone: "blue" },
};
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
  const [voices, setVoices] = useState<Voice[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [text, setText] = useState(sample);
  const [model, setModel] = useState("mimo/mimo-v2.5-tts");
  const [voice, setVoice] = useState("mimo-default");
  const [speed, setSpeed] = useState(1);
  const [format, setFormat] = useState("wav");
  const [instructions, setInstructions] = useState("");
  const [audioUrl, setAudioUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [gateway, setGateway] = useState<Gateway | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const selectedModel = useMemo(
    () => models.find((item) => item.gateway_id === model),
    [models, model],
  );
  const selectedVoice = useMemo(
    () => voices.find((item) => item.public_name === voice),
    [voices, voice],
  );
  useEffect(() => {
    Promise.all([
      api<Voice[]>("/api/voices"),
      api<Model[]>("/api/models"),
      api<Job[]>("/api/jobs?limit=500"),
      api<Gateway>("/api/gateway"),
    ])
      .then(([v, m, j, g]) => {
        setVoices(v);
        setModels(m);
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
  const cloneVoice = async (config: CloneConfig) => {
    const file = fileRef.current?.files?.[0];
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
    setModel(created.voice.provider + "/" + created.voice.model_id);
    setVoice(created.voice.public_name);
    setNotice(created.message);
    return created.voice;
  };
  const nav = [
    { id: "synthesize", label: "合成工作台", icon: AudioLines },
    { id: "voices", label: "音色库", icon: Library },
    { id: "clone", label: "声音克隆", icon: Mic2 },
    { id: "design", label: "Voice Design", icon: WandSparkles },
    { id: "gateway", label: "API 网关", icon: Code2 },
    { id: "history", label: "任务历史", icon: Clock3 },
    { id: "settings", label: "设置", icon: Settings2 },
  ];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-orbit">
            <AudioLines size={18} />
          </div>
          <div>
            <strong>VOICE / STUDIO</strong>
            <span>local gateway</span>
          </div>
        </div>
        <div className="workspace-label">
          工作区 <span>LOCAL</span>
        </div>
        <nav>
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={active === item.id ? "nav-item active" : "nav-item"}
                onClick={() => setActive(item.id)}
                key={item.id}
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
        <div className="sidebar-foot">
          <div className="connection">
            <span className="live-dot" />
            <span>本地服务在线</span>
            <small>8765</small>
          </div>
          <div className="build">MVP 0.5.0 · Multi-provider</div>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <div>
            <div className="eyebrow">
              {nav.find((n) => n.id === active)?.label}
            </div>
            <h1>{titleFor(active)}</h1>
          </div>
          <div className="top-actions">
            <span className="service-pill">
              <span className="live-dot" />
              混合模式
            </span>
            <button className="icon-button" title="帮助">
              <CircleHelp size={18} />
            </button>
            <button className="avatar">你</button>
          </div>
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
          />
        )}
        {active === "clone" && (
          <ClonePanel fileRef={fileRef} models={models} onClone={cloneVoice} />
        )}
        {active === "design" && (
          <VoiceDesignPanel models={models} onDesign={designVoice} />
        )}
        {active === "gateway" && (
          <GatewayPanel gateway={gateway} models={models} voices={voices} />
        )}
        {active === "history" && <History jobs={jobs} onRefresh={refreshJobs} />}
        {active === "settings" && <Settings models={models} />}
      </main>
    </div>
  );
}

function titleFor(active: string) {
  return (
    {
      synthesize: "把文字变成可听见的质感",
      voices: "音色库",
      clone: "声音克隆",
      design: "Voice Design",
      gateway: "OpenAI 兼容网关",
      history: "任务历史",
      settings: "设置",
    } as Record<string, string>
  )[active];
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

  return (
    <section className="synthesis-layout">
      <div className="editor-column">
        <div className="section-heading">
          <div>
            <span className="section-kicker">01 / SCRIPT</span>
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
            <strong>
              {p.selectedModel?.mode === "provider" ? "真实 API" : "本地演示"}
            </strong>
          </div>
          <div>
            <span>输出</span>
            <strong>{p.format.toUpperCase()}</strong>
          </div>
        </div>
        {p.audioUrl && (
          <div className="player">
            <div className="player-icon">
              <Volume2 size={20} />
            </div>
            <div className="player-main">
              <div className="player-title">
                刚刚生成的音频{" "}
                <span>· {p.selectedVoice?.display_name || p.voice}</span>
              </div>
              <audio controls src={p.audioUrl} />
            </div>
            <a
              className="download-button"
              href={p.audioUrl}
              download={"voice-studio." + p.format}
              title="下载"
            >
              <Download size={17} />
            </a>
          </div>
        )}
        <div className="generate-row">
          <button
            className="primary-button"
            onClick={p.synthesize}
            disabled={p.busy || !selectedVoiceValue}
          >
            <Sparkles size={17} />
            {p.busy ? "生成中..." : "生成语音"}
            <span>CTRL ↵</span>
          </button>
          <span className="hint">生成前会校验模型与音色的作用域</span>
        </div>
      </div>
      <aside className="control-column">
        <div className="control-section">
          <div className="section-kicker">02 / VOICE</div>
          <label>厂商</label>
          <select
            value={selectedProvider}
            onChange={(e) => chooseProvider(e.target.value)}
          >
            {Object.keys(providerMeta)
              .filter((id) =>
                synthesisModels.some((item) => item.provider === id),
              )
              .map((id) => (
                <option value={id} key={id}>
                  {providerMeta[id].label}
                </option>
              ))}
          </select>
          <label>模型</label>
          <select value={p.model} onChange={(e) => p.setModel(e.target.value)}>
            {providerModels.map((item) => (
              <option value={item.gateway_id} key={item.gateway_id}>
                {item.display_name}
              </option>
            ))}
          </select>
          {p.selectedModel && (
            <div className="model-meta">
              <span
                className={
                  "provider-mark " +
                  providerMeta[p.selectedModel.provider]?.tone
                }
              >
                {providerMeta[p.selectedModel.provider]?.mark}
              </span>
              <div>
                <strong>{p.selectedModel.quality}质感</strong>
                <small>
                  {p.selectedModel.latency}响应 ·{" "}
                  {p.selectedModel.mode === "provider"
                    ? "真实厂商接口"
                    : "演示适配器"}
                </small>
              </div>
            </div>
          )}
          {(p.selectedModel?.model_id === "qwen3-tts-instruct-flash" ||
            p.selectedModel?.model_id === "seed-tts-2.0") && (
            <>
              <label>表达指令</label>
              <input
                value={p.instructions}
                onChange={(event) => p.setInstructions(event.target.value)}
                placeholder="例如：温暖、克制，结尾轻微上扬"
              />
            </>
          )}
          <label>音色</label>
          <select
            value={selectedVoiceValue}
            onChange={(e) => p.setVoice(e.target.value)}
            disabled={!compatibleVoices.length}
          >
            {!compatibleVoices.length && (
              <option value="">请先创建或导入兼容音色</option>
            )}
            {compatibleVoices.map((item) => (
              <option value={item.public_name} key={item.id}>
                {item.display_name} · {item.public_name}
              </option>
            ))}
          </select>
          <button
            className="inline-action"
            onClick={() => p.setActive("clone")}
          >
            <Plus size={15} />
            创建或克隆音色
          </button>
        </div>
        <div className="control-section bordered">
          <div className="section-kicker">03 / FEEL</div>
          <div className="range-label">
            <label>语速</label>
            <output>{p.speed.toFixed(1)}×</output>
          </div>
          <input
            type="range"
            min="0.5"
            max="2"
            step="0.1"
            value={p.speed}
            onChange={(e) => p.setSpeed(Number(e.target.value))}
          />
          <div className="range-scale">
            <span>慢</span>
            <span>自然</span>
            <span>快</span>
          </div>
          <label>输出格式</label>
          <div className="segmented">
            {["wav", "mp3"].map((item) => (
              <button
                className={p.format === item ? "selected" : ""}
                onClick={() => p.setFormat(item)}
                key={item}
              >
                {item.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
        <div className="control-note">
          <Gauge size={15} />
          <span>
            {p.selectedModel?.mode === "provider"
              ? "当前模型会调用已保存的厂商凭据，结果来自真实语音服务。"
              : "当前模型使用本地演示适配器，不会消耗厂商额度。"}
          </span>
        </div>
      </aside>
    </section>
  );
}

function VoiceLibrary({
  voices,
  models,
  onClone,
  onImport,
  onBatchImport,
  onRemove,
}: {
  voices: Voice[];
  models: Model[];
  onClone: () => void;
  onImport: (config: ImportVoiceConfig) => Promise<void>;
  onBatchImport: (configs: ImportVoiceConfig[]) => Promise<void>;
  onRemove: (voice: Voice) => Promise<void>;
}) {
  const [provider, setProvider] = useState("all");
  const [showImport, setShowImport] = useState(false);
  const filtered =
    provider === "all"
      ? voices
      : voices.filter((item) => item.provider === provider);
  const counts = Object.fromEntries(
    Object.keys(providerMeta).map((id) => [
      id,
      voices.filter((item) => item.provider === id).length,
    ]),
  );
  return (
    <section className="page-section voice-library">
      <div className="page-toolbar">
        <div>
          <span className="section-kicker">VOICE REGISTRY</span>
          <h2>预置音色与克隆音色</h2>
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
      <div className="voice-filters">
        <button
          className={provider === "all" ? "selected" : ""}
          onClick={() => setProvider("all")}
        >
          全部 <span>{voices.length}</span>
        </button>
        {Object.entries(providerMeta).map(([id, meta]) => (
          <button
            className={provider === id ? "selected" : ""}
            onClick={() => setProvider(id)}
            key={id}
          >
            <span className={"provider-dot " + meta.tone} />
            {meta.label}
            <span>{counts[id] || 0}</span>
          </button>
        ))}
      </div>
      <div className="voice-table">
        <div className="table-head">
          <span>音色</span>
          <span>厂商 / 模型</span>
          <span>类型</span>
          <span>语言</span>
          <span>状态</span>
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
                  <small>{item.public_name}</small>
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
              <span className="status">
                <span className="live-dot" />
                可用
              </span>
              <button
                className="icon-button delete-voice"
                title="从音色库移除"
                onClick={() => onRemove(item)}
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))
        ) : (
          <div className="empty-state">
            <Library size={21} />
            <span>这个厂商还没有可用音色</span>
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
    </section>
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
            <span className="section-kicker">REMOTE VOICE</span>
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
                {(mode === "sync" ? syncProviders : Object.keys(providerMeta))
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
  const promptLimit = 2000;
  const previewLimit = 2000;

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
    if (!selected || !prompt.trim() || !previewText.trim() || !displayName.trim() || !publicName.trim()) return;
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
          <span className="section-kicker">VOICE DESIGN / 01</span>
          <h2>先写下声音的性格，<br /><em>再让它开口。</em></h2>
          <p>不需要参考音频。用自然语言描述年龄、质感、语速和情绪，创建一枚可以复用的设计音色。</p>
        </div>
        <div className="design-signal"><WandSparkles size={21} /><span>3 家厂商 · 2 种资产模式</span></div>
      </div>
      <div className="design-layout">
        <div className="design-form">
          <div className="design-step"><span>02</span><div><b>选择设计引擎</b><small>不同厂商的 Voice Design 形态不同，界面会自动显示必填项。</small></div></div>
          <div className="provider-switch">
            {Object.entries(providerMeta).filter(([id]) => designModels.some((item) => item.provider === id)).map(([id, meta]) => (
              <button className={provider === id ? "selected" : ""} onClick={() => chooseProvider(id)} key={id}><span className={"provider-dot " + meta.tone} />{meta.label}</button>
            ))}
          </div>
          <label>设计模型</label>
          <select value={modelId} onChange={(event) => setModelId(event.target.value)}>
            {providerModels.map((item) => <option value={item.model_id} key={item.gateway_id}>{item.display_name}</option>)}
          </select>
          <div className="design-step design-step-spaced"><span>03</span><div><b>描述你想要的声音</b><small>越具体越稳定；避免同时写互相冲突的特征。</small></div></div>
          <textarea className="design-prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} maxLength={promptLimit} />
          <div className="design-count">{prompt.length} / {promptLimit.toLocaleString()}</div>
          <label>试听文本</label>
          <textarea className="design-preview-text" value={previewText} onChange={(event) => setPreviewText(event.target.value)} maxLength={previewLimit} />
          <div className="form-grid design-names"><div><label>显示名称</label><input value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></div><div><label>兼容别名</label><input value={publicName} onChange={(event) => setPublicName(event.target.value)} /></div></div>
          <button className="primary-button design-submit" onClick={() => void submit()} disabled={working || !selected || !prompt.trim() || !previewText.trim()}><WandSparkles size={17} />{working ? "正在设计..." : "创建并试听音色"}<span>↵</span></button>
        </div>
        <aside className="design-inspector">
          <div className="inspector-label">DESIGN OUTPUT</div>
          {previewVoice ? <div className="design-result"><div className="result-mark"><Check size={19} /></div><strong>{previewVoice.display_name}</strong><small>{previewVoice.provider === "mimo" ? "请求级设计模板" : "已保存到音色库"}</small>{previewVoice.preview_url && <audio controls src={previewVoice.preview_url} />}</div> : <div className="design-empty"><WandSparkles size={28} /><strong>还没有试听结果</strong><span>提交描述后，这里会出现试听播放器与资产状态。</span></div>}
          <div className="design-rules"><b>设计提示</b><span>声音质感</span><span>年龄与身份</span><span>语速与停顿</span><span>情绪和使用场景</span></div>
        </aside>
      </div>
    </section>
  );
}

function ClonePanel({
  fileRef,
  models,
  onClone,
}: {
  fileRef: React.RefObject<HTMLInputElement | null>;
  models: Model[];
  onClone: (config: CloneConfig) => Promise<void>;
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
  const [consented, setConsented] = useState(false);
  const [fileName, setFileName] = useState("");
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
  const submit = async () => {
    if (
      !selected ||
      !displayName.trim() ||
      !publicName.trim() ||
      !consented ||
      !fileName
    )
      return;
    setWorking(true);
    try {
      await onClone({
        provider,
        model_id: modelId,
        display_name: displayName.trim(),
        public_name: publicName.trim(),
      });
    } finally {
      setWorking(false);
    }
  };

  return (
    <section className="page-section clone-page">
      <div className="clone-intro">
        <span className="section-kicker">VOICE CLONING / 01</span>
        <h2>
          让一个真实的声音
          <br />
          <em>留下它的纹理。</em>
        </h2>
        <p>
          上传一段已获授权的参考音频，再选择厂商和明确支持声音复刻的目标模型。
        </p>
        <label className="consent-line">
          <input
            type="checkbox"
            checked={consented}
            onChange={(event) => setConsented(event.target.checked)}
          />
          我确认已获得录音中说话人的明确授权
        </label>
      </div>
      <div className="clone-form">
        <label className="upload-zone">
          <input
            type="file"
            accept={
              isVolcengineClone
                ? ".wav,.mp3,.ogg,.m4a,.aac,.pcm,audio/*"
                : ".wav,.mp3,.m4a,audio/wav,audio/mpeg,audio/mp4"
            }
            ref={fileRef}
            onChange={(event) =>
              setFileName(event.target.files?.[0]?.name || "")
            }
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
        <div className="form-grid">
          <div>
            <label>目标厂商</label>
            <select
              value={provider}
              onChange={(event) => chooseProvider(event.target.value)}
            >
              {Object.keys(providerMeta)
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
          <div>
            <label>目标模型</label>
            <select
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
        </div>
        <div className="form-grid">
          <div>
            <label>显示名称</label>
            <input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
            />
          </div>
          <div>
            <label>兼容别名</label>
            <input
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
            !consented ||
            !fileName ||
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
              : selected?.mode === "provider"
                ? "该模型会在每次生成语音时向厂商发送本地参考音频。"
                : "该模型当前使用本地演示适配器，不会向厂商上传参考音频。"}
        </p>
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
  return (
    <section className="page-section gateway-page">
      <div className="gateway-header">
        <div>
          <span className="section-kicker">OPENAI COMPATIBILITY</span>
          <h2>把 Voice Studio 接到任何支持 OpenAI 的应用</h2>
          <p>
            本地网关统一模型、音色别名和输出格式。厂商 Key
            只留在后端，外部应用只需要一个 Base URL 和网关 Key。
          </p>
        </div>
        <div className="gateway-status">
          <span>
            <span className="live-dot" /> 运行中
          </span>
            <small>{activeGateway?.managed ? "仅本机监听 · 可轮换 Key" : "仅本机监听 · 环境变量托管"}</small>
        </div>
      </div>
      <div className="gateway-grid">
        <div className="code-panel">
          <div className="code-head">
            <span>连接信息</span>
            <button className="icon-button" title="复制连接信息" onClick={() => copy("连接信息", `${base}\nBearer ${key}`)}>
              <Copy size={16} />
            </button>
          </div>
          <div className="code-line">
            <span>Base URL</span>
            <code>{base}</code>
          </div>
          <div className="code-line">
            <span>API Key</span>
            <code>{visibleKey ? key : (activeGateway?.key_hint || "未读取")}</code>
            <button className="inline-copy" onClick={() => copy("网关 Key", key)} title="复制网关 Key"><Copy size={13} /></button>
          </div>
          <div className="code-line">
            <span>模式</span>
            <code>{activeGateway?.mode || "hybrid"} · Provider Adapter</code>
          </div>
          <div className="code-snippet"><span>外部应用只需要配置 Base URL 与网关 Key</span></div>
        </div>
        <div className="capability-panel">
          <div className="capability-title">
            <KeyRound size={17} />
            当前兼容面
          </div>
          <div className="capability">
            <Check size={15} />
            <span>
              <strong>GET /v1/models</strong>
              <small>OpenAI SDK 模型发现 · 统一返回四家厂商模型</small>
            </span>
          </div>
          <div className="capability">
            <Check size={15} />
            <span>
              <strong>POST /v1/audio/speech</strong>
              <small>非流式音频合成 · 支持 wav / mp3 / opus / aac / flac / pcm</small>
            </span>
          </div>
          <div className="capability">
            <Check size={15} />
            <span>
              <strong>POST /v1/audio/speech/stream</strong>
              <small>SSE 音频分片 · 火山 Seed / 千问 CosyVoice / MiniMax 支持原生 MP3 流 · MiMo 自动兼容</small>
            </span>
          </div>
          <div className="gateway-warning">
            <CircleHelp size={15} />
            <span>{activeGateway?.note || "MiMo 已接入真实厂商接口。"}<br />Key 来源：{activeGateway?.key_source || "本地配置"}</span>
          </div>
          <div className="gateway-actions">
            <button className="secondary-button" onClick={() => setVisibleKey((value) => !value)}>{visibleKey ? <EyeOff size={14} /> : <Eye size={14} />}{visibleKey ? "隐藏 Key" : "显示 Key"}</button>
            <button className="secondary-button" disabled={!activeGateway?.managed || rotating} onClick={rotate}><RotateCcw size={14} className={rotating ? "spinning" : ""} />{rotating ? "正在轮换" : "轮换网关 Key"}</button>
          </div>
          {copied && <div className="copy-feedback"><Check size={14} />{copied}</div>}
        </div>
      </div>
      <section className="gateway-observability">
        <div className="observability-head">
          <div>
            <span className="section-kicker">GATEWAY HEALTH</span>
            <h3>运行统计</h3>
            <p>仅统计本版本启用记录后的网关语音请求，不混入旧任务数据。</p>
          </div>
          <div className="observability-controls">
            <div className="segmented compact-segmented">
              {[['24h', '24 小时'], ['7d', '7 天'], ['30d', '30 天'], ['all', '全部']].map(([id, label]) => (
                <button className={statsWindow === id ? "selected" : ""} onClick={() => setStatsWindow(id)} key={id}>{label}</button>
              ))}
            </div>
            <select value={statsProvider} onChange={(event) => setStatsProvider(event.target.value)} aria-label="筛选统计厂商">
              <option value="">全部厂商</option>
              {Object.entries(providerMeta).map(([id, meta]) => <option value={id} key={id}>{meta.label}</option>)}
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
                    <span><b>{statsProviderLabel(item.name)}</b><small>厂商</small></span><code>{item.requests}</code><code>{item.success_rate}%</code><code>{formatLatency(item.first_chunk_latency.p95)}</code><code>{formatLatency(item.total_latency.p95)}</code>
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
      </section>
      <div className="gateway-testbench">
        <div className="testbench-header">
          <div>
            <span className="section-kicker">LIVE CHECK</span>
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
                {Object.keys(providerMeta).map((provider) => {
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
            {selectedTestModel && <div className="test-model-note"><span className={"provider-mark " + providerMeta[selectedTestModel.provider]?.tone}>{providerMeta[selectedTestModel.provider]?.mark}</span><span><strong>{selectedTestModel.display_name}</strong><small>{selectedTestModel.mode === "provider" ? "真实厂商接口" : "本地演示适配器"} · {compatibleVoices.length} 个兼容音色</small></span></div>}
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
          <div className="examples-head"><div><span className="section-kicker">COPY READY</span><strong>当前请求示例</strong></div><button className="inline-copy" onClick={() => copy(exampleTab, examples[exampleTab])} title="复制当前示例"><Copy size={14} /></button></div>
          <div className="example-tabs">{[["powershell", "PowerShell"], ["curl", "curl"], ["python", "Python"], ["javascript", "JavaScript"], ["stream", "SSE 流式"]].map(([id, label]) => <button className={exampleTab === id ? "selected" : ""} onClick={() => setExampleTab(id)} key={id}>{label}</button>)}</div>
          <pre>{examples[exampleTab]}</pre>
        </div>
      </div>
    </section>
  );
}

type StorageInfo = {
  job_count: number;
  audio_count: number;
  audio_bytes: number;
  audio_megabytes: number;
  missing_audio_count: number;
};

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function History({ jobs, onRefresh }: { jobs: Job[]; onRefresh: () => Promise<void> }) {
  const [dateFilter, setDateFilter] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [storage, setStorage] = useState<StorageInfo | null>(null);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");
  const dates = Array.from(
    new Set(jobs.map((job) => job.created_date || new Date(job.created_at).toLocaleDateString("sv-SE"))),
  ).sort((a, b) => b.localeCompare(a));
  const filtered = dateFilter
    ? jobs.filter((job) => (job.created_date || new Date(job.created_at).toLocaleDateString("sv-SE")) === dateFilter)
    : jobs;
  const visibleIds = filtered.map((job) => job.id);
  const selectedJobs = filtered.filter((job) => selectedIds.has(job.id));
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));
  const clearDate = () => setDateFilter("");
  const loadStorage = () => api<StorageInfo>("/api/jobs/storage").then(setStorage).catch(() => undefined);

  useEffect(() => {
    void loadStorage();
  }, [jobs.length]);
  useEffect(() => {
    setSelectedIds((current) => new Set([...current].filter((id) => jobs.some((job) => job.id === id))));
  }, [jobs]);
  useEffect(() => {
    setSelectedIds(new Set());
  }, [dateFilter]);

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
    if (!exportIds.length && !dateFilter) return setMessage("请先选择要导出的任务");
    setWorking(true);
    setMessage("正在整理 ZIP 文件...");
    try {
      const response = await fetch("/api/jobs/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_ids: exportIds, date: exportIds.length ? undefined : dateFilter }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = dateFilter && !exportIds.length ? `voice-studio-${dateFilter}.zip` : "voice-studio-selected-jobs.zip";
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
    const ids = [...selectedIds];
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
    await onRefresh();
    await loadStorage();
    setWorking(false);
  };

  return (
    <section className="page-section">
      <div className="page-toolbar">
        <div>
          <span className="section-kicker">ACTIVITY LOG</span>
          <h2>{dateFilter ? `${dateFilter} 的任务` : "最近任务"}</h2>
        </div>
        <div className="history-toolbar-actions">
          <label className="history-date-filter">
            <Clock3 size={15} />
            <span>按天</span>
            <input type="date" value={dateFilter} onChange={(event) => setDateFilter(event.target.value)} aria-label="按日期筛选任务" />
          </label>
          {dateFilter && <button className="icon-button" onClick={clearDate} title="清除日期筛选"><X size={16} /></button>}
          <button className="secondary-button" onClick={() => void refresh()} disabled={working}><RefreshCw size={16} />刷新</button>
        </div>
      </div>
      {dates.length > 0 && (
        <div className="history-date-chips" aria-label="有任务的日期">
          <button className={!dateFilter ? "selected" : ""} onClick={clearDate}>全部</button>
          {dates.slice(0, 8).map((date) => <button className={dateFilter === date ? "selected" : ""} onClick={() => setDateFilter(date)} key={date}>{date}</button>)}
        </div>
      )}
      <div className="history-bulk-bar">
        <label className="history-select-all"><input type="checkbox" checked={allVisibleSelected} onChange={toggleAll} disabled={!visibleIds.length} />选择当前{dateFilter ? "日期" : "列表"}</label>
        <span>{selectedIds.size ? `已选 ${selectedIds.size} 条` : "未选择任务"}</span>
        <div className="history-bulk-actions">
          <button className="secondary-button" onClick={() => void downloadZip()} disabled={working || (!selectedIds.size && !dateFilter)}><Download size={15} />{selectedIds.size ? "导出选中" : "导出本日"}</button>
          <button className="danger-button" onClick={() => void deleteSelected()} disabled={working || !selectedIds.size}><Trash2 size={15} />删除选中</button>
        </div>
      </div>
      {storage && <div className="history-storage"><FileAudio size={15} /><span>任务音频占用 <strong>{storage.audio_megabytes.toFixed(1)} MB</strong> · {storage.audio_count} 个文件</span>{storage.missing_audio_count > 0 && <small>{storage.missing_audio_count} 个文件已丢失</small>}</div>}
      {message && <div className="history-message"><Activity size={14} />{message}</div>}
      <div className="history-list">
        {filtered.length === 0 ? <div className="empty-state"><Clock3 size={22} /><span>{dateFilter ? "这一天没有任务记录。" : "还没有任务，去合成工作台生成第一条语音。"}</span></div> : filtered.map((job) => (
          <div className="history-row" key={job.id}>
            <label className="history-checkbox"><input type="checkbox" checked={selectedIds.has(job.id)} onChange={() => toggleJob(job.id)} aria-label={`选择任务 ${job.id}`} /></label>
            <div className="history-icon"><Check size={16} /></div>
            <div className="history-main">
              <strong>{job.voice} · {job.model}</strong>
              <span>{job.input_chars} 字符 · {job.duration_ms / 1000}s · {new Date(job.created_at).toLocaleString()}</span>
              {job.input_text ? <details className="history-record"><summary>查看文字记录</summary><p>{job.input_text}</p></details> : <span className="history-missing">旧记录未保存原始文字</span>}
            </div>
            <div className="history-actions">
              <a className={job.text_url ? "history-action" : "history-action disabled"} href={job.text_url || undefined} title={job.text_url ? "下载文字记录" : "没有可下载的文字记录"} aria-label="下载文字记录"><FileText size={16} /></a>
              <a className={job.audio_url ? "history-action" : "history-action disabled"} href={job.audio_url || undefined} title={job.audio_url ? "下载声音文件" : "声音文件不可用"} aria-label="下载声音文件"><Download size={16} /></a>
              <button className="history-action danger-action" onClick={() => void deleteOne(job)} title="删除任务" aria-label="删除任务"><Trash2 size={16} /></button>
              <span className="status"><span className="live-dot" />{job.status === "completed" ? "已完成" : job.status}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function Settings({ models }: { models: Model[] }) {
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
      setMessage("凭据已写入 Windows Credential Manager");
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
      !window.confirm("删除这个账号及其 Windows Credential Manager 凭据？")
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
    <section className="page-section settings-page">
      <div>
        <span className="section-kicker">SECURE CREDENTIALS</span>
        <h2>厂商账号与 API 凭据</h2>
        <p className="settings-lead">
          API Key 直接写入 Windows Credential Manager。页面和 SQLite
          只保存脱敏后缀与 Endpoint，不会回显完整密钥。
        </p>
      </div>
      <div className="credential-layout">
        <div className="provider-rail">
          {Object.entries(providerMeta).map(([id, meta]) => {
            const count = accounts.filter(
              (item) => item.provider === id,
            ).length;
            const active = accounts.some(
              (item) => item.provider === id && item.status === "active",
            );
            return (
              <button
                className={
                  provider === id ? "provider-tab selected" : "provider-tab"
                }
                onClick={() => setProvider(id)}
                key={id}
              >
                <span className={"provider-mark " + meta.tone}>
                  {meta.mark}
                </span>
                <span className="provider-copy">
                  <strong>{meta.label}</strong>
                  <small>
                    {models.filter((item) => item.provider === id).length}{" "}
                    个模型 · {count ? count + " 个账号" : "未配置"}
                  </small>
                </span>
                <span
                  className={
                    active
                      ? "account-indicator active"
                      : count
                        ? "account-indicator saved"
                        : "account-indicator"
                  }
                />
              </button>
            );
          })}
          <div className="security-note">
            <ShieldCheck size={16} />
            <span>
              密钥由当前 Windows 用户加密保存，其他系统账号无法直接读取。
            </span>
          </div>
        </div>
        <div className="credential-editor">
          <div className="editor-title">
            <div>
              <span className="section-kicker">
                {provider.toUpperCase()} / ACCOUNT
              </span>
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
                      : "粘贴后将直接写入 Windows Credential Manager"
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
    </section>
  );
}
