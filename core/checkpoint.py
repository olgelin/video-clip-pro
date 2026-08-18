"""Step-by-step checkpoint/resume for pipeline."""
import json, os
from pathlib import Path
from datetime import datetime

STEP_NAMES = {
    1: "transcribe",
    2: "analyze_draft",
    3: "analyze_refine",
    4: "postprocess",
    5: "cut",
    6: "compose",
    7: "render",
}

class CheckpointManager:
    """Save/load pipeline execution state."""
    
    def __init__(self, output_dir):
        self.dir = Path(output_dir) / "checkpoints"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._completed = set()
        self._load_completed()
    
    def _load_completed(self):
        """Load completed steps from disk."""
        if self.dir.exists():
            for f in self.dir.glob("step_*.json"):
                try:
                    step = int(f.stem.split("_")[1])
                    self._completed.add(step)
                except:
                    pass
    
    def is_completed(self, step):
        return step in self._completed
    
    def save(self, step, context=None):
        """Save checkpoint for a completed step."""
        data = {
            "step": step,
            "name": STEP_NAMES.get(step, f"step_{step}"),
            "timestamp": datetime.now().isoformat(),
            "context": context or {},
        }
        path = self.dir / f"step_{step:02d}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self._completed.add(step)
        return path
    
    def load(self, step):
        """Load checkpoint for a specific step."""
        path = self.dir / f"step_{step:02d}.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return None
    
    def get_completed(self):
        return sorted(self._completed)
    
    def summary(self):
        steps = self.get_completed()
        if not steps:
            return "No checkpoints found"
        names = [STEP_NAMES.get(s, f"step_{s}") for s in steps]
        return f"Completed: {len(steps)}/7 steps ({', '.join(names)})"
