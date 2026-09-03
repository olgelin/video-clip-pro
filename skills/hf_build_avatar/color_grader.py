"""color_grader.py — mood→精确配色，纯代码查表，不调LLM。

🔴 审美定版（用户）：蓝色科技风——蓝 #6C8CFF / 青 #00D4FF 主色，紫 #A855F7 / 金 #FFD700 点缀，
   深色蓝紫渐变背景。不跳红/橙/绿。
   情绪差异用「明暗 + 饱和度 + 主次比重」表达（负面更暗更紫、正面更亮更青），不换色相到红橙绿。
"""

# mood → 完整色板（全部锁定蓝/青/紫/金，禁止红橙绿）
PALETTES = {
    "冷静理性": {
        "primary": "#6C8CFF", "secondary": "#00D4FF", "accent": "#FFD700",
        "gradient_start": "#060618", "gradient_mid": "#0A0C26", "gradient_end": "#0C1030",
        "particle": "rgba(108,140,255,0.6)", "glow": "rgba(0,212,255,0.3)",
        "data_highlight": "#00D4FF",
    },
    "冲突": {
        # 负面 → 紫主 + 蓝次（更暗更压抑），金点缀，不用红
        "primary": "#A855F7", "secondary": "#6C8CFF", "accent": "#FFD700",
        "gradient_start": "#060618", "gradient_mid": "#0A0C26", "gradient_end": "#0C1030",
        "particle": "rgba(168,85,247,0.6)", "glow": "rgba(108,140,255,0.3)",
        "data_highlight": "#A855F7",
    },
    "紧张不安": {
        "primary": "#A855F7", "secondary": "#00D4FF", "accent": "#FFD700",
        "gradient_start": "#060618", "gradient_mid": "#0A0C26", "gradient_end": "#0C1030",
        "particle": "rgba(168,85,247,0.6)", "glow": "rgba(0,212,255,0.3)",
        "data_highlight": "#A855F7",
    },
    "希望": {
        "primary": "#00D4FF", "secondary": "#6C8CFF", "accent": "#FFD700",
        "gradient_start": "#060618", "gradient_mid": "#0C1020", "gradient_end": "#120C28",
        "particle": "rgba(0,212,255,0.6)", "glow": "rgba(108,140,255,0.4)",
        "data_highlight": "#00D4FF",
    },
    "希望升华": {
        "primary": "#00D4FF", "secondary": "#A855F7", "accent": "#FFD700",
        "gradient_start": "#060618", "gradient_mid": "#0E0C22", "gradient_end": "#140C30",
        "particle": "rgba(0,212,255,0.7)", "glow": "rgba(168,85,247,0.5)",
        "data_highlight": "#00D4FF",
    },
    "愤怒冲突": {
        # 最负面 → 深紫 + 暗蓝（最暗最压抑），金点睛，不用红橙
        "primary": "#A855F7", "secondary": "#6C8CFF", "accent": "#FFD700",
        "gradient_start": "#060618", "gradient_mid": "#0A0C26", "gradient_end": "#0C1030",
        "particle": "rgba(168,85,247,0.7)", "glow": "rgba(108,140,255,0.4)",
        "data_highlight": "#A855F7",
    },
    "压迫沉重": {
        "primary": "#A855F7", "secondary": "#6C8CFF", "accent": "#FFD700",
        "gradient_start": "#060618", "gradient_mid": "#0A0C26", "gradient_end": "#0C1030",
        "particle": "rgba(142,68,173,0.5)", "glow": "rgba(108,140,255,0.3)",
        "data_highlight": "#A855F7",
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
