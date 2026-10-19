import { useCallback, useEffect, useState } from "react";

const PROVIDER_ORDER = ["zyt_foundry", "openai_compatible", "anthropic_compatible"];

const PROVIDER_BLURBS = {
  zyt_foundry: "Default. OpenAI-compatible gateway with the gpt-5.5 to gpt-6.1 family.",
  openai_compatible: "Any endpoint that speaks /v1/chat/completions with tools.",
  anthropic_compatible: "Any endpoint that speaks the Anthropic Messages API with tools.",
};

const inputClass =
  "w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground shadow-sm outline-none transition focus:border-ring focus:ring-2 focus:ring-ring/30 disabled:bg-muted disabled:text-muted-foreground";
const primaryButton =
  "inline-flex items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50";
const outlineButton =
  "inline-flex items-center justify-center gap-2 rounded-md border border-input bg-background px-3.5 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent disabled:pointer-events-none disabled:opacity-50";

function cx(...classes) {
  return classes.filter(Boolean).join(" ");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
  return body;
}

export function useSetup() {
  const [settings, setSettings] = useState(null);
  const [prereqs, setPrereqs] = useState(null);
  const [error, setError] = useState("");

  const refreshSettings = useCallback(async () => {
    try {
      setSettings(await api("/api/settings"));
      setError("");
    } catch (e) {
      setError(`Backend not reachable: ${e.message}`);
    }
  }, []);

  const refreshPrereqs = useCallback(async () => {
    try {
      setPrereqs(await api("/api/prereqs"));
    } catch {
      setPrereqs(null);
    }
  }, []);

  useEffect(() => {
    refreshSettings();
    refreshPrereqs();
  }, [refreshSettings, refreshPrereqs]);

  return { settings, setSettings, prereqs, refreshSettings, refreshPrereqs, error };
}

