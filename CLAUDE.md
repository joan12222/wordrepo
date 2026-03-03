# 项目进度

## 已完成

- **index.html**（约 1600 行）：完整 PWA 单词记忆工具，单文件实现全部功能
  - 生词本管理：首次打开选择导入 JSON 或新建，数据存 localStorage
  - PDF 解析：pdf.js 3.11.174 本地文件，利用位置/字号信息识别标题(h2/h3)和正文段落，排版层次化渲染，双击英文单词标记/取消标记；自动清除乱码字符；多页间插入分隔线；自动检测试卷格式并对选项缩进
  - 已存在单词检测：双击已在生词本的单词提示「已存在」
  - 手动录入：屏顶部始终显示输入框，Enter 提交，支持词组（含空格）
  - 词组选中：PDF 内选中文字后出现悬浮按钮可添加词组（mouseup/touchend 触发）
  - 复合词修复：`loadPDF()` 拼接后对 `word - word` → `word-word` 做替换
  - 释义生成支持两种模式（切换开关，默认手动模式）：
    - **手动模式**：点击「生成释义提示词」→ 显示格式化提示词文本框 + 一键复制 → 用户去 claude.ai 获取 JSON → 粘贴回工具点「导入释义」
    - **API 模式**：调用 claude-sonnet-4-6，每批 15 个单词，返回 JSON 含中文释义/英文释义/用法说明/例句
  - 手动模式 JSON 字段兼容两套 key：`chinese/english/example`（提示词模板格式）和 `chineseDefinition/englishDefinition/examples`（内部格式）
  - 单词复习：按熟练度多选筛选，每词最多 4 题（2 道四选一 + 2 道拼写输入），答后显示解析
    - w2c：看单词选中文（四选一）
    - d2w：看英文释义选单词（四选一）
    - c2w_spell：看中文释义，手动拼写英文单词
    - e2w_spell：看英文释义，手动拼写英文单词
  - 复习连胜系统（「单词 × 题型」二维粒度，存于 `word.reviewStats`）：
    - 进入复习时「完全不会」→「掌握中」
    - 某题型连胜 ≥ 5：本轮跳过该题型
    - 全部 4 种题型连胜均 ≥ 3：自动升为「已掌握」
    - 答错：该题型连胜归零
    - `reviewStats` 随 JSON 导出保留
  - 熟练度管理：筛选展示 + 多选批量修改 + 单词详情内单独修改
  - 删除功能：两个入口——①多选后批量工具栏「删除」按钮（二次确认）；②单词详情弹窗内「删除此单词」
  - 导入/导出：JSON 格式，含全部字段
  - PWA：manifest 通过 Blob URL 注入，Service Worker 通过 Blob URL 注册并缓存

## 进行中

无

## 待完成

无（需求已全部实现）

## 下次继续的切入点

- 入口文件：`index.html`（约 1600 行）
- 关键函数行号（以当前文件为准）：
  - 生词本渲染：`renderVocab()` 第 661 行
  - 批量删除：`batchDelete()` 第 744 行，`doBatchDelete()` 第 755 行
  - 单词详情（含删除）：`showDetail()` 第 761 行
  - PDF 文本清洗：`cleanPDFText()` 第 807 行
  - PDF 解析：`loadPDF()` 第 816 行，`renderPDFText()` 第 885 行
  - 待添加列表：`addPend()` 第 933 行，`clearPDF()` 第 1078 行
  - 模式切换：`setGenMode()` 第 990 行
  - 手动模式提示词生成：`genManualPrompt()` 第 1001 行
  - 手动模式 JSON 导入：`importManualJSON()` 第 1031 行
  - 手动录入：`addManualWord()` 第 1090 行
  - 词组选中悬浮按钮：`setupPhraseSelect()` 第 1102 行
  - Claude API 调用：`claudeChunk()` 第 1178 行
  - 复习题目生成：`buildQs()` 第 1286 行
  - 连胜更新：`updateWordStreak()` 第 1399 行
  - 四选一判题：`checkAns()` 第 1410 行
  - 拼写题判题：`checkSpell()` 第 1435 行
  - 数据导入/导出：`importJSON()` 第 1508 行，`exportJSON()` 第 1554 行

## 版本管理

- **当前版本**：v1.2.7
- **版本规则**：每次修改代码后必须同步更新版本号，共三处：
  1. 首页 `<p class="home-ver">v x.x.x</p>`
  2. 设置页「关于」卡片内的版本 badge
  3. Service Worker 缓存名 `const CACHE='wr-x.x.x'`（缓存名变更可自动清理旧缓存）
- **版本号规则**：功能新增 → 中间位 +1（如 1.1→1.2）；小修小补 → 末位 +1（如 1.1.0→1.1.1）

## 重要约定

- **单文件原则**：所有功能在 `index.html` 内实现，不新增文件
- **pdf.js**：本地文件 `pdf.min.js` + `pdf.worker.min.js`，版本 3.11.174
- **Claude API**：使用 `claude-sonnet-4-6`，浏览器直接请求需带 `anthropic-dangerous-direct-browser-access: true` 头
- **熟练度枚举**：`完全不会` / `掌握中` / `已掌握`，对应 CSS 类 `b0` / `b1` / `b2`
- **单词 ID**：由 `uid()` 生成（`Date.now().toString(36) + random`），纯字母数字，可安全用于 HTML `onclick` 属性
- **HTML 注入防护**：动态内容统一通过 `esc()` 函数转义；onclick 中只传数字索引或已知安全字符串
- **词库存储键**：`wr_vocab`（生词本）、`wr_apikey`（API Key）
- **生成模式**：`S.genMode` 状态，`'manual'`（默认）或 `'api'`；`setGenMode()` 切换时同步 UI 显隐
- **手动模式 JSON 兼容**：`importManualJSON()` 同时接受 `chinese/english/example` 和 `chineseDefinition/englishDefinition/examples` 两套字段名
- **拼写题**：`checkSpell()` 大小写不敏感比对，Enter 键可提交；`.spell-inp.ok/.no` 控制输入框颜色反馈
- **reviewStats 结构**：`{w2c:{streak:n}, d2w:{streak:n}, c2w_spell:{streak:n}, e2w_spell:{streak:n}}`，缺失字段默认 streak=0；旧数据兼容（`?.` 可选链）
