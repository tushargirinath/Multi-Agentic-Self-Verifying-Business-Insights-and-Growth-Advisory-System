"""MAVIS Multi-Provider LLM Client supporting OpenRouter (Free Tier) and Ollama."""
import json
import logging
import time
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger("mavis.llm")

# Verified list of active OpenRouter free models
OPENROUTER_FREE_MODELS = [
    "liquid/lfm-2.5-2.6b:free",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3.5-lightning:free",
    "dots-studio/dots-3-note-preview:free",
    "cohere/north-mini-code:free",
    "recursive/flint-v1.0:free",
    "poolside/laguna-s-2.1:free",
]


class LLMClient:
    """Enterprise multi-model gateway supporting OpenRouter free models and Ollama."""

    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.openrouter_key = settings.OPENROUTER_API_KEY
        self.openrouter_model = settings.OPENROUTER_MODEL or OPENROUTER_FREE_MODELS[0]
        self.ollama_key = settings.OLLAMA_API_KEY
        self.ollama_base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.active_model = self.openrouter_model

    def list_available_models(self) -> Dict[str, Any]:
        """Return available free models and active status."""
        return {
            "current_provider": self.provider,
            "active_model": self.active_model,
            "providers": {
                "openrouter": {
                    "configured": bool(self.openrouter_key),
                    "default_model": self.openrouter_model,
                    "free_models": OPENROUTER_FREE_MODELS,
                },
                "ollama": {
                    "configured": bool(self.ollama_key or self.ollama_base_url),
                    "base_url": self.ollama_base_url,
                    "key_present": bool(self.ollama_key),
                }
            }
        }

    def set_model(self, model_id: str, provider: Optional[str] = None):
        """Dynamically update active model or provider."""
        if provider:
            self.provider = provider
        self.active_model = model_id
        if self.provider == "openrouter":
            self.openrouter_model = model_id

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        max_tokens: int = 1200,
        temperature: float = 0.2
    ) -> Dict[str, Any]:
        """
        Execute completion with automatic failover across free models.
        """
        if self.provider == "ollama":
            res = self._call_ollama(prompt, system_instruction, max_tokens, temperature)
            if res.get("success"):
                return res
            # Fallback to OpenRouter if Ollama is unreachable
            logger.info("Ollama unreachable, failing over to OpenRouter free tier")

        return self._call_openrouter_with_failover(prompt, system_instruction, max_tokens, temperature)

    def _call_openrouter_with_failover(
        self,
        prompt: str,
        system: Optional[str],
        max_tokens: int,
        temperature: float
    ) -> Dict[str, Any]:
        """Try selected model first, then cycle through other free models if rate-limited."""
        key = self.openrouter_key or settings.OPENROUTER_API_KEY
        if not key:
            return {
                "success": False,
                "error": "OpenRouter API key is not configured.",
                "content": "",
                "provider": "openrouter",
                "model": "none"
            }

        candidate_models = [self.openrouter_model] + [
            m for m in OPENROUTER_FREE_MODELS if m != self.openrouter_model
        ]

        last_error = ""
        for model in candidate_models:
            t0 = time.time()
            try:
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://mavis.local",
                    "X-Title": "MAVIS Business Advisory System"
                }

                messages = []
                if system:
                    messages.append({"role": "system", "content": system})
                messages.append({"role": "user", "content": prompt})

                payload = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }

                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    "https://openrouter.ai/api/v1/chat/completions",
                    data=data,
                    headers=headers
                )

                with urllib.request.urlopen(req, timeout=20) as resp:
                    resp_json = json.loads(resp.read().decode("utf-8"))
                    msg = resp_json.get("choices", [{}])[0].get("message", {})
                    content = msg.get("content") or msg.get("reasoning") or ""
                    if not content or not str(content).strip():
                        logger.warning(f"Model {model} returned empty content, trying next free model...")
                        continue

                    latency = round((time.time() - t0) * 1000, 1)
                    self.active_model = model
                    return {
                        "success": True,
                        "content": str(content).strip(),
                        "provider": "openrouter",
                        "model": model,
                        "latency_ms": latency,
                        "error": None
                    }

            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore")
                last_error = f"HTTP {e.code}: {err_body[:120]}"
                logger.warning(f"Model {model} failed ({last_error}), trying next free model...")
                continue
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Model {model} connection error: {last_error}")
                continue

        return {
            "success": False,
            "error": f"All free models exhausted. Last error: {last_error}",
            "content": "",
            "provider": "openrouter",
            "model": self.openrouter_model
        }

    def _call_ollama(
        self,
        prompt: str,
        system: Optional[str],
        max_tokens: int,
        temperature: float
    ) -> Dict[str, Any]:
        """Query Ollama or OpenAI-compatible custom endpoint."""
        t0 = time.time()
        url = f"{self.ollama_base_url}/api/chat"
        try:
            headers = {"Content-Type": "application/json"}
            if self.ollama_key:
                headers["Authorization"] = f"Bearer {self.ollama_key}"

            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.active_model or "llama3",
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                }
            }

            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data.get("message", {}).get("content", "")
                return {
                    "success": True,
                    "content": content,
                    "provider": "ollama",
                    "model": payload["model"],
                    "latency_ms": round((time.time() - t0) * 1000, 1),
                    "error": None
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": "",
                "provider": "ollama",
                "model": "ollama"
            }


# Singleton instance
llm_client = LLMClient()