function ProviderForm({ settings, onSaved }) {
  const [selected, setSelected] = useState(settings.active_provider);
  const [drafts, setDrafts] = useState({});
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState(null);

  const provider = settings.providers[selected];
  const draft = drafts[selected] || {};
  const setField = (field, value) =>
    setDrafts((current) => ({ ...current, [selected]: { ...current[selected], [field]: value } }));

  const save = async () => {
    const fields = {};
    if (draft.api_key) fields.api_key = draft.api_key;
    if (!provider.fixed_url && draft.base_url !== undefined) fields.base_url = draft.base_url;
    if (draft.model !== undefined) fields.model = draft.model;
    const next = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ active_provider: selected, providers: { [selected]: fields } }),
    });
    setDrafts((current) => ({ ...current, [selected]: {} }));
    onSaved(next);
    return next;
  };

  const run = async (label, action) => {
    setBusy(label);
    setResult(null);
    try {
      await action();
    } catch (e) {
      setResult({ ok: false, text: e.message });
    } finally {
      setBusy("");
    }
  };

  const onSave = () =>
    run("save", async () => {
      await save();
      setResult({ ok: true, text: `Saved. ${provider.label} is now the active provider.` });
    });

  const onTest = () =>
    run("test", async () => {
      await save();
      const test = await api("/api/settings/test", { method: "POST" });
      setResult(
        test.ok
          ? { ok: true, text: `Connected to ${test.provider} (${test.model}). Reply: “${test.reply || "(empty)"}”` }
          : { ok: false, text: test.error }
      );
    });

  const onClearKey = () =>
    run("clear", async () => {
      const next = await api("/api/settings", {
        method: "PUT",
        body: JSON.stringify({ providers: { [selected]: { clear_key: true } } }),
      });
      onSaved(next);
      setResult({ ok: true, text: "Saved key removed." });
    });

  const onLoadModels = () =>
    run("models", async () => {
      await save();
      const next = await api(`/api/models/${selected}`, { method: "POST" });
      onSaved(next);
      setResult({ ok: true, text: `Loaded ${next.providers[selected].models.length} models from ${provider.label}.` });
    });

  const modelValue = draft.model ?? provider.model;
  const knownModel = provider.models.includes(modelValue);
  const [customModel, setCustomModel] = useState(false);
  const showCustom = customModel || !provider.models.length || (modelValue && !knownModel);

  const keyPlaceholder = provider.has_key
    ? provider.key_source === "environment"
      ? `Using ZYT_FOUNDRY_API_KEY from the environment (${provider.key_hint})`
      : `Saved (${provider.key_hint}). Type to replace.`
    : "Paste your API key";

  return (
    <div className="space-y-5">
      <div className="grid gap-2">
        {PROVIDER_ORDER.map((id) => {
          const p = settings.providers[id];
          const active = settings.active_provider === id;
          return (
            <button
              key={id}
              type="button"
              onClick={() => {
                setSelected(id);
                setCustomModel(false);
                setResult(null);
              }}
              className={cx(
                "rounded-xl border p-3.5 text-left transition",
                selected === id ? "border-foreground/40 bg-accent shadow-sm" : "border-border hover:bg-accent/60"
              )}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2.5 text-sm font-medium text-foreground">
                  <span
                    className={cx(
                      "flex h-4 w-4 items-center justify-center rounded-full border",
                      selected === id ? "border-foreground" : "border-muted-foreground/40"
                    )}
                  >
                    {selected === id ? <span className="h-2 w-2 rounded-full bg-foreground" /> : null}
                  </span>
                  {p.label}
                </span>
                <span className="flex items-center gap-1.5">
                  {active ? (
                    <span className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
                      Active
                    </span>
                  ) : null}
                  <span
                    className={cx(
                      "rounded-md px-2 py-0.5 text-[11px] font-medium",
                      p.has_key ? "bg-muted text-muted-foreground" : "bg-amber-50 text-amber-700"
                    )}
                  >
                    {p.has_key ? "Key set" : "No key"}
                  </span>
                </span>
              </div>
              <p className="mt-1.5 pl-[26px] text-xs leading-5 text-muted-foreground">{PROVIDER_BLURBS[id]}</p>
            </button>
          );
        })}
      </div>

      <div className="space-y-3.5 rounded-xl border border-border bg-muted/30 p-4">
        <label className="block space-y-1.5">
          <span className="text-xs font-medium text-muted-foreground">Base URL</span>
          <input
            className={inputClass}
            value={draft.base_url ?? provider.base_url}
            onChange={(e) => setField("base_url", e.target.value)}
            disabled={provider.fixed_url}
            spellCheck={false}
          />
        </label>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Model</span>
            <button
              type="button"
              className="text-xs font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline disabled:opacity-50"
              onClick={onLoadModels}
              disabled={!!busy || !(provider.has_key || draft.api_key)}
              title={provider.has_key || draft.api_key ? "Ask the provider for its model list" : "Add an API key first"}
            >
              {busy === "models" ? "Loading…" : provider.models_fetched ? "Reload models" : "Load models"}
            </button>
          </div>
          {showCustom ? (
            <div className="flex gap-2">
              <input
                className={inputClass}
                value={modelValue}
                onChange={(e) => setField("model", e.target.value)}
                placeholder={provider.kind === "anthropic" ? "claude-opus-5-5" : "model id"}
                spellCheck={false}
              />
              {provider.models.length ? (
                <button type="button" className={outlineButton} onClick={() => {
                  setCustomModel(false);
                  setField("model", provider.models[0]);
                }}>
                  List
                </button>
              ) : null}
            </div>
          ) : (
            <select
              className={inputClass}
              value={modelValue}
              onChange={(e) => {
                if (e.target.value === "__custom__") {
                  setCustomModel(true);
                } else {
                  setField("model", e.target.value);
                }
              }}
            >
              {provider.models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
              <option value="__custom__">Custom…</option>
            </select>
          )}
        </div>
        <label className="block space-y-1.5">
          <span className="text-xs font-medium text-muted-foreground">API key</span>
          <input
            className={inputClass}
            type="password"
            autoComplete="off"
            value={draft.api_key ?? ""}
            onChange={(e) => setField("api_key", e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onTest()}
            placeholder={keyPlaceholder}
            spellCheck={false}
          />
        </label>
        <p className="text-xs leading-5 text-muted-foreground">
          Keys are saved on this machine in <code className="font-mono">{settings.settings_path}</code> (git-ignored)
          and never sent back to the browser.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={primaryButton} onClick={onTest} disabled={!!busy}>
          {busy === "test" ? "Testing…" : "Save and test"}
        </button>
        <button type="button" className={outlineButton} onClick={onSave} disabled={!!busy}>
          {busy === "save" ? "Saving…" : "Save"}
        </button>
        {provider.key_source === "settings" ? (
          <button
            type="button"
            className="ml-auto text-xs font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
            onClick={onClearKey}
            disabled={!!busy}
          >
            Remove saved key
          </button>
        ) : null}
      </div>

      {result ? (
        <div
          className={cx(
            "rounded-lg border px-3.5 py-2.5 text-sm leading-6",
            result.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-red-200 bg-red-50 text-red-700"
          )}
        >
          {result.text}
        </div>
      ) : null}
    </div>
  );
}

function CopyCommand({ command }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="mt-2 flex items-center gap-2 rounded-lg bg-slate-950 px-3 py-2">
      <code className="min-w-0 flex-1 truncate font-mono text-xs text-slate-200">{command}</code>
      <button
        type="button"
        className="shrink-0 text-xs font-medium text-slate-400 hover:text-white"
        onClick={() => {
          navigator.clipboard?.writeText(command);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

function SetupGuide({ prereqs, onRecheck }) {
  const [checking, setChecking] = useState(false);
  if (!prereqs) {
    return <p className="text-sm text-muted-foreground">Checking this machine…</p>;
  }
  return (
    <div className="space-y-4">
      <div
        className={cx(
          "rounded-lg border px-3.5 py-2.5 text-sm",
          prereqs.ready ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"
        )}
      >
        {prereqs.ready
          ? "Everything required is installed."
          : "Some required tools are missing. Install them, then check again."}
      </div>

      <ul className="space-y-2.5">
        {prereqs.items.map((item) => (
          <li key={item.name} className="rounded-xl border border-border p-3.5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="flex items-center gap-2 text-sm font-medium text-foreground">
                  <span
                    className={cx(
                      "h-2 w-2 shrink-0 rounded-full",
                      item.ok ? "bg-emerald-500" : item.required ? "bg-red-500" : "bg-slate-300"
                    )}
                  />
                  {item.name}
                </p>
                <p className="mt-1 pl-4 text-xs leading-5 text-muted-foreground">{item.purpose}</p>
              </div>
              <span
                className={cx(
                  "shrink-0 rounded-md px-2 py-0.5 text-[11px] font-medium",
                  item.ok
                    ? "bg-emerald-50 text-emerald-700"
                    : item.required
                      ? "bg-red-50 text-red-700"
                      : "bg-muted text-muted-foreground"
                )}
              >
                {item.ok ? "Ready" : item.required ? "Required" : "Optional"}
              </span>
            </div>
            {item.ok && item.detail ? (
              <p className="mt-1.5 truncate pl-4 font-mono text-[11px] text-muted-foreground">{item.detail}</p>
            ) : null}
            {!item.ok ? (
              <div className="pl-4">
                {item.detail ? <p className="mt-1.5 text-xs text-muted-foreground">{item.detail}</p> : null}
                <CopyCommand command={item.install[prereqs.platform] || item.install.macos} />
              </div>
            ) : null}
          </li>
        ))}
      </ul>

      <button
        type="button"
        className={outlineButton}
        disabled={checking}
        onClick={async () => {
          setChecking(true);
          await onRecheck();
          setChecking(false);
        }}
      >
        {checking ? "Checking…" : "Check again"}
      </button>
    </div>
  );
}

export function SettingsDrawer({ open, tab, onTab, onClose, setup }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const { settings, setSettings, prereqs, refreshPrereqs, error } = setup;

  return (
    <div className={cx("fixed inset-0 z-50", open ? "" : "pointer-events-none")} aria-hidden={!open}>
      <div
        className={cx("absolute inset-0 bg-slate-950/20 transition-opacity", open ? "opacity-100" : "opacity-0")}
        onClick={onClose}
      />
      <aside
        className={cx(
          "absolute inset-y-0 right-0 flex w-full max-w-[460px] flex-col border-l border-border bg-background shadow-2xl transition-transform duration-200",
          open ? "translate-x-0" : "translate-x-full"
        )}
        role="dialog"
        aria-label="Settings"
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h2 className="text-base font-semibold tracking-tight text-foreground">Settings</h2>
            <p className="text-xs text-muted-foreground">Model provider and machine setup</p>
          </div>
          <button type="button" className="rounded-md px-2 py-1 text-sm text-muted-foreground hover:bg-accent" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="border-b border-border px-5 pt-3">
          <div className="inline-flex gap-1 rounded-lg bg-muted p-1">
            {[
              ["provider", "Model provider"],
              ["setup", "Setup guide"],
            ].map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => onTab(id)}
                className={cx(
                  "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  tab === id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                )}
              >
                {label}
                {id === "setup" && prereqs && !prereqs.ready ? <span className="h-1.5 w-1.5 rounded-full bg-amber-500" /> : null}
                {id === "provider" && settings && !settings.configured ? (
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                ) : null}
              </button>
            ))}
          </div>
          <div className="h-3" />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          {tab === "provider" && settings ? <ProviderForm settings={settings} onSaved={setSettings} /> : null}
          {tab === "setup" ? <SetupGuide prereqs={prereqs} onRecheck={refreshPrereqs} /> : null}
        </div>
      </aside>
    </div>
  );
}
