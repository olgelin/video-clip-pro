"""Unified LLM provider with multi-backend support."""
import requests

class LLMProvider:
    """Unified LLM provider supporting deepseek, openai, and custom backends."""
    
    def __init__(self, provider="deepseek", model="deepseek-chat", api_key=None):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.api_url = self._resolve_url()
    
    def _resolve_url(self):
        if self.provider == "deepseek":
            return "https://api.deepseek.com/chat/completions"
        elif self.provider == "openai":
            return "https://api.openai.com/v1/chat/completions"
        else:
            return self.provider.rstrip("/") + "/chat/completions"
    
    def chat(self, prompt, system_msg="You are a helpful assistant.", temperature=0.1, max_tokens=4096):
        resp = requests.post(
            self.api_url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=300,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"API error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        usage = data.get("usage", {})
        return {
            "content": data["choices"][0]["message"]["content"],
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }
