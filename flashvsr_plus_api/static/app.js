const $ = (id) => document.getElementById(id);

const state = {
  file: null,
  upload: null,
  selection: null,
  mode: "turbo",
  availableModes: [],
  activeJobId: null,
  pollTimer: null,
  previewUrl: null,
};

const els = {
  serviceStatus: $("serviceStatus"), fileInput: $("fileInput"), dropzone: $("dropzone"),
  uploadProgress: $("uploadProgress"), uploadLabel: $("uploadLabel"), uploadPercent: $("uploadPercent"), uploadBar: $("uploadBar"),
  fileCard: $("fileCard"), videoPreview: $("videoPreview"), fileName: $("fileName"), fileSize: $("fileSize"), replaceFile: $("replaceFile"),
  validation: $("validation"), sourceMeta: $("sourceMeta"), sourceResolution: $("sourceResolution"), sourceFrames: $("sourceFrames"), sourceFps: $("sourceFps"), sourceDuration: $("sourceDuration"),
  settingsEmpty: $("settingsEmpty"), jobForm: $("jobForm"), scaleOptions: $("scaleOptions"),
  baseModeOption: $("baseModeOption"),
  customWidth: $("customWidth"), customHeight: $("customHeight"), useCustom: $("useCustom"), customHint: $("customHint"),
  frameLimitRow: $("frameLimitRow"), frameLimit: $("frameLimit"), frameLimitTitle: $("frameLimitTitle"), frameLimitHint: $("frameLimitHint"),
  outputResolution: $("outputResolution"), outputProfile: $("outputProfile"), startButton: $("startButton"),
  taskPanel: $("taskPanel"), taskSubtitle: $("taskSubtitle"), taskState: $("taskState"), taskBar: $("taskBar"), taskPercent: $("taskPercent"), stageText: $("stageText"),
  resultMetrics: $("resultMetrics"), cancelButton: $("cancelButton"), downloadButton: $("downloadButton"), newTaskButton: $("newTaskButton"),
};

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes, index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return `${value.toFixed(index ? 1 : 0)} ${units[index]}`;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) return "—";
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return mins ? `${mins}分 ${secs}秒` : `${secs} 秒`;
}

function errorMessage(payload, fallback = "操作失败") {
  if (!payload) return fallback;
  if (typeof payload.detail === "string") return payload.detail;
  return fallback;
}

async function checkService() {
  try {
    const response = await fetch("/readyz", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok || data.status !== "ready") throw new Error("not ready");
    els.serviceStatus.className = "service-status ready";
    els.serviceStatus.lastElementChild.textContent = data.model_loaded ? "GPU 就绪 · 模型已加载" : "GPU 就绪";
    state.availableModes = data.available_modes || [];
    syncModeControls();
  } catch (_) {
    els.serviceStatus.className = "service-status error";
    els.serviceStatus.lastElementChild.textContent = "服务暂不可用";
  }
}

function syncModeControls() {
  const locked = Boolean(state.activeJobId);
  document.querySelectorAll('input[name="mode"]').forEach((input) => {
    const available = input.value === "turbo" || state.availableModes.includes(input.value);
    input.disabled = locked || !available;
    input.closest("label")?.classList.toggle("disabled", input.disabled);
  });
}

function setValidation(messages, kind = "ok") {
  els.validation.className = `validation ${kind === "ok" ? "" : kind}`.trim();
  els.validation.replaceChildren();
  const list = Array.isArray(messages) ? messages : [messages];
  if (list.length > 1) {
    const ul = document.createElement("ul");
    list.forEach((message) => { const li = document.createElement("li"); li.textContent = message; ul.append(li); });
    els.validation.append(ul);
  } else {
    els.validation.textContent = list[0];
  }
  els.validation.classList.remove("hidden");
}

