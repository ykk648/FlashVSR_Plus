# FlashVSR+ FastAPI 服务

服务是单进程、单 GPU 队列。模型只在第一个任务到来时加载，避免多个
uvicorn worker 重复占用 24 GB 显存；远程运行统一放在 tmux 中。

## 启动

```bash
cd FlashVSR_Plus
cp -n .env.example .env
uv run flashvsr-plus-api --host 0.0.0.0 --port 18303 --device cuda:0
```

推荐使用：

```bash
scripts/start_api_tmux.sh
tmux attach -t flashvsr-plus-api
```

浏览器工作台：`http://SERVER_IP:18303/`。接口文档：
`http://SERVER_IP:18303/docs`。服务默认不提供用户鉴权；若要暴露
到公网，应放在带鉴权和上传限速的反向代理后。

网页支持拖放上传、输入检查、720p/1080p/2048p 目标高度、自定义尺寸、保持宽高比的内部补边、超帧数截断选项、任务进度、
显存与耗时结果、Turbo/Base 模型选择以及 MP4 下载。上传文件保存在 `runtime/api/uploads/`，不会在
任务结束后立即删除，便于重试；需要按服务器存储策略定期清理。

## 接口

浏览器使用原始请求体上传文件，不依赖 multipart：

```bash
curl -sS -X POST \
  'http://127.0.0.1:18303/api/uploads?filename=case_0.mp4' \
  -H 'Content-Type: video/mp4' \
  --data-binary @examples/case_0.mp4
```

返回 `upload_id`、视频元数据、限制提示、720p/1080p/2048p 对应的最终输出
尺寸、兼容旧调用的倍率方案，以及模型内部
128 对齐画布。非 128 倍数的最终尺寸使用边缘补边参与推理，写出视频时去掉
补边，不会为满足模型对齐要求而裁掉原画面。使用
`upload_id` 提交任务：

```bash
curl -sS http://127.0.0.1:18303/api/jobs \
  -H 'Content-Type: application/json' \
  -d '{"upload_id":"UPLOAD_ID","scale":2,"mode":"turbo"}'
```

服务器内部调用仍可使用 allowlist 内的本地路径：

```bash
curl -sS http://127.0.0.1:18303/api/jobs \
  -H 'Content-Type: application/json' \
  -d '{"input_path":"/absolute/path/to/FlashVSR_Plus/examples/case_0.mp4","scale":2,"mode":"turbo"}'
```

返回 `202` 和任务 ID。查询、取消、下载：

```bash
curl -sS http://127.0.0.1:18303/api/jobs/JOB_ID
curl -sS -X POST http://127.0.0.1:18303/api/jobs/JOB_ID/cancel
curl -OJ http://127.0.0.1:18303/api/jobs/JOB_ID/download
```

端点：

- `GET /healthz`：进程存活检查。
- `GET /readyz`：worker、CUDA 和当前 resident 模型状态；无 CUDA 时返回 `degraded`，便于诊断容器权限。
- `/readyz` 的 `available_modes` 只包含已下载权重的模式，网页据此启用模型选项。
- `POST /api/uploads?filename=...`：上传并探测视频，默认单文件上限 8 GiB。
- `POST /api/jobs`：`upload_id` 与 `input_path` 二选一；支持 `scale`、`mode`，也可以显式给 `width`、`height`。默认处理完整视频；只有显式给 `frame_limit` 才会截取开头部分，当前上限由 `FLASHVSR_PLUS_MAX_FRAMES` 控制（默认 300，供快速预览使用）。
- `GET /api/jobs/{id}`、`POST /api/jobs/{id}/cancel`、`GET /api/jobs/{id}/download`。

输出 MP4 保留输入 FPS 和音频（由上游 pipeline 的 ffmpeg remux 完成）。
