#!/usr/bin/env bash
set -euo pipefail

# Domestic services are deliberately direct by default. Set
# FLASHVSR_USE_PROXY=1 only for a command that must reach a blocked external
# endpoint (for example a GitHub release asset), and provide the proxy through
# FLASHVSR_PROXY_URL or the standard HTTP_PROXY/HTTPS_PROXY variables.
export UV_INDEX_URL="${UV_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
export UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-$UV_INDEX_URL}"
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
if [[ "${FLASHVSR_USE_PROXY:-0}" == "1" ]]; then
  proxy_url="${FLASHVSR_PROXY_URL:-${HTTPS_PROXY:-${HTTP_PROXY:-}}}"
  if [[ -z "$proxy_url" ]]; then
    echo "FLASHVSR_USE_PROXY=1 requires FLASHVSR_PROXY_URL or HTTP(S)_PROXY" >&2
    return 1 2>/dev/null || exit 1
  fi
  export HTTP_PROXY="${HTTP_PROXY:-$proxy_url}"
  export HTTPS_PROXY="${HTTPS_PROXY:-$proxy_url}"
  export ALL_PROXY="${ALL_PROXY:-$proxy_url}"
else
  unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy || true
fi

if command -v chsrc >/dev/null 2>&1; then
  # chsrc changes user-level package-manager configuration. Ignore a source
  # that is unavailable and retain the explicit environment variables above.
  chsrc set pip tuna 2>/dev/null || true
  chsrc set uv tuna 2>/dev/null || true
fi

printf 'UV_INDEX_URL=%s\n' "$UV_INDEX_URL"
printf 'UV_DEFAULT_INDEX=%s\n' "$UV_DEFAULT_INDEX"
printf 'HF_ENDPOINT=%s\n' "$HF_ENDPOINT"
printf 'HTTP_PROXY=%s\n' "${HTTP_PROXY-}"
printf 'HTTPS_PROXY=%s\n' "${HTTPS_PROXY-}"
printf 'ALL_PROXY=%s\n' "${ALL_PROXY-}"
