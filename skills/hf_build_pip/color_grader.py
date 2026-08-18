"""color_grader.py — mood→精确配色，纯代码查表，不调LLM"""

# mood → 完整色板
PALETTES = {
    "冷静理性": {
        "primary": "#6C8CFF", "secondary": "#00D4FF", "accent": "#FFD700",
        "gradient_start": "#060618", "gradient_mid": "#0A0C26", "gradient_end": "#0C1030",
        "particle": "rgba(108,140,255,0.6)", "glow": "rgba(0,212,255,0.3)",
        "data_highlight": "#6C8CFF",
    },
    "冲突": {
        "primary": "#FF4757", "secondary": "#FFD700", "accent": "#FF6B81",
        "gradient_start": "#060618", "gradient_mid": "#0A0C26", "gradient_end": "#0C1030",
        "particle": "rgba(255,71,87,0.6)", "glow": "rgba(255,215,0,0.3)",
        "data_highlight": "#FF4757",
    },
    "紧张不安": {
        "primary": "#A855F7", "secondary": "#FF4757", "accent": "#FFD700",
        "gradient_start": "#060618", "gradient_mid": "#0A0C26", "gradient_end": "#0C1030",
        "particle": "rgba(168,85,247,0.6)", "glow": "rgba(255,71,87,0.3)",
        "data_highlight": "#A855F7",
    },
    "希望": {
        "primary": "#FFD700", "secondary": "#6C8CFF", "accent": "#00D4FF",
        "gradient_start": "#060618", "gradient_mid": "#0C1020", "gradient_end": "#120C28",
        "particle": "rgba(255,215,0,0.6)", "glow": "rgba(108,140,255,0.4)",
        "data_highlight": "#FFD700",
    },
    "希望升华": {
        "primary": "#FFD700", "secondary": "#00D4FF", "accent": "#6C8CFF",
        "gradient_start": "#060618", "gradient_mid": "#0E0C22", "gradient_end": "#140C30",
        "particle": "rgba(255,215,0,0.7)", "glow": "rgba(0,212,255,0.5)",
        "data_highlight": "#FFD700",
    },
    "愤怒冲突": {
        "primary": "#FF3B30", "secondary": "#FF9500", "accent": "#FFD700",
        "gradient_start": "#060618", "gradient_mid": "#0A0C26", "gradient_end": "#0C1030",
        "particle": "rgba(255,59,48,0.7)", "glow": "rgba(255,149,0,0.4)",
        "data_highlight": "#FF3B30",
    },
    "压迫沉重": {
        "primary": "#8E44AD", "secondary": "#2C3E50", "accent": "#A855F7",
        "gradient_start": "#060618", "gradient_mid": "#0A0C26", "gradient_end": "#0C1030",
        "particle": "rgba(142,68,173,0.5)", "glow": "rgba(44,62,80,0.2)",
        "data_highlight": "#8E44AD",
    },
}

# 默认色板（兜底）
_DEFAULT = PALETTES["冷静理性"]


def grade(mood: str) -> dict:
    """mood → 精确色板。未匹配则返回冷静理性。"""
    # 模糊匹配
    for key in PALETTES:
        if key in mood or mood in key:
            return PALETTES[key]
    return _DEFAULT