function resetUploadView() {
  state.file = null; state.upload = null; state.selection = null;
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = null;
  els.fileInput.value = "";
  els.dropzone.classList.remove("hidden");
  els.fileCard.classList.add("hidden");
  els.uploadProgress.classList.add("hidden");
  els.validation.classList.add("hidden");
  els.sourceMeta.classList.add("hidden");
  els.jobForm.classList.add("hidden");
  els.settingsEmpty.classList.remove("hidden");
}

function showFile(file) {
  els.dropzone.classList.add("hidden");
  els.fileCard.classList.remove("hidden");
  els.fileName.textContent = file.name;
  els.fileSize.textContent = formatBytes(file.size);
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = URL.createObjectURL(file);
  els.videoPreview.src = state.previewUrl;
}

function uploadFile(file) {
  state.file = file;
  showFile(file);
  els.uploadProgress.classList.remove("hidden");
  els.uploadLabel.textContent = "正在上传并检查视频";
  els.uploadPercent.textContent = "0%";
  els.uploadBar.style.width = "0%";
  els.validation.classList.add("hidden");

  const xhr = new XMLHttpRequest();
  xhr.open("POST", `/api/uploads?filename=${encodeURIComponent(file.name)}`);
  xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
  xhr.upload.onprogress = (event) => {
    if (!event.lengthComputable) return;
    const percent = Math.min(99, Math.round(event.loaded / event.total * 100));
    els.uploadPercent.textContent = `${percent}%`;
    els.uploadBar.style.width = `${percent}%`;
  };
  xhr.onload = () => {
    let payload = null;
    try { payload = JSON.parse(xhr.responseText); } catch (_) { /* no-op */ }
    if (xhr.status < 200 || xhr.status >= 300) {
      els.uploadProgress.classList.add("hidden");
      setValidation(errorMessage(payload, "上传或视频检查失败"), "error");
      return;
    }
    els.uploadPercent.textContent = "100%";
    els.uploadBar.style.width = "100%";
    els.uploadLabel.textContent = "上传完成";
    window.setTimeout(() => els.uploadProgress.classList.add("hidden"), 500);
    state.upload = payload;
    renderAnalysis(payload);
  };
  xhr.onerror = () => {
    els.uploadProgress.classList.add("hidden");
    setValidation("网络连接中断，请重试。", "error");
  };
  xhr.send(file);
}

function renderAnalysis(data) {
  const source = data.source;
  els.sourceResolution.textContent = `${source.width} × ${source.height}`;
  els.sourceFrames.textContent = `${source.frames} 帧`;
  els.sourceFps.textContent = `${source.fps.toFixed(2)} FPS`;
  els.sourceDuration.textContent = formatDuration(source.duration_seconds);
  els.sourceMeta.classList.remove("hidden");

  if (data.warnings.length) setValidation(data.warnings, "warning");
  else setValidation("视频检查通过，可以开始配置超分任务。", "ok");

  els.scaleOptions.replaceChildren();
  const resolutionOptions = data.resolution_options || data.options;
  resolutionOptions.forEach((option) => {
    const label = document.createElement("label");
    label.className = `scale-option${option.allowed ? "" : " disabled"}`;
    const input = document.createElement("input");
    input.type = "radio"; input.name = "scale"; input.value = option.label || option.scale; input.disabled = !option.allowed;
    const copy = document.createElement("span");
    const title = document.createElement("b"); title.textContent = option.label || `${option.scale}×`;
    const detail = document.createElement("small");
    detail.textContent = `${option.width} × ${option.height}`;
    if (option.model_width !== option.width || option.model_height !== option.height) {
      detail.textContent += ` · 内部 ${option.model_width} × ${option.model_height}`;
    }
    copy.append(title, detail); label.append(input, copy); els.scaleOptions.append(label);
    input.addEventListener("change", () => selectOption({ ...option, custom: false }));
  });

  const allowed = resolutionOptions.filter((item) => item.allowed);
  const preferred = allowed.find((item) => item.height === 1080) || allowed[0];
  if (preferred) {
    const input = [...els.scaleOptions.querySelectorAll("input")].find((item) => item.value === (preferred.label || String(preferred.scale)));
    input.checked = true;
    selectOption({ ...preferred, custom: false, resolutionPreset: true });
  } else {
    state.selection = null;
    els.outputResolution.textContent = "需要自定义";
    els.outputProfile.textContent = "展开自定义尺寸，使用系统建议值";
  }

  const suggestion = data.custom_suggestion;
  els.customWidth.value = suggestion.width;
  els.customHeight.value = suggestion.height;
  els.customHint.textContent = `建议 ${suggestion.width} × ${suggestion.height}：${suggestion.reason}。`;
  els.frameLimitRow.classList.toggle(
    "hidden",
    !(data.offers_frame_limit || data.requires_frame_limit),
  );
  els.frameLimit.checked = false;
  els.frameLimitTitle.textContent = `仅处理开头 ${data.limits.max_frames} 帧（可选）`;
  els.frameLimitHint.textContent = `不勾选将处理完整视频；勾选时约处理 ${formatDuration(data.limits.max_frames / source.fps)}，适合快速预览。`;
  els.settingsEmpty.classList.add("hidden");
  els.jobForm.classList.remove("hidden");
  updateStartState();
}

