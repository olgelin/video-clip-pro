# 画面组多卡 HTML（一段多张卡片，代码层注入依次弹入）

你是口播视频卡片设计师。下面是「画面组」里的多张信息卡片内容，每张对应一句口播，卡片会一张接一张弹出来。

## 画面组主题
{theme}

## 卡片列表（每张含类型/数据/情绪）
{cards_json}

字段含义：`headline` 标题 / `subtext` 副文 / `metric` 数字指标 / `layout` 类型 / `data` 数据点 `[{label,value}]` / `bullets` 要点 / `takeaway` 金句 / `emotion` 情绪

## 卡片类型（按 layout 字段，严格照做）

| layout | 怎么做 |
|--------|--------|
| big-number | 大字 headline + `metric` 大数字（48-72px），`data` 做成 badge 条 |
| comparison | `data` 两个数据点分列左右，中间 VS 或分隔线 |
| bullets | headline + `bullets` 列表（2-4 条带序号） |
| quote-card | 大引号 + headline + takeaway |
| title-only | headline + subtext 两行 |

## Few-Shot 示例（严格模仿结构，替换成你的字段内容）

### big-number 示例
```html
<div class="seg-card" data-seg="0">
  <div style="font-size:12px;color:#00d4ff;letter-spacing:2px;font-weight:600;">BREAKTHROUGH</div>
  <div style="font-size:52px;font-weight:900;color:#fff;font-family:monospace;line-height:1;">50%<span style="font-size:20px;color:#ffd700;">+</span></div>
  <div style="font-size:14px;color:rgba(255,255,255,0.7);">全球开发者加速采用</div>
  <div style="display:flex;gap:8px;margin-top:10px;">
    <span style="font-size:12px;padding:3px 10px;border-radius:20px;background:rgba(0,212,255,0.15);border:1px solid rgba(0,212,255,0.4);color:#00d4ff;">接入率 50%+</span>
  </div>
</div>
```

### comparison 示例
```html
<div class="seg-card" data-seg="0">
  <div style="font-size:16px;font-weight:700;color:#fff;">1人 = 10人效率</div>
  <div style="display:flex;gap:12px;margin-top:10px;align-items:center;">
    <div style="flex:1;text-align:center;">
      <div style="font-size:12px;color:rgba(255,255,255,0.5);">过去</div>
      <div style="font-size:22px;font-weight:800;color:#6c8cff;">1人=1人</div>
    </div>
    <div style="font-size:20px;font-weight:900;color:#ffd700;">VS</div>
    <div style="flex:1;text-align:center;">
      <div style="font-size:12px;color:rgba(255,255,255,0.5);">现在</div>
      <div style="font-size:22px;font-weight:800;color:#00d4ff;">1人=10人</div>
    </div>
  </div>
</div>
```

### bullets 示例
```html
<div class="seg-card" data-seg="0">
  <div style="font-size:16px;font-weight:700;color:#fff;">AI体系三层金字塔</div>
  <div style="margin-top:8px;display:flex;flex-direction:column;gap:6px;">
    <div style="font-size:13px;color:rgba(255,255,255,0.75);">01 · 底层：基础模型提供算力</div>
    <div style="font-size:13px;color:rgba(255,255,255,0.75);">02 · 中层：工具链连接生态</div>
    <div style="font-size:13px;color:rgba(255,255,255,0.75);">03 · 顶层：应用触达用户</div>
  </div>
</div>
```

### quote-card 示例
```html
<div class="seg-card" data-seg="0" style="position:relative;padding-left:40px;">
  <div style="position:absolute;left:8px;top:0;font-size:40px;color:rgba(108,140,255,0.35);">&ldquo;</div>
  <div style="font-size:16px;font-weight:800;color:#fff;">不会AI = 10年前不会用手机</div>
  <div style="font-size:12px;color:rgba(255,255,255,0.6);margin-top:6px;">拥抱AI，否则被淘汰</div>
</div>
```

## 🎨 配色铁律（🔴 必须遵守）

**单一蓝色科技风**：深色蓝紫渐变底 + 蓝 `#6c8cff` / 青 `#00d4ff` 主色，紫 `#a855f7` / 金 `#ffd700` 点缀（金只用于关键数字或 VS，最多 1-2 处）。🔴 禁止红/橙/绿，禁止多色乱混——整卡一个色系，文字以白 `#ffffff` / 浅灰为主。

## 🔴 硬性要求

1. 生成**一个** HTML 容器（`<div>`），里面包含**所有**卡片
2. 每张卡片必须用 `<div class="seg-card" data-seg="{i}">` 包裹（i 从 0 开始按顺序递增）
3. 卡片按口播顺序**竖排**（`display:flex;flex-direction:column;gap:14px`），从上到下堆叠
4. 🔴 **只用 cards_json 里的字段内容**（headline / metric / data / bullets / takeaway / subtext），**禁止自己编造文字、禁止把口播原文整句写进卡片**（原文在底部字幕里，写了会重复）
5. 🔴 **每个字段只显示一次**：headline 显示一次、data 显示一次，禁止同一个文字出现两遍
6. 🔴 **绝对不要写 `<script>` 标签，不要写任何 GSAP 动画代码**——代码层会注入"依次弹入"的时间线，你只负责静态布局
7. 🔴 **半透明背景（透出人物，绝不能用不透明黑块遮挡人脸）**：
   - 外层容器（包住所有 seg-card 的 div）**绝对禁止写 `background`**
   - 每张 seg-card 背景用 `rgba(...)`，**alpha ≤ 0.7**（如 `rgba(15,18,40,0.65)`），禁止纯色 `#` 背景

## 自检清单

- [ ] 每张卡按 layout 类型做（big-number / comparison / bullets / quote-card / title-only）
- [ ] 只用了 cards_json 的字段，没自己加口播原文整句
- [ ] 每个字段只显示一次，无重复文字
- [ ] 单主色蓝青，无红橙绿多色
- [ ] 有视觉锚点（大数字/对比/序号/引号/badge），不是纯文字
- [ ] 半透明背景透出人物

## 输出

只输出 HTML（div 结构，无 `<script>`、无解释文字）。
