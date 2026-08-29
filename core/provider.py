"""provider.py — LLM provider with task→model routing + cost tracking + extract_json"""
from __future__ import annotations
import json, os, time, uuid, re, requests, threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# ── Task → Model mapping
# Actual DeepSeek API models: deepseek-chat (fast), deepseek-reasoner (powerful)
# ⚡ V23 fix: deepseek-chat/reasoner → deepseek-v4-pro (舊模型已503)
TASK_MODELS = {
    "transcribe": {"primary": "deepseek-v4-pro", "fallback": [], "max_tokens": 2000},
    "understand": {"primary": "deepseek-chat", "fallback": [], "max_tokens": 8000},
    "understand_verify": {"primary": "deepseek-chat", "fallback": [], "max_tokens": 8000},
    "draft": {"primary": "deepseek-chat", "fallback": [], "max_tokens": 4000},
    "review": {"primary": "deepseek-chat", "fallback": [], "max_tokens": 3000},
    "refine": {"primary": "deepseek-v4-pro", "fallback": [], "max_tokens": 8000},
    "edit": {"primary": "deepseek-v4-pro", "fallback": [], "max_tokens": 4000},
    "concept": {"primary": "deepseek-chat", "fallback": [], "max_tokens": 80},
    "scene_content": {"primary": "deepseek-chat", "fallback": [], "max_tokens": 8000},
    "pip_scene": {"primary": "deepseek-chat", "fallback": [], "max_tokens": 8000},
    "scene_designer": {"primary": "deepseek-v4-pro", "fallback": [], "max_tokens": 1000},
    "card_direct": {"primary": "deepseek-v4-pro", "fallback": [], "max_tokens": 8000},
    "card_html": {"primary": "deepseek-v4-pro", "fallback": [], "max_tokens": 8000},
    "card_enrich": {"primary": "deepseek-chat", "fallback": [], "max_tokens": 8000},
    "storyboard": {"primary": "deepseek-v4-pro", "fallback": [], "max_tokens": 4000},
    "storyboard_split": {"primary": "deepseek-chat", "fallback": [], "max_tokens": 300},
    "design_system": {"primary": "deepseek-v4-pro", "fallback": [], "max_tokens": 2000},
}
MODEL_PRICES = {
    "deepseek-v4-pro": {"input": 0.5, "output": 2.0},
    "deepseek-chat": {"input": 0.27, "output": 1.1},
    "deepseek-reasoner": {"input": 0.55, "output": 2.2},
}
RMB_TO_USD = 0.14


# ── V34: LLM 统一配置 — 换模型/供应商只改 llm_config.yaml，不改代码 ──
import yaml as _yaml

def _load_llm_config() -> dict:
    """加载统一配置 E:/Hermes-Agent/workspace/xiaoshan/llm_config.yaml。找不到返回 {}（向后兼容）。"""
    config_path = os.environ.get(
        "VCP_LLM_CONFIG",
        str(Path(__file__).resolve().parent.parent.parent / "llm_config.yaml"),
    )
    if not Path(config_path).exists():
        return {}
    try:
        with open(config_path) as f:
            return _yaml.safe_load(f) or {}
    except Exception:
        return {}

_LLM_CONFIG = _load_llm_config()

# model_override：把任务映射里的模型名做替换（换模型改 llm_config.yaml，不改代码）
_OVERRIDE = _LLM_CONFIG.get("model_override", {})


def _apply_override(model: str) -> str:
    return _OVERRIDE.get(model, model)


# 把 TASK_MODELS 里的 primary/fallback 做 override
for _cfg in TASK_MODELS.values():
    if "primary" in _cfg:
        _cfg["primary"] = _apply_override(_cfg["primary"])
    if "fallback" in _cfg:
        _cfg["fallback"] = [_apply_override(m) for m in _cfg["fallback"]]

# 供应商配置（model → {url, api_key_env}）
_PROVIDERS = {}
for _pname, _pcfg in _LLM_CONFIG.get("providers", {}).items():
    _base = _pcfg.get("base_url", "https://api.deepseek.com")
    _env = _pcfg.get("api_key_env", "DEEPSEEK_API_KEY")
    for _m in _pcfg.get("models", []):
        _PROVIDERS[_m] = {"url": _base.rstrip("/") + "/chat/completions", "api_key_env": _env}

VISION_MODEL = _apply_override(_LLM_CONFIG.get("vision_model", "deepseek-v4-flash-vision-exp"))

