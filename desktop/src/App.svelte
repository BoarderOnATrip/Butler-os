<script>
  import { invoke } from "@tauri-apps/api/core";
  import { open } from "@tauri-apps/plugin-shell";

  let screen = "welcome";
  let status = "Checking runtime...";
  let runtimeReady = false;
  let preflightResult = "";
  let secretCaptureResult = "";
  let apiKey = "";
  let agentId = "";
  let saving = false;
  let bridgePairing = null;
  let startingBridge = false;
  let openScreenStatus = null;
  let openScreenSessions = [];
  let openScreenImportResult = null;
  let openScreenBusy = false;
  let openScreenLoaded = false;
  let memoryStatus = null;
  let memoryIndexResult = null;
  let memoryBusy = false;
  let memoryLoaded = false;
  let corePrompt = "";
  let coreAgentBusy = false;
  let coreAgentResult = null;

  async function refreshStatus() {
    try {
      const result = await invoke("get_runtime_status");
      runtimeReady = Boolean(result?.runtime_available);
      agentId = result?.config?.AIBUTLER_AGENT_ID ?? "";
      status = runtimeReady ? "Runtime ready." : "Runtime not ready.";
    } catch (error) {
      runtimeReady = false;
      status = `Runtime check failed: ${String(error)}`;
    }
  }

  refreshStatus().catch((error) => {
    console.error("Status check failed:", error);
  });

  async function runToolJson(tool, args = {}, options = {}) {
    const raw = await invoke("run_tool", {
      tool,
      args: JSON.stringify(args),
      approved: options.approved ?? false,
      note: options.note ?? "",
    });
    return JSON.parse(raw);
  }

  async function openElevenLabs() {
    await open("https://elevenlabs.io/app/conversational-ai");
  }

  async function saveElevenLabsConfig() {
    if (!apiKey.trim()) {
      status = "Paste your ElevenLabs API key first.";
      return;
    }
    if (!agentId.trim()) {
      status = "Paste your ElevenLabs agent ID first.";
      return;
    }

    saving = true;
    status = "Saving ElevenLabs configuration...";
    try {
      await invoke("run_tool", {
        tool: "save_secret",
        args: JSON.stringify({ name: "elevenlabs", value: apiKey.trim() }),
        approved: true,
        note: "Desktop onboarding saved ElevenLabs API key",
      });
      await invoke("save_config", { key: "AIBUTLER_AGENT_ID", value: agentId.trim() });
      status = "ElevenLabs connected. Next: macOS permissions.";
      screen = "permissions";
    } catch (error) {
      status = `Failed to save ElevenLabs config: ${String(error)}`;
    } finally {
      saving = false;
    }
  }

  async function openAccessibility() {
    await invoke("open_system_settings", { pane: "accessibility" });
  }

  async function openScreenRecording() {
    await invoke("open_system_settings", { pane: "screen-recording" });
  }

  async function runPreflight() {
    try {
      preflightResult = await invoke("run_tool", {
        tool: "preflight_computer_use",
        args: "{}",
      });
      status = "Preflight completed.";
    } catch (error) {
      preflightResult = String(error);
      status = "Preflight failed.";
    }
  }

  async function autoCaptureSecrets() {
    try {
      secretCaptureResult = await invoke("run_tool", {
        tool: "auto_capture_keys",
        args: "{}",
        approved: true,
        note: "Desktop onboarding auto-captured secrets",
      });
      status = "Additional secrets captured. Butler is ready.";
      screen = "ready";
    } catch (error) {
      secretCaptureResult = String(error);
      status = "Secret capture failed.";
    }
  }

  async function startVoice() {
    try {
      await invoke("start_voice_loop");
      status = "Voice loop launched.";
    } catch (error) {
      status = `Failed to launch voice: ${String(error)}`;
    }
  }

  async function loadBridgePairing() {
    try {
      bridgePairing = await invoke("get_bridge_pairing");
      status = "Phone pairing material loaded.";
    } catch (error) {
      status = `Failed to load bridge pairing: ${String(error)}`;
    }
  }

  async function startBridge() {
    startingBridge = true;
    try {
      bridgePairing = await invoke("start_bridge");
      status = "Secure phone bridge started in LAN mode.";
    } catch (error) {
      status = `Failed to start phone bridge: ${String(error)}`;
    } finally {
      startingBridge = false;
    }
  }

  async function runDailyBriefing() {
    try {
      const result = await invoke("run_agentic", {
        objective: "Generate today's executive briefing: calendar events, pending tasks, and top priorities.",
      });
      alert(result);
    } catch (error) {
      alert(String(error));
    }
  }

  async function refreshOpenScreen() {
    openScreenBusy = true;
    try {
      const statusResult = await runToolJson("openscreen_status");
      const sessionsResult = await runToolJson("openscreen_list_sessions", { limit: 5 });
      openScreenStatus = statusResult.output ?? null;
      openScreenSessions = sessionsResult.output?.sessions ?? [];
      if (openScreenStatus?.available) {
        status = `OpenScreen detected${openScreenStatus.recordings_dir ? " and ready for import." : "."}`;
      } else {
        status = "OpenScreen not detected yet. Install the app or prepare the repo, then scan again.";
      }
    } catch (error) {
      status = `OpenScreen scan failed: ${String(error)}`;
    } finally {
      openScreenBusy = false;
    }
  }

  async function launchOpenScreen() {
    openScreenBusy = true;
    try {
      const result = await runToolJson("openscreen_launch");
      const launchedVia = result.output?.launched_via;
      status =
        launchedVia === "repo"
          ? "OpenScreen dev mode launched from the local repo."
          : "OpenScreen launched.";
      await refreshOpenScreen();
    } catch (error) {
      status = `Failed to launch OpenScreen: ${String(error)}`;
      openScreenBusy = false;
    }
  }

  async function importOpenScreenSession(sessionManifestPath = "") {
    openScreenBusy = true;
    try {
      const result = await runToolJson("openscreen_import_session", {
        session_manifest_path: sessionManifestPath,
        pin: true,
      });
      openScreenImportResult = result.output ?? null;
      status = `Imported OpenScreen capture into Butler context: ${result.output?.artifact_ref ?? "artifact"}`;
      await refreshOpenScreen();
    } catch (error) {
      status = `Failed to import OpenScreen capture: ${String(error)}`;
      openScreenBusy = false;
    }
  }

  async function importLatestOpenScreen() {
    await importOpenScreenSession("");
  }

  async function refreshMemoryStatus() {
    memoryBusy = true;
    try {
      const result = await runToolJson("butler_memory_status");
      memoryStatus = result.output ?? null;
      if (memoryStatus?.total_drawers) {
        status = `Butler recall ready with ${memoryStatus.total_drawers} indexed memories.`;
      }
    } catch (error) {
      status = `Butler recall status failed: ${String(error)}`;
    } finally {
      memoryBusy = false;
    }
  }

  async function reindexMemory(clear = true) {
    memoryBusy = true;
    try {
      const result = await runToolJson("butler_memory_index", { clear });
      memoryIndexResult = result.output ?? null;
      memoryStatus = memoryIndexResult;
      status = `Indexed ${memoryIndexResult?.indexed_documents ?? 0} Butler memories into local recall.`;
    } catch (error) {
      status = `Butler recall indexing failed: ${String(error)}`;
    } finally {
      memoryBusy = false;
    }
  }

  async function askCoreAgent() {
    if (!corePrompt.trim()) {
      status = "Ask Butler something first.";
      return;
    }

    coreAgentBusy = true;
    try {
      const raw = await invoke("run_core_agent", { prompt: corePrompt.trim() });
      const result = JSON.parse(raw);
      coreAgentResult = result.output ?? null;
      status = coreAgentResult?.summary ?? "Butler core agent finished.";
      if (!memoryStatus?.total_drawers) {
        await refreshMemoryStatus();
      }
    } catch (error) {
      status = `Butler core agent failed: ${String(error)}`;
    } finally {
      coreAgentBusy = false;
    }
  }

  $: if (screen === "ready" && (!openScreenLoaded || !memoryLoaded)) {
    if (!openScreenLoaded) {
      openScreenLoaded = true;
      refreshOpenScreen().catch((error) => {
        console.error("OpenScreen scan failed:", error);
      });
    }
    if (!memoryLoaded) {
      memoryLoaded = true;
      refreshMemoryStatus().catch((error) => {
        console.error("Butler recall scan failed:", error);
      });
    }
  }
