"""Quality gates: score each step output, auto-retry if below threshold."""
import json
from pathlib import Path
from datetime import datetime

THRESHOLDS = {
    "transcribe": {"min_words": 10, "min_duration": 5.0},
    "edl": {"min_segments": 4, "max_gap": 15.0},
    "cut": {"min_total_dur": 5.0},
}

class QualityGate:
    """Score output quality and decide if retry is needed."""
    
    def __init__(self, output_dir):
        self.log_path = Path(output_dir) / "quality_scores.json"
        self.scores = []
        self._load()
    
    def _load(self):
        if self.log_path.exists():
            try:
                with open(self.log_path, encoding="utf-8") as f:
                    self.scores = json.load(f)
            except:
                pass
    
    def _save(self):
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(self.scores[-100:], f, indent=2, ensure_ascii=False)
    
    def score_transcript(self, words, duration):
        """Score transcription quality 0-100."""
        score = 100
        words_per_sec = len(words) / max(duration, 1)
        if words_per_sec < 1.0:
            score -= 20  # Very sparse
        if len(words) < 10:
            score -= 30
        if duration < 5:
            score -= 20
        return max(0, score)
    
    def score_edl(self, ranges):
        """Score EDL quality 0-100."""
        score = 100
        if len(ranges) < 4:
            score -= 20 * (4 - len(ranges))
        if len(ranges) > 12:
            score -= 10
        for i in range(len(ranges) - 1):
            gap = ranges[i + 1]["start"] - ranges[i]["end"]
            if gap > 10.0:
                score -= 15
        for r in ranges:
            dur = r["end"] - r["start"]
            if dur < 1.0:
                score -= 5
        return max(0, score)
    
    def log_score(self, step, score, details=""):
        entry = {
            "time": datetime.now().isoformat(),
            "step": step,
            "score": score,
            "details": details,
        }
        self.scores.append(entry)
        self._save()
        return score
    
    def needs_retry(self, step_name, score):
        """Check if score is below threshold and retry is warranted."""
        thresh = {
            "transcribe": 50, "analyze": 60, "cut": 70, "compose": 60
        }.get(step_name, 40)
        return score < thresh
    
    def summary(self):
        if not self.scores:
            return "No quality data"
        recent = self.scores[-5:]
        lines = [f"  [{s['step']}] score={s['score']}" for s in recent]
        return "Recent quality scores:\n" + "\n".join(lines)
    
    def latest_score(self, step=""):
        for s in reversed(self.scores):
            if not step or s["step"] == step:
                return s["score"]
        return None
    
    def reset(self):
        self.scores = []
        self._save()
