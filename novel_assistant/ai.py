from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Generator, List, Optional

import requests


@dataclass
class AIConfig:
    provider: str = "deepseek"
    endpoint: str = "https://api.deepseek.com/chat/completions"
    api_key: str = ""
    model: str = "deepseek-chat"
    temperature: float = 0.8
    monthly_budget: float = 20.0


MODEL_PRICING = {
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "deepseek-chat": {"input": 0.27 / 1_000_000, "output": 1.10 / 1_000_000},
    "qwen-plus": {"input": 0.4 / 1_000_000, "output": 1.2 / 1_000_000},
}

PROVIDER_PRESETS = {
    "deepseek": {
        "endpoint": "https://api.deepseek.com/chat/completions",
        "model": "deepseek-chat",
    },
    "openai": {
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
    },
    "qwen": {
        "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "model": "qwen-plus",
    },
}


class AIClient:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = self.load_config()

    def load_config(self) -> AIConfig:
        if not self.config_path.exists():
            return AIConfig()
        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        cfg = AIConfig(**{**AIConfig().__dict__, **raw})
        self.apply_provider_preset(cfg, force=False)
        return cfg

    def save_config(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(self.config.__dict__, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def build_messages(self, system_prompt: str, user_prompt: str) -> List[Dict[str, str]]:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def apply_provider_preset(self, cfg: AIConfig, force: bool = True) -> None:
        provider = cfg.provider.strip().lower()
        preset = PROVIDER_PRESETS.get(provider)
        if not preset:
            return
        if force or not cfg.endpoint:
            cfg.endpoint = preset["endpoint"]
        if force or not cfg.model:
            cfg.model = preset["model"]

    @staticmethod
    def extract_content(response: Dict) -> str:
        choices = response.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        return message.get("content", "")

    def completion(self, system_prompt: str, user_prompt: str, stream: bool = False):
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "messages": self.build_messages(system_prompt, user_prompt),
            "temperature": self.config.temperature,
            "stream": stream,
        }
        if stream:
            return self._stream_request(headers, payload)
        r = requests.post(self.config.endpoint, headers=headers, json=payload, timeout=(15, 120))
        r.raise_for_status()
        return r.json()

    def _stream_request(self, headers: Dict, payload: Dict) -> Generator[str, None, None]:
        with requests.post(
            self.config.endpoint,
            headers=headers,
            json=payload,
            stream=True,
            timeout=120,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                text = line.decode("utf-8")
                if text.startswith("data: "):
                    data = text[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {}).get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        continue

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        p = MODEL_PRICING.get(self.config.model, {"input": 0.5 / 1_000_000, "output": 1.5 / 1_000_000})
        return input_tokens * p["input"] + output_tokens * p["output"]


def load_prompt_template(template_dir: Path, name: str, variables: Dict[str, str]) -> str:
    template_path = template_dir / f"{name}.txt"
    if not template_path.exists():
        return "{{selectedText}}"
    text = template_path.read_text(encoding="utf-8")
    for k, v in variables.items():
        text = text.replace("{{" + k + "}}", v)
    return text
