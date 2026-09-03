"""hf_build_pip v82 — 从 storyboard 接收场景，生成HTML
架构: storyboard(分镜+视觉方向) → Python框架(grid+粒子+辉光) → Scene LLM(Three.js+标题+标签)
"""
import json, re, time
from pathlib import Path
from skills._common.scene_base import SceneBuilderBase


class Hf_build_pip(SceneBuilderBase):
    name = "hf_build_pip"

    def execute(self, context: dict) -> dict:
        provider = context.get("provider")
        scenes = context.get("scenes", [])
        if not scenes:
            print("  ⛔ 无 storyboard 场景")
            return {"html_files": [], "review": {}}

        n = len(scenes)
        print(f"\n[6/6] PIP — {n}场景")

        # 🔴 P1：检测输入视频方向（竖屏/横屏），动态场景尺寸
        from core.hf_card_builder import _detect_orientation
        orientation = _detect_orientation(context.get("video_path", ""))
        print(f"      方向: {'横屏 1920×1080' if orientation == 'landscape' else '竖屏 1080×1920'}")

        from skills.hf_build_pip.color_grader import grade
        from skills.hf_build_pip.motion_director import direct as motion_gen
        from skills.hf_build_pip.stage_template import build_stage

        scene_prompt_tpl = self.load_prompt("scene_system")
        output_dir = Path(context.get("output_dir", ".")) / "hf_build_pip"
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
                stage = build_stage(idx, dur, palette, motion, ghost=ghost, quote=quote, llm_motion=llm_motion, orientation=orientation)
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
            print(f"\n[渲染] HyperFrames 合成 {len(render_ranges)} 个全屏场景 (PIP)...")
            hf_dir = build_hyperframes_composition(render_edl, words, project_root, video_path, layout_mode="pip")
            if hf_dir:
                polished = render_hyperframes(hf_dir)
                if polished:
                    return {"final_polished": str(polished)}
        except Exception as e:
            print(f"      PIP 渲染错误: {e}")
        return {}

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