</script>

<main class="app">
  <div class="shell">
    <div class="eyebrow">aiButler</div>
    <h1>Your Personal Executive Layer</h1>
    <p class="sub">
      Connect voice, grant permissions, store secrets securely, then talk naturally.
    </p>

    <div class="status">
      <span class:ready={runtimeReady}>{runtimeReady ? "Ready" : "Blocked"}</span>
      <span>{status}</span>
    </div>

    {#if screen === "welcome"}
      <section class="panel">
        <h2>1. Connect ElevenLabs</h2>
        <p>
          Open ElevenLabs, create or choose your Conversational AI agent, then paste the API key and agent ID here.
        </p>
        <div class="button-row">
          <button class="secondary" on:click={openElevenLabs}>Open ElevenLabs</button>
        </div>
        <label>
          ElevenLabs API Key
          <input bind:value={apiKey} placeholder="sk_..." type="password" />
        </label>
        <label>
          ElevenLabs Agent ID
          <input bind:value={agentId} placeholder="agent_..." />
        </label>
        <div class="button-row">
          <button class="primary" disabled={saving || !runtimeReady} on:click={saveElevenLabsConfig}>
            {saving ? "Saving..." : "Save And Continue"}
          </button>
        </div>
      </section>
    {/if}

    {#if screen === "permissions"}
      <section class="panel">
        <h2>2. Grant macOS Permissions</h2>
        <p>Butler needs Accessibility and Screen Recording for supervised computer use.</p>
        <div class="button-row stack">
          <button on:click={openAccessibility}>Open Accessibility Settings</button>
          <button on:click={openScreenRecording}>Open Screen Recording Settings</button>
          <button on:click={runPreflight}>Run Computer-Use Preflight</button>
        </div>
        {#if preflightResult}
          <pre>{preflightResult}</pre>
        {/if}
        <div class="button-row">
          <button class="primary" on:click={() => (screen = "secrets")}>Continue</button>
        </div>
      </section>
    {/if}

    {#if screen === "secrets"}
      <section class="panel">
        <h2>3. Capture More Secrets</h2>
        <p>
          Butler can scan your clipboard history for API keys and store them in Keychain so future integrations do not require terminal work.
        </p>
        <div class="button-row">
          <button on:click={autoCaptureSecrets}>Auto-Capture Clipboard Secrets</button>
        </div>
        {#if secretCaptureResult}
          <pre>{secretCaptureResult}</pre>
        {/if}
        <div class="button-row">
          <button class="secondary" on:click={() => (screen = "ready")}>Skip For Now</button>
        </div>
      </section>
    {/if}

    {#if screen === "ready"}
      <section class="panel">
        <h2>Butler Is Ready</h2>
        <p>You can launch the voice loop now and start using Butler without exporting env vars.</p>
        <div class="button-row stack">
          <button class="primary" on:click={startVoice}>Launch Voice Butler</button>
          <button on:click={runDailyBriefing}>Run Daily Executive Briefing</button>
          <button on:click={startBridge} disabled={startingBridge}>
            {startingBridge ? "Starting Phone Bridge..." : "Enable Secure Phone Pairing"}
          </button>
          <button class="secondary" on:click={loadBridgePairing}>Show Pairing Token</button>
          <button class="secondary" on:click={refreshStatus}>Refresh Status</button>
        </div>
        {#if bridgePairing}
          <div class="pairing-box">
            <div class="pairing-label">Phone Pairing</div>
            <div class="pairing-row">
              <span>Bridge URL</span>
              <code>{bridgePairing.url_hint ?? `http://YOUR_MAC_IP:${bridgePairing.port}`}</code>
            </div>
            <div class="pairing-row">
              <span>Pairing token</span>
              <code>{bridgePairing.token}</code>
            </div>
            <p class="pairing-note">
              Keep this token private. The mobile app needs both the bridge URL and pairing token before it can use
              Butler on your Mac.
            </p>
          </div>
        {/if}
        <div class="integration-box">
          <div class="integration-head">
            <div>
              <div class="pairing-label">Pi-Style Core</div>
              <h3>Butler Recall Layer</h3>
            </div>
            <span class="integration-pill" class:ready={memoryStatus?.total_drawers > 0}>
              {memoryStatus?.total_drawers > 0 ? "Warm" : "Cold"}
            </span>
          </div>
          <p>
            Butler stays thin and canonical. MemPalace is the disposable long-horizon recall layer, and the core
            agent routes simple prompts into memory, follow-ups, pending review, or the context map.
          </p>
          <div class="button-row">
            <button class="secondary" on:click={refreshMemoryStatus} disabled={memoryBusy}>
              {memoryBusy ? "Checking Recall..." : "Check Recall Status"}
            </button>
            <button class="secondary" on:click={() => reindexMemory(true)} disabled={memoryBusy}>
              {memoryBusy ? "Indexing..." : "Rebuild Recall Index"}
            </button>
          </div>
          {#if memoryStatus}
            <div class="integration-meta recall-meta">
              <div>
                <span>Indexed memories</span>
                <code>{memoryStatus.total_drawers}</code>
              </div>
              <div>
                <span>Palace path</span>
                <code>{memoryStatus.palace_path}</code>
              </div>
              <div>
                <span>Top wings</span>
                <code>{Object.entries(memoryStatus.wings ?? {}).map(([key, value]) => `${key}:${value}`).join(" • ") || "Not indexed yet"}</code>
              </div>
            </div>
          {/if}
          <label>
            Ask Butler Core
            <input
              bind:value={corePrompt}
              placeholder="What do I know about Ava, who do I owe a reply to, or show my context map?"
              on:keydown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  askCoreAgent();
                }
              }}
            />
          </label>
          <div class="button-row">
            <button class="primary" on:click={askCoreAgent} disabled={coreAgentBusy || !corePrompt.trim()}>
              {coreAgentBusy ? "Asking Butler..." : "Ask Butler Core"}
            </button>
          </div>
          {#if coreAgentResult}
            <div class="session-card recall-card">
              <div class="session-title">{coreAgentResult.mode.replaceAll("_", " ")}</div>
              <div class="recall-summary">{coreAgentResult.summary}</div>
              {#if coreAgentResult.citations?.length}
                <div class="session-list compact">
                  {#each coreAgentResult.citations as item}
                    <div class="session-card result-card">
                      <div class="session-title">{item.title ?? item.ref}</div>
                      <div class="session-sub">{item.ref}</div>
                      {#if item.similarity !== null && item.similarity !== undefined}
                        <div class="session-sub">Similarity: {Math.round(item.similarity * 100)}%</div>
                      {/if}
                      {#if item.subtitle}
                        <div class="search-snippet">{item.subtitle}</div>
                      {/if}
                    </div>
                  {/each}
                </div>
              {/if}
            </div>
          {/if}
          {#if memoryIndexResult}
            <div class="integration-meta recall-meta">
              <div>
                <span>Last index run</span>
                <code>{memoryIndexResult.indexed_documents} docs • {memoryIndexResult.indexed_sheets} sheets • {memoryIndexResult.indexed_events} events</code>
              </div>
            </div>
          {/if}
        </div>
        <div class="integration-box">
          <div class="integration-head">
            <div>
              <div class="pairing-label">OpenScreen Companion</div>
              <h3>Capture Without OBS Bloat</h3>
            </div>
            <span class="integration-pill" class:ready={openScreenStatus?.available}>
              {openScreenStatus?.available ? "Detected" : "Not Found"}
            </span>
          </div>
          <p>
            OpenScreen already covers the part we want from OBS: recording, webcam, system audio, zooms, annotations,
            trimming, and export. Butler links those capture sessions into context without copying the large media
            files.
          </p>
          <div class="button-row">
            <button class="secondary" on:click={refreshOpenScreen} disabled={openScreenBusy}>
              {openScreenBusy ? "Scanning..." : "Scan OpenScreen"}
            </button>
            <button class="secondary" on:click={launchOpenScreen} disabled={openScreenBusy}>Launch OpenScreen</button>
            <button
              class="secondary"
              on:click={importLatestOpenScreen}
              disabled={openScreenBusy || !openScreenStatus?.latest_session}
            >
              Import Latest Capture
            </button>
          </div>
          {#if openScreenStatus}
            <div class="integration-meta">
              <div>
                <span>Recordings</span>
                <code>{openScreenStatus.recordings_dir ?? "Not found yet"}</code>
              </div>
              <div>
                <span>App bundle</span>
                <code>{openScreenStatus.app_bundle_path ?? "Repo or install needed"}</code>
              </div>
              <div>
                <span>Repo</span>
                <code>{openScreenStatus.repo_path ?? "Not found"}</code>
              </div>
              <div>
                <span>Sessions</span>
                <code>{openScreenSessions.length}</code>
              </div>
            </div>
          {/if}
          {#if openScreenSessions.length}
            <div class="session-list">
              {#each openScreenSessions as item}
                <div class="session-card">
                  <div class="session-title">{item.title}</div>
                  <div class="session-sub">{item.recorded_at}</div>
                  <div class="session-sub">
                    Screen: {item.screen_video?.exists ? "linked" : "missing"}
                    {#if item.webcam_video?.path}
                      • Webcam: {item.webcam_video?.exists ? "linked" : "missing"}
                    {/if}
                    {#if item.cursor_telemetry?.sample_count}
                      • Cursor: {item.cursor_telemetry.sample_count} samples
                    {/if}
                  </div>
                  <div class="button-row">
                    <button
                      class="secondary small"
                      on:click={() => importOpenScreenSession(item.session_manifest_path)}
                      disabled={openScreenBusy}
                    >
                      Import This Capture
                    </button>
                  </div>
                </div>
              {/each}
            </div>
          {/if}
          {#if openScreenImportResult}
            <div class="integration-meta">
              <div>
                <span>Artifact ref</span>
                <code>{openScreenImportResult.artifact_ref}</code>
              </div>
              <div>
                <span>Artifact sheet</span>
                <code>{openScreenImportResult.artifact_sheet?.path}</code>
              </div>
              <div>
                <span>Pending review</span>
                <code>{openScreenImportResult.pending_item?.path ?? "Not needed"}</code>
              </div>
            </div>
          {/if}
        </div>
      </section>
    {/if}
  </div>
</main>

<style>
  :global(body) {
    margin: 0;
    background:
      radial-gradient(circle at top left, rgba(0, 255, 157, 0.14), transparent 35%),
      radial-gradient(circle at top right, rgba(0, 140, 255, 0.12), transparent 35%),
      linear-gradient(180deg, #090a10 0%, #0f1118 100%);
    color: #edf1f7;
    font-family: "SF Pro Display", "Segoe UI", sans-serif;
  }

  .app {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px 24px;
  }

  .shell {
    width: min(680px, 100%);
  }

  .eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.16em;
    font-size: 0.8rem;
    color: #7d889a;
    margin-bottom: 10px;
  }

  h1 {
    margin: 0;
    font-size: clamp(2.3rem, 5vw, 4rem);
    line-height: 0.98;
    background: linear-gradient(135deg, #f7fafc 0%, #9ef6d1 42%, #7cd9ff 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .sub {
    margin: 14px 0 24px;
    color: #98a3b3;
    font-size: 1.05rem;
    max-width: 52ch;
  }

  .status {
    display: flex;
    gap: 12px;
    align-items: center;
    padding: 12px 14px;
    margin-bottom: 22px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.04);
    color: #c4ccda;
    font-size: 0.95rem;
  }

  .status span:first-child {
    border-radius: 999px;
    padding: 4px 10px;
    background: rgba(255, 120, 120, 0.14);
    color: #ffb6b6;
    font-weight: 700;
    text-transform: uppercase;
    font-size: 0.72rem;
    letter-spacing: 0.08em;
  }

  .status span:first-child.ready {
    background: rgba(0, 255, 157, 0.12);
    color: #9ef6d1;
  }

  .panel {
    border-radius: 24px;
    padding: 28px;
    background: rgba(16, 18, 27, 0.82);
    border: 1px solid rgba(255, 255, 255, 0.08);
    box-shadow: 0 28px 90px rgba(0, 0, 0, 0.35);
    backdrop-filter: blur(18px);
  }

  h2 {
    margin: 0 0 10px;
    font-size: 1.4rem;
  }

  p {
    color: #a2adbc;
    line-height: 1.5;
  }

  label {
    display: block;
    margin-top: 16px;
    font-size: 0.9rem;
    color: #cad3df;
  }

  input {
    width: 100%;
    box-sizing: border-box;
    margin-top: 8px;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    background: rgba(255, 255, 255, 0.04);
    color: #eef5ff;
    padding: 14px 16px;
    font-size: 1rem;
  }

  .button-row {
    display: flex;
    gap: 12px;
    margin-top: 22px;
    flex-wrap: wrap;
  }

  .button-row.stack {
    flex-direction: column;
  }

  button {
    border: 0;
    border-radius: 14px;
    padding: 14px 18px;
    font-size: 0.98rem;
    font-weight: 700;
    cursor: pointer;
    color: #0b0d12;
    background: linear-gradient(135deg, #9ef6d1 0%, #7cd9ff 100%);
  }

  button.secondary {
    background: rgba(255, 255, 255, 0.08);
    color: #edf1f7;
    border: 1px solid rgba(255, 255, 255, 0.08);
  }

  button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  pre {
    margin-top: 18px;
    padding: 14px;
    max-height: 180px;
    overflow: auto;
    border-radius: 12px;
    background: #0a0c12;
    color: #9ef6d1;
    border: 1px solid rgba(255, 255, 255, 0.06);
    font-size: 0.78rem;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .pairing-box {
    margin-top: 20px;
    padding: 18px;
    border-radius: 16px;
    background: #0a0d15;
    border: 1px solid rgba(255, 255, 255, 0.08);
  }

  .pairing-label {
    margin-bottom: 12px;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #7cd9ff;
  }

  .pairing-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 12px;
    color: #b9c5d7;
  }

  code {
    padding: 10px 12px;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.04);
    color: #9ef6d1;
    font-size: 0.84rem;
    word-break: break-all;
  }

  .pairing-note {
    margin: 0;
    color: #8e99ab;
    font-size: 0.9rem;
  }

  h3 {
    margin: 0;
    font-size: 1.05rem;
  }

  .integration-box {
    margin-top: 20px;
    padding: 20px;
    border-radius: 18px;
    background: linear-gradient(180deg, rgba(14, 17, 25, 0.92), rgba(10, 12, 19, 0.96));
    border: 1px solid rgba(124, 217, 255, 0.14);
  }

  .integration-head {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: flex-start;
  }

  .integration-pill {
    border-radius: 999px;
    padding: 6px 12px;
    background: rgba(255, 120, 120, 0.14);
    color: #ffb6b6;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .integration-pill.ready {
    background: rgba(0, 255, 157, 0.12);
    color: #9ef6d1;
  }

  .integration-meta {
    display: grid;
    gap: 10px;
    margin-top: 18px;
  }

  .integration-meta div {
    display: grid;
    gap: 6px;
  }

  .integration-meta span {
    font-size: 0.82rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #7d889a;
  }

  .recall-meta {
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  }

  .session-list {
    display: grid;
    gap: 12px;
    margin-top: 18px;
  }

  .session-list.compact {
    margin-top: 14px;
  }

  .session-card {
    padding: 14px;
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.07);
  }

  .session-title {
    font-weight: 700;
    color: #edf1f7;
  }

  .session-sub {
    margin-top: 6px;
    color: #9aa6b7;
    font-size: 0.9rem;
  }

  .recall-card {
    margin-top: 18px;
  }

  .recall-summary {
    margin-top: 8px;
    color: #d8e0ec;
    white-space: pre-wrap;
    line-height: 1.5;
  }

  .result-card {
    background: rgba(255, 255, 255, 0.03);
  }

  .search-snippet {
    margin-top: 8px;
    color: #c5cfdd;
    font-size: 0.92rem;
    line-height: 1.45;
    white-space: pre-wrap;
  }

  button.small {
    padding: 10px 14px;
    font-size: 0.88rem;
  }
</style>
