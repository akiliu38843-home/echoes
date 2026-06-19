"""LLM client thin wrapper. 默认走 uyilink proxy（OpenAI 兼容）。

环境变量：
  OPENAI_API_KEY            — 代理 key
  OPENAI_BASE_URL           — 代理 base URL（默认 https://sz.uyilink.com/v1）
  HINDCAST_MODEL            — 模型 ID（默认 gpt-5.4-mini）
  HINDCAST_MAX_TOKENS       — 单次输出上限（默认 600）
  HINDCAST_RETRIES          — 重试次数（默认 3）

未来切回 Claude 时改这里即可。
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from openai import OpenAI


DEFAULT_BASE_URL = "https://sz.uyilink.com/v1"
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_MAX_TOKENS = 600
DEFAULT_RETRIES = 3
RETRY_BACKOFF_SEC = 5


def get_client() -> OpenAI:
    """构建 OpenAI client，自动剥离 socks proxy（避免 504）。"""
    # 临时清理 proxy env vars（uyilink 国内端点不需代理）
    for var in ("ALL_PROXY", "all_proxy", "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        os.environ.pop(var, None)

    base_url = os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    return OpenAI(base_url=base_url)


def chat_json(
    client: OpenAI,
    system: str,
    user: str,
    model: str | None = None,
    max_tokens: int | None = None,
    retries: int | None = None,
) -> dict[str, Any]:
    """调用 LLM 并解析 JSON 输出。失败重试 + 容错。

    Returns:
        dict — 解析后的 JSON，含 `_failed` / `_error` 字段如果全部重试失败
    """
    model = model or os.getenv("HINDCAST_MODEL", DEFAULT_MODEL)
    max_tokens = max_tokens or int(os.getenv("HINDCAST_MAX_TOKENS", DEFAULT_MAX_TOKENS))
    retries = retries or int(os.getenv("HINDCAST_RETRIES", DEFAULT_RETRIES))

    last_err = None
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                timeout=120,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.strip("`").lstrip("json").strip()
            return json.loads(raw)
        except json.JSONDecodeError as e:
            return {"_failed": True, "_error": f"json_decode: {e}", "_raw": raw[:300]}
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(RETRY_BACKOFF_SEC * (attempt + 1))

    return {"_failed": True, "_error": str(last_err)[:200]}


def chat_text(
    client: OpenAI,
    system: str,
    user: str,
    model: str | None = None,
    max_tokens: int | None = None,
    retries: int | None = None,
) -> str:
    """调用 LLM 返回纯文本（对话用，不解析 JSON）。失败重试 + 容错。

    用于 consult.py 的 C 端咨询对话；与 chat_json 共用 client / retry / proxy 处理。
    失败返回以 `[咨询暂时不可用]` 开头的安全字符串，调用方据此降级。
    """
    model = model or os.getenv("HINDCAST_MODEL", DEFAULT_MODEL)
    max_tokens = max_tokens or int(os.getenv("HINDCAST_MAX_TOKENS", DEFAULT_MAX_TOKENS))
    retries = retries or int(os.getenv("HINDCAST_RETRIES", DEFAULT_RETRIES))

    last_err = None
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                timeout=120,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(RETRY_BACKOFF_SEC * (attempt + 1))

    return f"[咨询暂时不可用] {str(last_err)[:160]}"