function selectOption(option) {
  state.selection = option;
  els.outputResolution.textContent = `${option.width} × ${option.height}`;
  const modelWidth = option.model_width || Math.ceil(option.width / 128) * 128;
  const modelHeight = option.model_height || Math.ceil(option.height / 128) * 128;
  const paddingNote = (modelWidth !== option.width || modelHeight !== option.height)
    ? `最终画面不裁切；模型内部补边至 ${modelWidth} × ${modelHeight}，输出时去除补边。`
    : "无需内部补边。";
  els.outputProfile.textContent = `${option.profile || "自定义输出尺寸"} · ${paddingNote}`;
  updateStartState();
}

function updateStartState() {
  els.startButton.disabled = !state.selection;
}

function stageProgress(stage, status, processedFrames, mode) {
  const modelName = mode === "base" ? "Base" : mode === "v1" ? "V1" : "Turbo";
  if (status === "queued") return { percent: 4, text: "等待 GPU 队列" };
  if (stage === "loading_model") return { percent: 9, text: `正在加载 ${modelName} 模型` };
  if (stage === "inference") return { percent: 18, text: "正在执行超分推理" };
  if (/input/i.test(stage)) return { percent: 15, text: "正在预处理输入视频" };
  if (/KV cache/i.test(stage)) return { percent: 25, text: "正在规划 GPU 缓存" };
  const match = stage.match(/Decode segment (\d+)\/(\d+)/i);
  if (match) {
    const current = Number(match[1]), total = Number(match[2]);
    return { percent: Math.round(30 + current / total * 58), text: `正在解码输出片段 ${current}/${total}` };
  }
  const streamingMatch = stage.match(/Decode segment (\d+)\s/i);
  if (streamingMatch && processedFrames) {
    const current = Number(streamingMatch[1]);
    const total = Math.max(current, Math.ceil(processedFrames / 16));
    return { percent: Math.round(30 + current / total * 58), text: `正在解码输出片段 ${current}/${total}` };
  }
  if (/DiT stream/i.test(stage)) return { percent: 72, text: "核心推理完成，正在解码" };
  if (/TinyDecoder/i.test(stage)) return { percent: 90, text: "解码完成，正在封装视频" };
  if (/Color correction/i.test(stage)) return { percent: 94, text: "正在校正色彩" };
  if (/Video saved/i.test(stage)) return { percent: 97, text: "正在写入输出文件" };
  if (status === "completed") return { percent: 100, text: "处理完成" };
  return { percent: 22, text: stage || "正在处理" };
}

function setTaskProgress(percent, text) {
  els.taskBar.style.width = `${percent}%`;
  els.taskPercent.textContent = `${percent}%`;
  els.stageText.textContent = text;
}

