# 中国网络环境部署指南

本文介绍如何在中国网络环境中部署 FlashVSR+。仓库提供 uv 锁定环境、国内
PyPI 与 hf-mirror 配置、模型下载和校验脚本、单 GPU FastAPI 任务队列、网页
工作台以及 tmux 进程管理脚本。

## 环境与镜像

国内 PyPI、ModelScope 和 hf-mirror 默认直连；仅访问受限的 GitHub/Hugging
Face CDN 时，才临时使用用户自行配置的代理。真实代理地址只应保存在本地
`.env`，不要提交到公开仓库。安装前执行：

```bash
cd FlashVSR_Plus
source scripts/configure_china_mirrors.sh
scripts/bootstrap_uv.sh
```

脚本优先调用 `chsrc`（若已安装），同时显式设置清华 PyPI 和 hf-mirror；
只有设置 `FLASHVSR_USE_PROXY=1` 的单条命令才会导出代理变量；代理地址从
`FLASHVSR_PROXY_URL` 或标准 `HTTP_PROXY`/`HTTPS_PROXY` 变量读取。

安装脚本还会把仓库自带的 Triton block-sparse attention 作为可编辑包装入
`.venv`。该算子不需要本地 `nvcc` 编译；锁定环境使用 PyTorch
`2.6.0+cu124`，宿主机只需提供兼容的 NVIDIA 驱动。

## 模型

FlashVSR+ 官方权重仓库是 `ruchangyao/FlashVSR_plus`，其中同时包含 Turbo
和 Base 权重。下载脚本默认使用 `HF_ENDPOINT=https://hf-mirror.com`；如果有
可用的 ModelScope 镜像，可通过 `--modelscope-id` 切换：

```bash
uv run python scripts/download_flashvsr_plus.py --mode turbo
# 全量（约 13 GB，含 turbo/base 两套 DiT 和投影）
uv run python scripts/download_flashvsr_plus.py --mode all
# 若 hf-mirror 被重定向到无法直连的 CDN，再仅给该命令加代理：
FLASHVSR_USE_PROXY=1 FLASHVSR_PROXY_URL=http://proxy-host:7890 \
  uv run python scripts/download_flashvsr_plus.py --mode turbo
```

下载后的布局：

```text
ckpts/TCDecoder.ckpt
ckpts/Wan2.1_VAE.pth
ckpts/turbo/{dit,lq_proj_in}.safetensors
ckpts/base/{dit,lq_proj_in}.safetensors
```

下载器默认设置 `HF_HUB_DISABLE_XET=1`，通过普通 HTTPS/LFS 获取文件，避免
部分镜像环境下的 Xet 鉴权问题。API `/readyz` 只列出本地实际已安装的模式，
网页会据此启用 Turbo/Base 选择。

## 启动与停止

```bash
cp -n .env.example .env
scripts/start_api_tmux.sh
tmux attach -t flashvsr-plus-api
```

启动后在同一内网浏览器访问：

```text
http://SERVER_IP:18303/
```

网页上传目录为 `runtime/api/uploads/`，输出目录为 `runtime/api/outputs/`。默认
允许最大 8 GiB 上传、快速预览可截取开头 300 帧、目标像素不超过 8,294,400；可在 `.env`
中通过 `FLASHVSR_PLUS_MAX_UPLOAD_BYTES`、`FLASHVSR_PLUS_MAX_FRAMES` 和
`FLASHVSR_PLUS_MAX_TARGET_PIXELS` 调整。网页会先探测视频并只开放满足限制的
目标清晰度；网页以输出高度为主选项，提供 720p、1080p、2048p，并根据输入
视频宽高比自动计算偶数宽度。长视频默认处理完整内容；“仅处理开头 300 帧”是
可选的快速预览开关，不勾选即可提交完整视频。长视频会增加总耗时和输出存储，
但分段解码时显存主要由目标分辨率和分段大小决定，不随视频总帧数线性增长。
最终输出尺寸不要求是
128 的倍数：服务会在模型输入阶段居中补边到 128 对齐画布，并在编码前裁掉
补边，因此不会因为模型约束改变用户选择的最终宽高比。

停止或查看日志：

```bash
scripts/status_api_tmux.sh
scripts/stop_api_tmux.sh
tail -f runtime/api/server.log
```

## 基准测试

先确认 GPU：

```bash
nvidia-smi
uv run python scripts/check_deployment.py
```

使用真实视频跑显存/耗时报告：

```bash
uv run python scripts/benchmark_flashvsr_plus.py \
  --input examples/case_0.mp4 --output runtime/bench/case_0_turbo.mp4 \
  --mode turbo --height 1024 --width 1920 --max-frames 25 \
  --json runtime/bench/case_0_turbo.json
```

脚本记录总耗时、FPS、`max_memory_allocated`、`max_memory_reserved` 以及
pipeline 元数据。报告必须标注 GPU 型号、驱动、PyTorch/CUDA、输入尺寸、帧数、
attention backend 和 decoder 模式；不要把不同分辨率的显存数字直接横向比较。
