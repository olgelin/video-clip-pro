"""hf_build_avatar — 从 storyboard 接收场景，生成HTML
架构: storyboard(分镜+视觉方向) → Python框架(grid+粒子+辉光) → Scene LLM(Three.js+标题+标签)
"""
import json, re, time
from pathlib import Path
from core.base import SkillBase


class Hf_build_avatar(SkillBase):
    name = "hf_build_avatar"

    def execute(self, context: dict) -> dict:
        provider = context.get("provider")
        scenes = context.get("scenes", [])
        if not scenes:
            print("  ⛔ 无 storyboard 场景")
            return {"html_files": [], "review": {}}

        # 🔴 avatar 数据适配：数字人视频 + 口播稿字幕（无剪切，不走转录）
        if context.get("avatar_video_path"):
            context["video_path"] = context["avatar_video_path"]
            # 数字人视频复制成 final.mp4（叠加逻辑 _compose_pip 期待 final.mp4）
            import shutil as _shutil
            _av = Path(context["avatar_video_path"])
            _final = Path(context.get("output_dir", ".")) / "final.mp4"
            if _av.exists() and not _final.exists():
                _shutil.copy2(_av, _final)
            if not context.get("words") and context.get("script_data"):
                context["words"] = self._script_to_words(
                    context["script_data"], context.get("voice_scene_durations", []))

        n = len(scenes)
        print(f"\n[6/6] Avatar — {n}场景")

        # 🔴 场景方向优先用 --orientation（数字人合成用竖屏素材时，场景仍可横屏）
        from core.hf_card_builder import _detect_orientation
        orientation = context.get("orientation") or _detect_orientation(context.get("video_path", ""))
        print(f"      方向: {'横屏 1920×1080' if orientation == 'landscape' else '竖屏 1080×1920'}")

        from skills.hf_build_avatar.color_grader import grade
        from skills.hf_build_avatar.motion_director import direct as motion_gen
        from skills.hf_build_avatar.stage_template import build_stage

        scene_prompt_tpl = self.load_prompt("scene_system")
        output_dir = Path(context.get("output_dir", ".")) / "hf_build_avatar"
        output_dir.mkdir(parents=True, exist_ok=True)
        html_files = []
        prev_scene = None

        for idx, scene in enumerate(scenes):
            quote = scene.get("narration", "")
            mood = scene.get("mood", "冷静理性")
            dur = scene.get("duration", 5)

            ke = scene.get("key_elements", [])
            d_tags = [e["text"] for e in ke if e.get("type") == "tag"]
            d_titles = [e["text"] for e in ke if e.get("type") == "title"]
            # 🔴 ghost 水印优先用 LLM 产出的 title（有意义关键词），tag 关闭时不再从口播截废话
            ghost = d_titles[0] if d_titles else (d_tags[0] if d_tags else (quote[:2] if len(quote) >= 2 else "?"))

            palette = grade(mood)
            motion = motion_gen(dur, scene.get("animation_style", "逐字渐入"), idx)

            brief = self._dict_to_brief(scene, idx, n, prev_scene)
            prompt = scene_prompt_tpl
            reps = {
                "visual_brief": brief,
                "color_palette": json.dumps(palette, ensure_ascii=False, indent=2),
                "layout_options": self._layout_menu(idx),
                "threejs_menu": self._threejs_menu(orientation),
                "motion_instructions": self._motion_nl(motion),
                "opening_hint": self._opening_hint(idx),
            }
            for k, v in reps.items():
                prompt = prompt.replace("{" + k + "}", v)

            content = self._call_scene(provider, prompt)
            if content:
                # 🔴 P0：提取 LLM 动画语句，合并进 stage 的统一 timeline（单一 __timelines["beat-N"]）
                content_html, llm_motion = self._extract_llm_motion(content, dur=dur)
                content_html = self._ensure_threejs(content_html, orientation)  # 🔴 兜底：Three.js 缺失注入默认粒子
                _pl = self._person_layout(orientation, scene.get('visual_type'))
                stage = build_stage(idx, dur, palette, motion, ghost=ghost, quote=quote, llm_motion=llm_motion,
                                    orientation=orientation, person_layout=_pl)
                scene["person_layout"] = _pl
                html = stage.replace("<!-- LLM_CONTENT_INSERT -->", content_html)
                (output_dir / f"beat-{idx}.html").write_text(html, encoding="utf-8")
                html_files.append(str(output_dir / f"beat-{idx}.html"))
                # 记录本场实际使用的 Three.js 技法，供下一场对比
                scene["_threejs_tech"] = self._detect_threejs_tech(content)
                print(f"  [{idx+1}/{n}] {len(html)//1024}KB [{scene.get('visual_type','?')[:10]}] {scene['_threejs_tech']} {quote[:20]}")
                prev_scene = scene
            else:
                print(f"  [{idx+1}/{n}] ❌ [{scene.get('visual_type','?')[:10]}]")

        ok = len(html_files)
        print(f"\n  质量: {ok}/{n} {'✅全通过' if ok == n else '⚠'}")
        # 🔴 P0：把 HTML 全屏场景渲染进最终视频（HyperFrames）
        render_result = self._render_scenes(context, scenes, output_dir)
        return {"html_files": html_files, **render_result}

    def _render_scenes(self, context: dict, scenes: list, output_dir: Path) -> dict:
        """P0：把 hf_build_pip 的全屏 HTML 场景渲染进最终视频"""
        if not scenes:
            return {}
        from core.hf_card_builder import build_hyperframes_composition, render_hyperframes
        words = context.get("words", [])
        video_path = Path(context.get("video_path", ""))
        project_root = Path(context.get("output_dir", "."))  # 项目根（final.mp4/hyperframes 所在）
        render_ranges = []
        for i, scene in enumerate(scenes):
            # output_dir 已是 hf_build_pip 子目录，直接拼 beat-N.html
            html_path = output_dir / f"beat-{i}.html"
            if not html_path.exists():
                continue
            html_content = html_path.read_text(encoding="utf-8")
            render_ranges.append({
                "start": scene.get("final_start", scene.get("start", 0)),
                "end": scene.get("final_end", scene.get("start", 0) + scene.get("duration", 5)),
                "beat": "INFO",
                "quote": scene.get("narration", ""),
                "_scene_html": html_content,
            })
        if not render_ranges:
            print("      ⚠ 渲染跳过：无 HTML 场景文件")
            return {}
        render_edl = {"ranges": render_ranges}
        try:
            print(f"\n[渲染] HyperFrames 合成 {len(render_ranges)} 个全屏场景 (Avatar)...")
            hf_dir = build_hyperframes_composition(render_edl, words, project_root, video_path,
                                                   layout_mode="avatar", orientation=context.get("orientation"))
            if hf_dir:
                polished = render_hyperframes(hf_dir)
                if polished:
                    return {"final_polished": str(polished)}
        except Exception as e:
            print(f"      PIP 渲染错误: {e}")
        return {}

    def _script_to_words(self, script_data: dict, scene_durations: list) -> list:
        """口播稿段落 + 配音时长 → words（逐段字幕，时间戳从配音时长累积，音画同步）"""
        sections = script_data.get("voiceover_sections", [])
        words = []
        acc = 0.0
        for i, sec in enumerate(sections):
            dur = scene_durations[i]["duration"] if i < len(scene_durations) else max(len(sec.get("content", "")) / 4.0, 2.0)
            words.append({"start": round(acc, 2), "end": round(acc + dur, 2), "text": sec.get("content", "")})
            acc += dur
        return words

    def _dict_to_brief(self, d: dict, idx: int, total: int, prev: dict = None) -> str:
        parts = [
            f"第{idx+1}/{total}场",
            f"🔴 本场时长：{d.get('duration', 5):.1f}秒（所有 GSAP 动画时间戳必须 < 此值，禁止动画超时）",
            f"视觉类型：{d.get('visual_type', 'quote_hero')}",
            f"画面隐喻（创作方向，不直接显示）：{d.get('concept', '')}",
            f"情绪：{d.get('mood', '')}",
            f"口播参考（理解语义用，禁止>15字原文贴入）：{d.get('narration', '')}",
        ]
        # 🔴 Cross-scene contrast
        if prev:
            prev_tech = prev.get("_threejs_tech", "")
            tech_hint = f"，上一场用了 {prev_tech} Three.js 技法你禁止再用" if prev_tech else ""
            parts.insert(2, f"🔴 上一场用了 {prev.get('visual_type','?')} 类型{tech_hint}，你这场的视觉/布局/Three.js技法/配色比重 必须完全不同")
        ke = d.get("key_elements", [])
        if ke:
            titles = [e["text"] for e in ke if e.get("type") == "title"]
            # 🔴 h1#main-title 必须用这个文字——禁止用 concept/画面隐喻里的文字
            if titles:
                parts.insert(1, f"🔴 h1#main-title 文字（禁止用画面隐喻里的文字做标题）：{titles[0]}")
            tags = [e["text"] for e in ke if e.get("type") == "tag"]
            nums = [e["text"] for e in ke if e.get("type") == "number"]
            if tags:
                parts.append(f"标签：{', '.join(tags)}")
            if nums:
                parts.append(f"数据：{', '.join(nums)}")
        if d.get("animation_style"):
            parts.append(f"入场动效：{d['animation_style']}")
        if d.get("chart_type"):
            parts.append(f"图表类型：{d['chart_type']}")
        # ── 抄自 video-factory：depth_layers / density_target / camera_motion / choreography ──
        dl = d.get("depth_layers", {})
        if dl:
            dl_text = " | ".join(f"{k}:{v}" for k, v in dl.items() if v)
            parts.append(f"🔴 层次结构（前景/中景/背景，必须按此分层）：{dl_text}")
        if d.get("density_target"):
            parts.append(f"🔴 元素密度：至少 {d['density_target']} 个可见元素（标题+卡片+进度条+标签+装饰层）")
        cm = d.get("camera_motion")
        if cm:
            cm_type = cm.get("type") if isinstance(cm, dict) else str(cm)
            parts.append(f"🔴 镜头运动（MUST 必须实现，禁止整场静止）：{cm_type}")
        ch = d.get("choreography", {})
        if ch:
            parts.append(f"动画动词：标题 {ch.get('title','')}，内容 {ch.get('content','')}")
        return "\n".join(parts)

    def _person_layout(self, orientation: str, visual_type: str = "") -> str:
        """🔴 数字人位置布局（v41 语义换位）：按视觉类型决定，金句/对比/时间线 → 左下（横屏右分栏），
        其余 → 右下角标。占位框（stage_template）和数字人 video 位置（hf_card_builder）都走同一映射，
        保证两层对齐。v40 已改 HyperFrames 同层渲染，位置切换用 GSAP 动画在 main timeline 上做，
        不再受 v39「ffmpeg 叠加统一位置」的约束。"""
        from skills.hf_build_avatar.person_zone import person_layout_for_visual_type
        return person_layout_for_visual_type(visual_type, orientation)

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

    def _opening_hint(self, idx: int) -> str:
        if idx == 0:
            return "🔴 开场——大字110-130px，选最炫Three.js，1-2个标签慢飘入，不用KPI。"
        return ""

    def _threejs_menu(self, orientation: str = "portrait") -> str:
        fw, fh = (1920, 1080) if orientation == "landscape" else (1080, 1920)
        menu = """选1个:

A. 粒子场聚散:
<canvas id="pt3d" style="position:absolute;inset:0;z-index:0;"></canvas>
<script>const c=document.getElementById("pt3d"),r=new THREE.WebGLRenderer({canvas:c,alpha:true,antialias:true});r.setPixelRatio(1);r.setSize(1080,1920,false);const s=new THREE.Scene(),cam=new THREE.PerspectiveCamera(35,1080/1920,.1,100);cam.position.set(0,3,12);cam.lookAt(0,0,0);const N=3000,ps=new Float32Array(N*3),cs=new Float32Array(N*3),spd=new Float32Array(N),A=4;const C1=new THREE.Color("#6C8CFF"),C2=new THREE.Color("#A855F7");for(let i=0;i<N;i++){const rad=Math.random()*6,aa=(i%A)/A*Math.PI*2,sp=rad*2.5+aa,sc=(Math.random()-.5)*rad*.4;ps[i*3]=Math.cos(sp)*rad+sc;ps[i*3+1]=(Math.random()-.5)*16;ps[i*3+2]=Math.sin(sp)*rad+sc;spd[i]=0.06+Math.random()*0.14;const t=Math.random(),cc=C1.clone().lerp(C2,t);cs[i*3]=cc.r;cs[i*3+1]=cc.g;cs[i*3+2]=cc.b}const g=new THREE.BufferGeometry();g.setAttribute("position",new THREE.BufferAttribute(ps,3));g.setAttribute("color",new THREE.BufferAttribute(cs,3));const pts=new THREE.Points(g,new THREE.PointsMaterial({size:.06,vertexColors:true,blending:THREE.AdditiveBlending,depthWrite:false,transparent:true,opacity:.75}));s.add(pts);function rd(t){const p=g.attributes.position.array;for(let i=0;i<N;i++){p[i*3+1]-=spd[i];if(p[i*3+1]<-9)p[i*3+1]=9}g.attributes.position.needsUpdate=true;r.render(s,cam)}window.addEventListener("hf-seek",e=>rd(e.detail.time));rd(window.__hfThreeTime||0);</script>

B. 星空慢旋:
<canvas id="stars" style="position:absolute;inset:0;z-index:0;"></canvas>
<script>const c=document.getElementById("stars"),r=new THREE.WebGLRenderer({canvas:c,alpha:true});r.setPixelRatio(1);r.setSize(1080,1920,false);const s=new THREE.Scene(),cam=new THREE.PerspectiveCamera(30,1080/1920,.1,60);cam.position.set(0,2,15);cam.lookAt(0,0,0);const N=2000,ps=new Float32Array(N*3);for(let i=0;i<N;i++){const θ=Math.random()*Math.PI*2,φ=Math.acos(2*Math.random()-1),r2=4+Math.random()*8;ps[i*3]=Math.sin(φ)*Math.cos(θ)*r2;ps[i*3+1]=Math.sin(φ)*Math.sin(θ)*r2;ps[i*3+2]=Math.cos(φ)*r2}const g=new THREE.BufferGeometry();g.setAttribute("position",new THREE.BufferAttribute(ps,3));const m=new THREE.PointsMaterial({size:.08,color:0x8899CC,blending:THREE.AdditiveBlending,depthWrite:false,transparent:true,opacity:.85});const st=new THREE.Points(g,m);s.add(st);function rd(t){st.rotation.y=t*.3;r.render(s,cam)}window.addEventListener("hf-seek",e=>rd(e.detail.time));rd(window.__hfThreeTime||0);</script>

C. 银河漩涡:
<canvas id="glx" style="position:absolute;inset:0;z-index:0;"></canvas>
<script>const c=document.getElementById("glx"),r=new THREE.WebGLRenderer({canvas:c,alpha:true});r.setPixelRatio(1);r.setSize(1080,1920,false);const s=new THREE.Scene(),cam=new THREE.PerspectiveCamera(35,1080/1920,.1,60);cam.position.set(0,4,12);cam.lookAt(0,0,0);const N=4000,ps=new Float32Array(N*3),cs=new Float32Array(N*3),A=4;for(let i=0;i<N;i++){const rad=Math.random()*6,aa=(i%A)/A*Math.PI*2,sp=rad*2.5+aa,sc=(Math.random()-.5)*rad*.4;ps[i*3]=Math.cos(sp)*rad+sc;ps[i*3+1]=(Math.random()-.5)*rad*.3;ps[i*3+2]=Math.sin(sp)*rad+sc;cs[i*3]=rad/6;cs[i*3+1]=.2+rad/6*.3;cs[i*3+2]=.8+rad/6*.2}const g=new THREE.BufferGeometry();g.setAttribute("position",new THREE.BufferAttribute(ps,3));g.setAttribute("color",new THREE.BufferAttribute(cs,3));const pts=new THREE.Points(g,new THREE.PointsMaterial({size:.07,vertexColors:true,blending:THREE.AdditiveBlending,depthWrite:false,transparent:true,opacity:.85}));s.add(pts);function rd(t){pts.rotation.y=t*.4;r.render(s,cam)}window.addEventListener("hf-seek",e=>rd(e.detail.time));rd(window.__hfThreeTime||0);</script>

D. 代码雨坠:
<canvas id="rain" style="position:absolute;inset:0;z-index:0;"></canvas>
<script>const c=document.getElementById("rain"),r=new THREE.WebGLRenderer({canvas:c,alpha:true});r.setPixelRatio(1);r.setSize(1080,1920,false);const s=new THREE.Scene(),cam=new THREE.PerspectiveCamera(50,1080/1920,.1,30);cam.position.z=10;const COLS=40,ROWS=50,COUNT=COLS*ROWS,pos=new Float32Array(COUNT*3),spd=new Float32Array(COUNT);for(let i=0;i<COUNT;i++){const col=i%COLS,row=Math.floor(i/COLS);pos[i*3]=(col-COLS/2)*0.35;pos[i*3+1]=(row-ROWS/2)*0.4+Math.random()*10;pos[i*3+2]=(Math.random()-.5)*3;spd[i]=0.05+Math.random()*0.12}const g=new THREE.BufferGeometry();g.setAttribute("position",new THREE.BufferAttribute(pos,3));const pts=new THREE.Points(g,new THREE.PointsMaterial({size:.09,color:0x00FF88,blending:THREE.AdditiveBlending,depthWrite:false,transparent:true,opacity:.8}));s.add(pts);function rd(t){const p=pts.geometry.attributes.position.array;for(let i=0;i<COUNT;i++){p[i*3+1]-=spd[i];if(p[i*3+1]<-7)p[i*3+1]=7+Math.random()*2}pts.geometry.attributes.position.needsUpdate=true;r.render(s,cam)}window.addEventListener("hf-seek",e=>rd(e.detail.time));rd(window.__hfThreeTime||0);</script>

E. 网格脉冲:
<canvas id="grid" style="position:absolute;inset:0;z-index:0;"></canvas>
<script>const c=document.getElementById("grid"),r=new THREE.WebGLRenderer({canvas:c,alpha:true});r.setPixelRatio(1);r.setSize(1080,1920,false);const s=new THREE.Scene(),cam=new THREE.PerspectiveCamera(40,1080/1920,.1,30);cam.position.set(0,3,8);cam.lookAt(0,0,0);const SIZE=20,DIVS=30,grp=new THREE.Group();for(let i=0;i<=DIVS;i++){for(let j=0;j<=DIVS;j++){const x=(i-DIVS/2)*(SIZE/DIVS),z=(j-DIVS/2)*(SIZE/DIVS);const dot=new THREE.Mesh(new THREE.SphereGeometry(.03,4,4),new THREE.MeshBasicMaterial({color:0x3366AA,transparent:true,opacity:.6}));dot.position.set(x,0,z);grp.add(dot)}}s.add(grp);function rd(t){grp.rotation.y=t*.4;for(let m of grp.children){m.position.y=Math.sin(t*2+m.position.x*.5+m.position.z*.5)*1.2}cam.position.y=3+Math.sin(t*.5)*1.5;r.render(s,cam)}window.addEventListener("hf-seek",e=>rd(e.detail.time));rd(window.__hfThreeTime||0);</script>

F. 粒子+Bloom辉光(电影感最强):
<canvas id="bg3d" style="position:absolute;inset:0;z-index:0;"></canvas>
<script>const c=document.getElementById("bg3d"),r=new THREE.WebGLRenderer({canvas:c,alpha:true,antialias:true});r.setPixelRatio(1);r.setSize(1080,1920,false);const s=new THREE.Scene(),cam=new THREE.PerspectiveCamera(35,1080/1920,.1,100);cam.position.set(0,3,12);cam.lookAt(0,0,0);const N=3000,ps=new Float32Array(N*3),cs=new Float32Array(N*3),spd=new Float32Array(N),A=4;const C1=new THREE.Color("#6C8CFF"),C2=new THREE.Color("#A855F7");for(let i=0;i<N;i++){const rad=Math.random()*6,aa=(i%A)/A*Math.PI*2,sp=rad*2.5+aa,sc=(Math.random()-.5)*rad*.4;ps[i*3]=Math.cos(sp)*rad+sc;ps[i*3+1]=(Math.random()-.5)*16;ps[i*3+2]=Math.sin(sp)*rad+sc;spd[i]=0.06+Math.random()*0.14;const t=Math.random(),cc=C1.clone().lerp(C2,t);cs[i*3]=cc.r;cs[i*3+1]=cc.g;cs[i*3+2]=cc.b}const g=new THREE.BufferGeometry();g.setAttribute("position",new THREE.BufferAttribute(ps,3));g.setAttribute("color",new THREE.BufferAttribute(cs,3));const core=new THREE.Points(g,new THREE.PointsMaterial({size:.05,vertexColors:true,blending:THREE.AdditiveBlending,depthWrite:false,transparent:true,opacity:.95}));const mid=new THREE.Points(g,new THREE.PointsMaterial({size:.16,vertexColors:true,blending:THREE.AdditiveBlending,depthWrite:false,transparent:true,opacity:.4}));const halo=new THREE.Points(g,new THREE.PointsMaterial({size:.5,vertexColors:true,blending:THREE.AdditiveBlending,depthWrite:false,transparent:true,opacity:.15}));s.add(halo);s.add(mid);s.add(core);function rd(t){const p=g.attributes.position.array;for(let i=0;i<N;i++){p[i*3+1]-=spd[i];if(p[i*3+1]<-9)p[i*3+1]=9}g.attributes.position.needsUpdate=true;r.render(s,cam)}window.addEventListener("hf-seek",e=>rd(e.detail.time));rd(window.__hfThreeTime||0);</script>"""
        # 🔴 P1：动态尺寸（横屏 1920×1080 / 竖屏 1080×1920）
        menu = menu.replace("setSize(1080,1920,false)", f"setSize({fw},{fh},false)")
        menu = menu.replace("1080/1920", f"{fw}/{fh}")
        menu = menu.replace("Vector2(1080,1920)", f"Vector2({fw},{fh})")
        return menu

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
            return self._fix_slow_rotation(html)
        print("        ⚠ Three.js 缺失 → 注入默认粒子场聚散兜底")
        # 清理 LLM 残留的空 canvas（只有 <canvas> 标签没有对应 Three.js 代码）
        html = re.sub(r'<canvas[^>]*>', '', html)
        return html + self._default_threejs(orientation)

    def _fix_slow_rotation(self, html: str) -> str:
        """🔴 强制 rotation 速度 ≥0.4 rad/s：LLM 生成变速呼吸时把 rotation.y=t*.2 写成慢速，
        螺旋臂 0.4s 才转 4.6 度=静止。正则把 rotation.y=t*X（X<0.4）强制提到 0.4。"""
        def repl(m):
            v = float(m.group(1))
            return f"rotation.y=t*{max(v, 0.4):g}"
        return re.sub(r'rotation\.y=t\*([0-9]*\.?[0-9]+)', repl, html)

    def _default_threejs(self, orientation: str) -> str:
        fw, fh = (1920, 1080) if orientation == "landscape" else (1080, 1920)
        # 蓝紫渐变粒子（对齐场景审美），N=3000，与 bg3d 技法一致的电影感
        return f"""<canvas id="pt3d" style="position:absolute;inset:0;z-index:0;"></canvas>
<script>const c=document.getElementById("pt3d"),r=new THREE.WebGLRenderer({{canvas:c,alpha:true,antialias:true}});r.setPixelRatio(1);r.setSize({fw},{fh},false);const s=new THREE.Scene(),cam=new THREE.PerspectiveCamera(35,{fw}/{fh},.1,100);cam.position.set(0,0,10);const N=3000,ps=new Float32Array(N*3),cs=new Float32Array(N*3),A=4;const C1=new THREE.Color("#6C8CFF"),C2=new THREE.Color("#A855F7");for(let i=0;i<N;i++){{ps[i*3]=(Math.random()-.5)*14;ps[i*3+1]=(Math.random()-.5)*18;ps[i*3+2]=(Math.random()-.5)*6;const t=Math.random(),cc=C1.clone().lerp(C2,t);cs[i*3]=cc.r;cs[i*3+1]=cc.g;cs[i*3+2]=cc.b}}const g=new THREE.BufferGeometry();g.setAttribute("position",new THREE.BufferAttribute(ps,3));g.setAttribute("color",new THREE.BufferAttribute(cs,3));const pts=new THREE.Points(g,new THREE.PointsMaterial({{size:.06,vertexColors:true,blending:THREE.AdditiveBlending,depthWrite:false,transparent:true,opacity:.75}}));s.add(pts);function rd(t){{pts.rotation.y=t*.45;pts.rotation.x=Math.sin(t*.9)*.12;r.render(s,cam)}}window.addEventListener("hf-seek",e=>rd(e.detail.time));rd(window.__hfThreeTime||0);</script>"""

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