async function createJob(event) {
  event.preventDefault();
  if (!state.upload || !state.selection || els.startButton.disabled) return;
  els.startButton.disabled = true;
  const checkedMode = document.querySelector('input[name="mode"]:checked');
  state.mode = checkedMode?.value || state.mode;
  const body = {
    upload_id: state.upload.upload_id,
    scale: state.selection.scale || 1,
    mode: state.mode,
  };
  if (state.selection.width && state.selection.height) {
    body.width = state.selection.width;
    body.height = state.selection.height;
  }
  if (els.frameLimit.checked) body.frame_limit = state.upload.limits.max_frames;
  try {
    const response = await fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await response.json();
    if (!response.ok) throw new Error(errorMessage(data, "任务提交失败"));
    showTask(data);
    pollJob(data.id);
  } catch (error) {
    setValidation(error.message, "error");
    els.startButton.disabled = false;
  }
}

function showTask(job) {
  state.activeJobId = job.id;
  syncModeControls();
  els.taskPanel.classList.remove("hidden");
  els.taskPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  els.taskSubtitle.textContent = `${job.target.width} × ${job.target.height} · ${job.processed_frames} 帧 · ${job.mode === "base" ? "Base" : "Turbo"}`;
  els.taskState.className = "task-state";
  els.taskState.textContent = "排队中";
  els.resultMetrics.classList.add("hidden");
  els.downloadButton.classList.add("hidden");
  els.newTaskButton.classList.add("hidden");
  els.cancelButton.classList.remove("hidden");
  els.cancelButton.disabled = false;
  els.cancelButton.textContent = "取消任务";
  els.cancelButton.dataset.jobId = job.id;
  setTaskProgress(4, "等待 GPU 队列");
}

async function pollJob(jobId) {
  window.clearTimeout(state.pollTimer);
  try {
    const response = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
    const job = await response.json();
    if (!response.ok) throw new Error(errorMessage(job, "无法读取任务状态"));
    renderJob(job);
    if (!["completed", "failed", "cancelled"].includes(job.status)) {
      state.pollTimer = window.setTimeout(() => pollJob(jobId), 1200);
    }
  } catch (error) {
    els.stageText.textContent = `${error.message}，正在重试…`;
    state.pollTimer = window.setTimeout(() => pollJob(jobId), 2500);
  }
}

function renderJob(job) {
  const modelName = job.mode === "base" ? "Base" : job.mode === "v1" ? "V1" : "Turbo";
  els.taskSubtitle.textContent = `${job.target.width} × ${job.target.height} · ${job.processed_frames} 帧 · ${modelName}`;
  if (job.status === "completed") {
    state.activeJobId = null;
    syncModeControls();
    setTaskProgress(100, "处理完成，可以下载");
    els.taskState.textContent = "已完成";
    els.taskState.className = "task-state success";
    els.cancelButton.classList.add("hidden");
    els.downloadButton.href = `/api/jobs/${job.id}/download`;
    els.downloadButton.classList.remove("hidden");
    els.newTaskButton.classList.remove("hidden");
    renderMetrics(job);
    return;
  }
  if (job.status === "failed" || job.status === "cancelled") {
    state.activeJobId = null;
    syncModeControls();
    const cancelled = job.status === "cancelled";
    setTaskProgress(cancelled ? 0 : 100, cancelled ? "任务已取消" : (job.error || "处理失败"));
    els.taskState.textContent = cancelled ? "已取消" : "失败";
    els.taskState.className = "task-state failure";
    els.cancelButton.classList.add("hidden");
    els.newTaskButton.classList.remove("hidden");
    return;
  }
  if (job.cancel_requested) {
    els.cancelButton.disabled = true;
    els.cancelButton.textContent = "已请求取消";
  }
  const progress = stageProgress(job.stage, job.status, job.processed_frames, job.mode);
  setTaskProgress(progress.percent, progress.text);
  els.taskState.textContent = job.status === "queued" ? "排队中" : "处理中";
}

