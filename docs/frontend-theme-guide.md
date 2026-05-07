# 前端主题接入约定

新增功能页面默认使用全局命令中心主题，不再单独写一套孤立皮肤。

## 页面结构

推荐页面根节点：

```vue
<section class="page xxx-command-page">
  <header class="hero-shell xxx-hero">
    <div class="hero-main">
      <p class="hero-kicker">MODULE</p>
      <h2>模块标题</h2>
      <p class="hero-lead">说明当前模块解决什么问题。</p>
      <div class="hero-pills">
        <span class="hero-pill">关键能力</span>
      </div>
    </div>
    <aside class="hero-side">
      <div class="status-block">
        <span>当前重点</span>
        <strong>一句话说明</strong>
        <small>补充说明。</small>
      </div>
    </aside>
  </header>
</section>
```

## 常用组件类

- `summary-card`：首页或模块数据指标卡。
- `dashboard-panel`：主要内容面板，自动适配明暗主题和玻璃渐变。
- `panel-title` + `panel-tag`：面板标题与右侧标签。
- `stack-list` + `stack-item`：纵向信息列表。
- `action-btn` / `action-btn subtle` / `ghost-button` / `text-link`：操作按钮。
- `text-input` / `text-area` / `filter-input`：表单输入控件。
- `table-shell` + `mini-table`：表格容器。

## 主题原则

- 不在页面里硬编码大面积白底或黑底，优先使用 `var(--panel)`、`var(--panel-strong)`、`var(--border-soft)`、`var(--text)`、`var(--muted)`。
- 新页面若需要少量局部样式，只写布局和尺寸；颜色、边框、阴影尽量复用全局变量。
- 明暗主题由 `html[data-theme="dark"]` 统一控制，页面内不要再重复造一套暗色覆盖。
