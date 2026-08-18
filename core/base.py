"""base.py — SkillBase with load_prompt() for modular prompt design.

Pattern: each skill has its own directory with impl.py, SKILL.md, and prompts/*.md.
Load prompts via self.load_prompt(name) — keeps LLM instructions out of code.
"""
from __future__ import annotations
import time, logging
from abc import ABC, abstractmethod
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class SkillError(Exception): pass
class InputValidationError(SkillError): pass
class OutputValidationError(SkillError): pass
class SkillTimeoutError(SkillError): pass

class SkillBase(ABC):
    name: str = "unnamed"
    timeout: int = 300

    def run(self, context: dict) -> dict:
        t0 = time.time()
        try:
            self.validate_input(context)
            result = self.execute(context)
            self.validate_output(result)
            elapsed = time.time() - t0
            logger.info(f"  [{self.name}] done ({elapsed:.1f}s)")
            return result
        except InputValidationError as e:
            logger.error(f"  [{self.name}] input error: {e}"); raise
        except OutputValidationError as e:
            logger.error(f"  [{self.name}] output error: {e}"); raise
        except SkillTimeoutError:
            logger.error(f"  [{self.name}] timeout"); return self.handle_timeout(context)
        except Exception as e:
            logger.error(f"  [{self.name}] error: {e}"); return self.handle_error(context, e)

    @abstractmethod
    def execute(self, context: dict) -> dict: pass

    def validate_input(self, context: dict): pass
    def validate_output(self, result: dict): pass
    def handle_timeout(self, context: dict) -> dict:
        raise SkillTimeoutError(f"{self.name} timed out after {self.timeout}s")
    def handle_error(self, context: dict, error: Exception) -> dict:
        raise error

    def require_keys(self, context: dict, keys: list):
        missing = [k for k in keys if k not in context or context[k] is None]
        if missing: raise InputValidationError(f"missing keys: {missing}")
    def require_file(self, path: str):
        if not Path(path).exists():
            raise InputValidationError(f"missing file: {path}")

    # ── Prompt loading ──
    # Usage: prompt = self.load_prompt("draft")
    # Auto-discovers from the skill's impl.py location.
    def load_prompt(self, name: str) -> str:
        """Load a prompt from <skill_dir>/prompts/<name>.md.
        
        Auto-discovers skill_dir from the subclass's module file location.
        Falls back to .md and .txt extensions.
        """
        import inspect
        # Find the file where this subclass is defined
        cls_file = inspect.getfile(self.__class__)
        skill_dir = Path(cls_file).parent
        
        prompts_dir = skill_dir / "prompts"
        for ext in (".md", ".txt"):
            p = prompts_dir / f"{name}{ext}"
            if p.exists():
                return p.read_text(encoding="utf-8")
        
        raise FileNotFoundError(
            f"Prompt '{name}' not found in {prompts_dir}/ (tried .md, .txt)"
        )