class RateLimiter:
    def __init__(self, rpm=10): self.rpm=rpm;self._times=[];self._lock=threading.Lock()
    def wait(self):
        with self._lock:
            now=time.time();self._times=[t for t in self._times if now-t<60]
            if len(self._times)>=self.rpm:time.sleep(60-len(self._times)+1)
            self._times.append(time.time())

class CostTracker:
    def __init__(self, output_dir="test_output"):
        self.output_dir=Path(output_dir);self.output_dir.mkdir(exist_ok=True)
        self.log_path=self.output_dir/"cost_log.json";self.entries=[];self._active={}
        if self.log_path.exists():
            try:self.entries=json.loads(self.log_path.read_text(encoding="utf-8")).get("entries",[])
            except:pass

    def estimate(self, stage, model, chars=0):
        p=MODEL_PRICES.get(model, MODEL_PRICES.get("deepseek-chat", {"input":0.5,"output":2.0}))
        tokens=chars*0.5
        cost=((tokens/1_000_000)*p["input"]+(tokens/1_000_000)*p["output"])*RMB_TO_USD if tokens>0 else 0
        eid=uuid.uuid4().hex[:8]
        entry={"id":eid,"stage":stage,"model":model,"estimated_usd":round(cost,6),"actual_usd":0,"status":"estimated","time":datetime.now(timezone.utc).isoformat()}
        self._active[eid]=entry
        return eid

    def reconcile(self, stage, success=True, chars=0, model=""):
        for eid,entry in list(self._active.items()):
            if entry["stage"]==stage:
                if model:entry["model"]=model
                if success:
                    p=MODEL_PRICES.get(entry["model"], MODEL_PRICES.get("deepseek-chat", {"input":0.27,"output":1.1}))
                    cost=((chars*0.5/1_000_000)*p["output"])*RMB_TO_USD
                    entry["actual_usd"]=round(cost,6);entry["status"]="completed"
                else:entry["status"]="failed"
                self.entries.append(entry)
                self._save();return
        # 无 active entry（estimate 未调用）→ 直接记录一次调用
        p=MODEL_PRICES.get(model, MODEL_PRICES.get("deepseek-chat", {"input":0.27,"output":1.1}))
        cost=((chars*0.5/1_000_000)*p["output"])*RMB_TO_USD if success else 0
        self.entries.append({
            "id": uuid.uuid4().hex[:8], "stage": stage, "model": model,
            "estimated_usd": 0, "actual_usd": round(cost, 6),
            "status": "completed" if success else "failed",
            "time": datetime.now(timezone.utc).isoformat(),
        })
        self._save()

    def snapshot(self):
        return {"total_spent_usd":round(sum(e.get("actual_usd",0) for e in self.entries if e.get("status")in("completed","failed")),4),"total_calls":len(self.entries),"successful_calls":sum(1 for e in self.entries if e.get("status")=="completed")}

    def summary(self):
        s=self.snapshot()
        return f"API calls: {s['total_calls']}, total cost: ${s['total_spent_usd']:.4f}"

    def _save(self):
        self.log_path.write_text(json.dumps({"updated":datetime.now(timezone.utc).isoformat(),"entries":self.entries[-50:],"summary":self.snapshot()},ensure_ascii=False,indent=2),encoding="utf-8")

