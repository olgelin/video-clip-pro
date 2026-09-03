"""loader.py — YAML-driven pipeline loader with phase/parallel execution"""
from __future__ import annotations
import json, threading, time, yaml, importlib, logging, traceback
from pathlib import Path
from typing import Optional
from core.base import SkillBase, SkillError
from core.provider import Provider

logger = logging.getLogger(__name__)

class StageResult:
    def __init__(self, name: str, status: str = "pending", output: Optional[dict] = None, error: str = ""):
        self.name = name; self.status = status; self.output = output or {}; self.error = error

class PipelineLoader:
    def __init__(self, provider: Optional[Provider] = None):
        self.provider = provider or Provider()
        self._results: list[StageResult] = []

    def load(self, yaml_path: str) -> dict:
        with open(yaml_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def run(self, manifest: dict, context: Optional[dict] = None) -> dict:
        context = dict(context or {})
        stages = manifest.get("stages", [])
        self._results = []

        # Group by phase
        phases: dict[str, list[dict]] = {}
        for s in stages:
            p = str(s.get("phase", "1"))
            phases.setdefault(p, []).append(s)

        for phase in sorted(phases.keys(), key=lambda x: float(x)):
            phase_stages = phases[phase]
            # Group by parallel_group (same group = parallel)
            pg: dict[str, list[dict]] = {}
            for s in phase_stages:
                g = s.get("parallel_group") or f"_serial_{s['name']}"
                pg.setdefault(g, []).append(s)

            for gname, gstages in pg.items():
                if len(gstages) == 1:
                    self._run_one(gstages[0], context)
                else:
                    self._run_parallel(gstages, context)

        # Save final context
        out_dir = context.get("output_dir", "test_output")
        Path(out_dir).mkdir(exist_ok=True)
        (Path(out_dir) / "pipeline_context.json").write_text(
            json.dumps({k:v for k,v in context.items() if k!="provider"}, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
        return context

    def _run_one(self, stage: dict, context: dict):
        sr = self._exec_stage(stage, context)
        if sr and sr.output:
            context.update(sr.output)

    def _run_parallel(self, stages: list[dict], context: dict):
        """Run stages in parallel (threading), merge all outputs into shared context."""
        ctx_lock = threading.Lock()
        results = []

        def _w(s):
            nonlocal results
            r = self._exec_stage(s, context)
            with ctx_lock:
                if r and r.output:
                    context.update(r.output)
                    results.append(r)

        threads = []
        for s in stages:
            t = threading.Thread(target=_w, args=(s,), daemon=True)
            threads.append(t); t.start()
        for t in threads: t.join()

    def _exec_stage(self, stage: dict, context: dict) -> Optional[StageResult]:
        name = stage["name"]; skill_mod = stage.get("skill", name)
        retry = stage.get("retry", 0); critical = stage.get("critical", False)
        optional = stage.get("optional", False)
        timeout = stage.get("timeout", 300)
        sr = StageResult(name, "failed")

        for attempt in range(retry + 1):
            try:
                mod = importlib.import_module(f"skills.{skill_mod}")
                # 兼容两种命名：capitalize(Hf_build_pip) + 驼峰(ReTranscribe)
                sk_cls = getattr(mod, skill_mod.capitalize(), None)
                if sk_cls is None:
                    cls_name2 = "".join(w.capitalize() for w in skill_mod.split("_"))
                    sk_cls = getattr(mod, cls_name2, None)
                sk_cls = sk_cls or getattr(mod, "run")
                if isinstance(sk_cls, type) and issubclass(sk_cls, SkillBase):
                    sk = sk_cls() if isinstance(sk_cls, type) else sk_cls
                    sk.timeout = timeout
                    result = sk.run({"provider": self.provider, **context})
                else:
                    result = sk_cls({"provider": self.provider, **context})

                sr = StageResult(name, "done", result)
                logger.info(f"  [{name}] OK")
                return sr
            except SkillError as e:
                logger.warning(f"  [{name}] attempt {attempt+1}: {e}")
                if attempt < retry:
                    time.sleep(3)
                else:
                    if optional:
                        sr = StageResult(name, "skipped")
                        return sr
                    if critical:
                        raise
                    sr = StageResult(name, "failed", error=str(e))
            except Exception as e:
                logger.error(f"  [{name}] unexpected error: {e}")
                traceback.print_exc()
                if attempt >= retry:
                    if optional: return StageResult(name, "skipped")
                    if critical: raise
                    sr = StageResult(name, "failed", error=str(e))
                    break
                time.sleep(3)
        return sr

