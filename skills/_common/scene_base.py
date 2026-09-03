"""scene_base.py — hf_build_pip / hf_build_avatar 公共基类。

抽取两个渲染 skill 的 11 个完全一致的方法（LLM 场景调用/清洗/Three.js 技法/校验），
消除"改一处不同步"的重复。hf_build_pip 和 hf_build_avatar 都继承本类。
"""
from __future__ import annotations
import re, time
from core.base import SkillBase


class SceneBuilderBase(SkillBase):
    """LLM 场景生成公共基类（call_scene/clean_scene/threejs 技法/校验）。"""

    def _call_scene(self, provider, prompt: str) -> str | None:
            for attempt in range(3):
                raw = provider.call("scene_content", prompt,
                    system=(
                        "🔴 HTML 输出机。你只输出 HTML 代码，禁止任何其他文字。"
                        "第一字符必须是 <。禁止'让''用户''I will''Let me''考虑''好的''OK''要求输出''给这段''输出''让我规划'等任何非 HTML 文字。"
                        "h1 文字从导演简报取，不是你编的。输出 <canvas> 或 <h1> 或 <div> 开头。输出完立即停止。输出任何推理文字你会被淘汰。"
                    ),
                    max_tokens=8000)
                content = self._clean_scene(raw)
                if content:
                    return content
                # 🔴 v4-pro 陷入推理（无 HTML 锚点）→ fallback deepseek-chat（非推理）
                raw2 = provider.call("scene_content", prompt,
                    system=(
                        "🔴 HTML 输出机。你只输出 HTML 代码片段（canvas/div/h1），禁止任何其他文字。"
                        "第一字符必须是 <。禁止输出 DOCTYPE/html/head/body/style 标签。"
                    ),
                    max_tokens=8000, model="deepseek-chat")
                content = self._clean_scene(raw2, strip_full_doc=True)
                if content:
                    return content
                time.sleep(1.5)
            return None
    def _clean_scene(self, raw, strip_full_doc: bool = False) -> str | None:
            """清洗 LLM 响应：剥推理前缀 + 剥代码块 + 剥完整文档外壳"""
            if not raw or len(raw) <= 80:
                return None
            content = raw.strip()
            # Strip common deepseek reasoning prefixes before HTML
            for garbage in ["要求输出", "给这段", "让我编", "让我输出", "好的，", "让我规划"]:
                if content.startswith(garbage):
                    content = content[len(garbage):].lstrip("，。：:\"' ")
            for tag in ["```html", "```"]:
                if tag in content:
                    parts = content.split(tag, 1)
                    if len(parts) > 1:
                        content = parts[1].split("```", 1)[0].strip()
            # fallback 场景：deepseek-chat 输出完整文档 → 提取 body 内容或剥离外壳
            if strip_full_doc:
                m = re.search(r'(?is)<body[^>]*>(.*?)</body>', content)
                if m:
                    content = m.group(1).strip()
                else:
                    content = re.sub(r'(?is)<!DOCTYPE[^>]*>', '', content)
                    content = re.sub(r'(?is)<head>.*?</head>', '', content)
                    content = re.sub(r'(?is)<style[^>]*>.*?</style>', '', content)
                    content = re.sub(r'(?is)<title[^>]*>.*?</title>', '', content)
                    content = re.sub(r'(?is)</?html[^>]*>', '', content)
                    content = re.sub(r'(?is)</?head[^>]*>', '', content)
                    content = re.sub(r'(?is)</?body[^>]*>', '', content)
                    content = re.sub(r'(?is)<meta[^>]*>', '', content)
            if not content.startswith("<"):
                cut = content.find("<")
                if cut > 0:
                    content = content[cut:]
            if content.startswith("<"):
                content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
                # 🔴 检测推理文字污染（deepseek 把"我会/注意：/我需要"思考文字混进 HTML）
                reasoning_markers = ["我会先", "我会在", "我需要", "注意：", "我将在", "或<div>开头",
                                     "主标题文字", "需要拆分", "让我们", "确保所有", "首先", "接下来我"]
                if any(m in content[:3000] for m in reasoning_markers):
                    print(f"    ⚠ 推理文字污染，触发 fallback")
                    return None
                if not self._validate(content):
                    return content
                print(f"    attempt 1/3: {', '.join(self._validate(content))}")
            return None
    def _default_threejs(self, orientation: str) -> str:
            fw, fh = (1920, 1080) if orientation == "landscape" else (1080, 1920)
            # 蓝紫渐变粒子（对齐场景审美），N=3000，与 bg3d 技法一致的电影感
            return f"""<canvas id="pt3d" style="position:absolute;inset:0;z-index:0;"></canvas>
    <script>const c=document.getElementById("pt3d"),r=new THREE.WebGLRenderer({{canvas:c,alpha:true,antialias:true}});r.setPixelRatio(1);r.setSize({fw},{fh},false);const s=new THREE.Scene(),cam=new THREE.PerspectiveCamera(35,{fw}/{fh},.1,100);cam.position.set(0,0,10);const N=3000,ps=new Float32Array(N*3),cs=new Float32Array(N*3),A=4;const C1=new THREE.Color("#6C8CFF"),C2=new THREE.Color("#A855F7");for(let i=0;i<N;i++){{ps[i*3]=(Math.random()-.5)*14;ps[i*3+1]=(Math.random()-.5)*18;ps[i*3+2]=(Math.random()-.5)*6;const t=Math.random(),cc=C1.clone().lerp(C2,t);cs[i*3]=cc.r;cs[i*3+1]=cc.g;cs[i*3+2]=cc.b}}const g=new THREE.BufferGeometry();g.setAttribute("position",new THREE.BufferAttribute(ps,3));g.setAttribute("color",new THREE.BufferAttribute(cs,3));const pts=new THREE.Points(g,new THREE.PointsMaterial({{size:.06,vertexColors:true,blending:THREE.AdditiveBlending,depthWrite:false,transparent:true,opacity:.75}}));s.add(pts);function rd(t){{pts.rotation.y=t*.45;pts.rotation.x=Math.sin(t*.9)*.12;r.render(s,cam)}}window.addEventListener("hf-seek",e=>rd(e.detail.time));rd(window.__hfThreeTime||0);</script>"""
    def _detect_threejs_tech(self, html: str) -> str:
            """从生成的 HTML 检测实际使用的 Three.js 技法（canvas id）"""
            tech_map = {
                "glx": "银河漩涡", "pt3d": "粒子场聚散", "bg3d": "粒子+Bloom辉光",
                "stars": "星空慢旋", "rain": "代码雨坠", "grid": "网格脉冲",
            }
            for cid, name in tech_map.items():
                if f'id="{cid}"' in html:
                    return name
            if "<canvas" in html:
                return "自定义3D"
            return "无3D(CSS场景)"
    def _ensure_threejs(self, html: str, orientation: str) -> str:
            """🔴 兜底：LLM 有时只输出注释不输出 Three.js 实际代码（画面时好时坏的根因）。
            检测缺失（无 new THREE.WebGLRenderer / hf-seek）则清理残留空 canvas 并注入默认技法 A（粒子场聚散）。"""
            if "new THREE.WebGLRenderer" in html or "hf-seek" in html:
                return self._fix_canvas_zindex(self._fix_slow_rotation(html))
            print("        ⚠ Three.js 缺失 → 注入默认粒子场聚散兜底")
            # 清理 LLM 残留的空 canvas（只有 <canvas> 标签没有对应 Three.js 代码）
            html = re.sub(r'<canvas[^>]*>', '', html)
            return html + self._default_threejs(orientation)
    def _extract_llm_motion(self, content: str, dur: float = 5.0):
            """提取 LLM 的 GSAP 动画语句，返回 (纯HTML结构, 动画语句字符串)
            只移除含 var tl 的 GSAP script，保留 importmap + Three.js module script。
            🔴 音画同步兜底：clamp 超过场景时长的动画时间戳。"""
            statements = re.findall(r'tl\.(?:from|to|fromTo)\([^;]*\);?', content)
            # 🔴 检测并删除未闭合 function() 的坏代码（LLM 偶发把 innerText countUp 写一半截断：
            #    `tl.to(".count-num",{innerText:function()` 没闭合 → 下一行 tl.from 被当参数 → JS 报 Unexpected identifier 'tl'）
            _clean_statements = []
            for _s in statements:
                if 'function(' in _s:
                    _after = _s[_s.rfind('function('):]
                    if 'return' not in _after or '})' not in _after:
                        continue  # 未闭合的 function()，删除整句
                _clean_statements.append(_s)
            statements = _clean_statements
            if dur and dur > 0:
                clamped = []
                for s in statements:
                    m = re.search(r'(-?\d+(?:\.\d+)?)\s*\)\s*;?\s*$', s)
                    if m and float(m.group(1)) >= dur:
                        s = s[:m.start(1)] + f"{max(0.1, dur - 0.5):.1f}" + s[m.end(1):]
                    clamped.append(s)
                statements = clamped
            llm_motion = "\n".join(statements)

            def _rm_gsap(m):
                block = m.group(0)
                if 'var tl' in block:
                    return ''  # 移除 GSAP script（timeline 由框架统一生成）
                if 'importmap' in block:
                    return ''  # 🔴 移除 importmap（Three.js 已由框架内联为全局 THREE）
                return block
            html = re.sub(r'<script[^>]*>.*?</script>', _rm_gsap, content, flags=re.DOTALL)
            # 🔴 兜底：移除 module script 里的 import 语句（LLM 可能残留），用全局 THREE
            html = re.sub(r'import\s*\*\s*as\s+THREE\s+from\s*["\']three["\'];?', '', html)
            html = re.sub(r'import\s*\{[^}]*\}\s*from\s*["\']three[^"\']*["\'];?', '', html)
            return html, llm_motion
    def _fix_slow_rotation(self, html: str) -> str:
            """🔴 强制 rotation 速度 ≥0.4 rad/s：LLM 生成变速呼吸时把 rotation.y=t*.2 写成慢速，
            螺旋臂 0.4s 才转 4.6 度=静止。正则把 rotation.y=t*X（X<0.4）强制提到 0.4。"""
            def repl(m):
                v = float(m.group(1))
                return f"rotation.y=t*{max(v, 0.4):g}"
            return re.sub(r'rotation\.y=t\*([0-9]*\.?[0-9]+)', repl, html)
    def _fix_canvas_zindex(self, html: str) -> str:
            """🔴 兜底：Three.js canvas 的 z-index 必须 ≥1（背景渐变层之上），否则 LLM 生成的
            不透明背景渐变会盖住粒子 → 粒子白画、画面静态。检测 <canvas> 若 z-index:0 或无 z-index，
            强制改成 z-index:1。"""
            def _fix_canvas(m):
                tag = m.group(0)
                if 'z-index:' in tag:
                    return re.sub(r'z-index:\s*0\b', 'z-index:2', tag)
                # 无 z-index，在 style 里补
                if 'style="' in tag:
                    return tag.replace('style="', 'style="z-index:2;', 1)
                if "style='" in tag:
                    return tag.replace("style='", "style='z-index:2;", 1)
                # 无 style，补一个
                return tag[:-1] + ' style="z-index:2;">'
            return re.sub(r'<canvas\b[^>]*>', _fix_canvas, html)
    def _layout_menu(self, idx: int) -> str:
            opts = [
                "主标题居中大字，标签在下方弧形排列",
                "主标题左对齐，标签以卡片堆叠在右侧",
                "主标题在顶部 25%，数据元素在中央大区域",
                "主标题在底部 65%，粒子从上方涌入标题",
                "主标题右对齐 70%位置，标签在左列纵向排列",
                "主标题顶部大字+副标题在下，标签横向底部排列",
            ]
            return f"建议方向（可以偏离）: {opts[idx % len(opts)]}\n{' | '.join(opts)}"
    def _motion_nl(self, motion: dict) -> str:
            lines = []
            for m in motion.get("timeline", []):
                eff = m.get("effect", "")
                t = m.get("start", 0)
                if "stagger" in eff:
                    lines.append(f"{t:.1f}s: 标题逐字渐入")
                elif "breathe" in eff:
                    lines.append(f"{t:.1f}s: 标题呼吸缩放")
                elif "sweep" in eff:
                    lines.append(f"{t:.1f}s: 扫光划过")
                elif "particle" in eff:
                    lines.append(f"{t:.1f}s: 粒子入场")
                elif "tag_reveal" in eff:
                    lines.append(f"{t:.1f}s: 标签逐个弹出")
            return "\n".join(lines) if lines else "0s: 标题渐入"
    def _rm_gsap(m):
                block = m.group(0)
                if 'var tl' in block:
                    return ''  # 移除 GSAP script（timeline 由框架统一生成）
                if 'importmap' in block:
                    return ''  # 🔴 移除 importmap（Three.js 已由框架内联为全局 THREE）
                return block
    def _validate(self, html: str) -> list:
            issues = []
            if len(html) < 300:
                issues.append(f"过小({len(html)}B)")
                return issues
            if "<h1" not in html[:500]:
                hits = sum(1 for m in ["让我","规划","考虑到","I will","Let me"] if m in html[:500])
                if hits >= 2:
                    issues.append("推理文本")
            h1 = re.search(r"<h1[^>]*>(.+?)</h1>", html, re.DOTALL)
            if not h1:
                issues.append("无h1")
            elif len(re.sub(r"<[^>]+>", "", h1.group(1)).strip()) < 2:
                issues.append("h1无文字")
            if "<!--" in html and "-->" in html:
                issues.append("注释")
            # 🔴 检测 style="..." 省略号（LLM 偷懒省略 CSS，导致画面时好时坏——标题/卡片/进度条全部裸文本）
            ellipsis = html.count('style="..."') + html.count("style='...'")
            if ellipsis > 3:
                issues.append(f"省略号style({ellipsis}个)")
            return issues