function renderMetrics(job) {
  const metrics = job.metrics || {};
  const items = [
    ["总耗时", Number.isFinite(metrics.seconds) ? `${metrics.seconds.toFixed(1)} 秒` : "—"],
    ["处理速度", Number.isFinite(metrics.frames_per_second) ? `${metrics.frames_per_second.toFixed(2)} FPS` : "—"],
    ["峰值显存", Number.isFinite(metrics.gpu_peak_memory_allocated_mib) ? `${(metrics.gpu_peak_memory_allocated_mib / 1024).toFixed(2)} GiB` : "—"],
    ["输出大小", formatBytes(job.output_bytes)],
  ];
  els.resultMetrics.replaceChildren();
  items.forEach(([label, value]) => {
    const box = document.createElement("div");
    const name = document.createElement("span"); name.textContent = label;
    const result = document.createElement("strong"); result.textContent = value;
    box.append(name, result); els.resultMetrics.append(box);
  });
  els.resultMetrics.classList.remove("hidden");
}

els.fileInput.addEventListener("change", () => { if (els.fileInput.files[0]) uploadFile(els.fileInput.files[0]); });
els.dropzone.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); els.fileInput.click(); } });
["dragenter", "dragover"].forEach((name) => els.dropzone.addEventListener(name, (event) => { event.preventDefault(); els.dropzone.classList.add("dragging"); }));
["dragleave", "drop"].forEach((name) => els.dropzone.addEventListener(name, (event) => { event.preventDefault(); els.dropzone.classList.remove("dragging"); }));
els.dropzone.addEventListener("drop", (event) => { if (event.dataTransfer.files[0]) uploadFile(event.dataTransfer.files[0]); });
els.replaceFile.addEventListener("click", () => { resetUploadView(); els.fileInput.click(); });
els.frameLimit.addEventListener("change", updateStartState);
document.querySelectorAll('input[name="mode"]').forEach((input) => {
  input.addEventListener("change", () => { if (input.checked) state.mode = input.value; });
});
els.useCustom.addEventListener("click", () => {
  const width = Math.ceil(Number(els.customWidth.value) / 2) * 2;
  const height = Math.ceil(Number(els.customHeight.value) / 2) * 2;
  if (!width || !height || width < 128 || height < 128) { els.customHint.textContent = "请输入有效的宽度和高度。"; return; }
  const modelWidth = Math.ceil(width / 128) * 128;
  const modelHeight = Math.ceil(height / 128) * 128;
  if (modelWidth * modelHeight > state.upload.limits.max_target_pixels) { els.customHint.textContent = `内部对齐尺寸 ${modelWidth} × ${modelHeight} 超过 ${(state.upload.limits.max_target_pixels / 1e6).toFixed(2)} MP 上限，请降低尺寸。`; return; }
  els.customWidth.value = width; els.customHeight.value = height;
  els.scaleOptions.querySelectorAll("input").forEach((input) => { input.checked = false; });
  selectOption({ custom: true, scale: 1, width, height, model_width: modelWidth, model_height: modelHeight, profile: "自定义输出尺寸" });
  els.customHint.textContent = `最终输出 ${width} × ${height}；模型内部补边至 ${modelWidth} × ${modelHeight}。`;
});
els.jobForm.addEventListener("submit", createJob);
els.cancelButton.addEventListener("click", async () => {
  const jobId = els.cancelButton.dataset.jobId;
  if (!jobId) return;
  els.cancelButton.disabled = true;
  try { await fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" }); } finally { els.cancelButton.disabled = false; pollJob(jobId); }
});
els.newTaskButton.addEventListener("click", () => {
  window.clearTimeout(state.pollTimer);
  els.taskPanel.classList.add("hidden");
  resetUploadView();
  window.scrollTo({ top: 0, behavior: "smooth" });
});

checkService();
window.setInterval(checkService, 30000);