class Provider:
    def __init__(self,cost_tracker=None):
        self._rate=RateLimiter();self._cost=cost_tracker or CostTracker()
        self._last_model=""

    @staticmethod
    def extract_json(text: str) -> Optional[dict]:
        """Extract JSON object from LLM response text (handles fences, chat noise)."""
        if not text: return None
        text = text.strip()
        # Try ```json ... ``` fences first
        for fence in ("```json", "```"):
            if fence in text:
                parts = text.split(fence, 1)[1].split("```", 1)[0].strip()
                text = parts
                break
        # Find outermost { ... } with valid JSON
        depth = 0; start = -1
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0: start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        return json.loads(text[start:i+1])
                    except json.JSONDecodeError:
                        continue
        return None

    def call(self,task,prompt,system="",max_tokens=None,model=None):
        cfg=TASK_MODELS.get(task,TASK_MODELS["edit"])
        models=([model] if model else [cfg["primary"]])+cfg["fallback"];mt=cfg.get("max_tokens",4000)
        if max_tokens:mt=max_tokens

        for model in models:
            # V34: 从配置查 url 和 key env（多供应商），无配置回退 deepseek 默认
            pcfg=_PROVIDERS.get(model,{"url":"https://api.deepseek.com/chat/completions","api_key_env":"DEEPSEEK_API_KEY"})
            url=pcfg["url"];env=pcfg["api_key_env"]
            keys=[k for k in (self._load_key(env),self._load_backup_key(env)) if k]
            keys=list(dict.fromkeys(keys))
            if not keys:
                print(f"  [Provider] {model} 无 API key");continue
            for api_key in keys:
                self._rate.wait()
                try:
                    resp=requests.post(
                        url,
                        headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},
                        json={"model":model,"messages":([{"role":"system","content":system}]if system else[])+[{"role":"user","content":prompt if prompt else ""}],"temperature":0,"max_tokens":mt},
                        timeout=120)
                    if resp.status_code==200:
                        msg = resp.json()["choices"][0]["message"]
                        # V34 fix: 只取 content，绝不 fallback reasoning_content（思考过程不是答案，会导致 JSON 解析失败）
                        raw = (msg.get("content") or "").strip()
                        if not raw:
                            continue
                        self._last_model=model
                        self._cost.reconcile(task,True,len(raw),model)
                        return raw
                    elif resp.status_code==429:
                        wait=int(resp.headers.get("retry-after",5))
                        print(f"  [Provider] 429, waiting {wait}s");time.sleep(wait)
                    elif resp.status_code==402:
                        print(f"  [Provider] {model} HTTP 402 欠费，切换备用 key")
                        continue
                    else:
                        print(f"  [Provider] {model} HTTP {resp.status_code}")
                except requests.Timeout:print(f"  [Provider] {model} timeout")
                except Exception as e:print(f"  [Provider] {model} error: {e}")
            if model!=models[-1]:time.sleep(3)
        return None

    def call_vision(self, prompt, image_path=None, max_tokens=800, timeout=60):
        """调用视觉模型（支持图片输入，模型从 llm_config.yaml 的 vision_model 读）"""
        import base64
        model = VISION_MODEL
        pcfg = _PROVIDERS.get(model, {"url": "https://api.deepseek.com/chat/completions", "api_key_env": "DEEPSEEK_API_KEY"})
        url = pcfg["url"]; env = pcfg["api_key_env"]
        keys = [k for k in (self._load_key(env), self._load_backup_key(env)) if k]
        keys = list(dict.fromkeys(keys))
        if not keys:
            return None
        content = [{"type": "text", "text": prompt}]
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}})
        # reasoning 模型：reasoning_content 先占 3000+ tokens，需给足空间让 content 输出
        max_tokens = max(max_tokens, 2000)
        for api_key in keys:
            self._rate.wait()
            try:
                resp = requests.post(
                    url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": max_tokens},
                    timeout=timeout)
                if resp.status_code == 200:
                    msg = resp.json()["choices"][0]["message"]
                    raw = (msg.get("content") or "").strip()
                    if raw:
                        self._last_model = model
                        self._cost.reconcile("visual_check", True, len(raw), model)
                        return raw
                    return None
                elif resp.status_code == 429:
                    time.sleep(5)
                elif resp.status_code == 402:
                    continue
                else:
                    print(f"  [Provider] vision HTTP {resp.status_code}")
            except requests.Timeout:
                print(f"  [Provider] vision timeout")
            except Exception as e:
                print(f"  [Provider] vision error: {e}")
        return None

    @property
    def last_model(self):return self._last_model
    @property
    def cost(self):return self._cost

    def _load_key(self, env="DEEPSEEK_API_KEY"):
        key = os.environ.get(env)
        if key: return key
        # 只有 deepseek 从 Hermes config.yaml 读（glm 等其他供应商走环境变量）
        if env != "DEEPSEEK_API_KEY":
            return None
        # 从 Hermes config.yaml 读 key
        hermes_cfg = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "config.yaml"
        if hermes_cfg.exists():
            import yaml
            with open(hermes_cfg, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            key = cfg.get("model", {}).get("api_key", "")
            if key and key.startswith("sk-"): return key
        # 回退：从 call_llm_v2.py 读
        kp = Path(__file__).parent.parent / "call_llm_v2.py"
        if kp.exists():
            m = re.search(r"(sk|sks)-[a-zA-Z0-9]+", kp.read_text(encoding="utf-8"))
            if m: return m.group(0)
        return None

    def _load_backup_key(self, env="DEEPSEEK_API_KEY"):
        """备用 key（主 key 402 欠费时自动切换）。从环境变量 <env>_BACKUP 或 .env 读。"""
        key = os.environ.get(f"{env}_BACKUP")
        if key: return key
        if env != "DEEPSEEK_API_KEY":
            return None
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY_BACKUP="):
                    v = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if v: return v
        return None
