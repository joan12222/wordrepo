# 项目进度

## 已完成

- **index.html**（约 1250 行）：完整 PWA 单词记忆工具，单文件实现全部功能
  - 生词本管理：首次打开选择导入 JSON 或新建，数据存 localStorage
  - PDF 解析：pdf.js 3.11.174 本地文件，利用位置/字号信息识别标题(h2/h3)和正文段落，排版层次化渲染，双击英文单词标记/取消标记；自动清除乱码字符；多页间插入分隔线；自动检测试卷格式并对选项缩进
  - Word 解析：JSZip 直接读取 .docx 内部 XML（word/document.xml），解析 `w:u` 下划线属性保留下划线空格（填空横线），支持 .doc/.docx 格式；mammoth HTML 转换后处理bold-only段落缺失问题
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
  - ~~复习连胜系统~~：**已过时，代码中不存在**——`word.reviewStats` 字段仅在 `exportJSON()` 里作为死字段透传，答题不会修改熟练度或产生连胜。熟练度变更只发生在「任务系统」（见下）和手动修改两处
  - 任务系统（今日任务/本周测验/单词速记，`S.taskSess`）：flash卡翻面 → 测验（答错的题回队尾直到全部答对）→ 全部答对后批量将词升级熟练度（今日任务→已掌握，本周测验→已存档）。核心函数：`startTaskSession()`/`renderTaskFlash()`/`buildAllQuizQs()`/`renderTaskResult()`；独立的「单词速记」模式（`startPwdSession()` 及一套 `Pwd*` 函数）结构相同但不修改熟练度
  - 熟练度管理：筛选展示 + 多选批量修改 + 单词详情内单独修改
  - 删除功能：两个入口——①多选后批量工具栏「删除」按钮（二次确认）；②单词详情弹窗内「删除此单词」
  - 导入/导出：JSON 格式，含全部字段（含扩展字段）
  - PWA：manifest 通过 Blob URL 注入，Service Worker 通过 Blob URL 注册并缓存
- **默写库**（教材周默写 + 模拟测试，v1.8.0 新增）：与生词本完全独立的第二套词库
  - 数据独立存储于 `wr_dict`（`S.dict`），词条结构 `{id,word,week,meaning,addedAt}`，不接入生词本统计/Gitee同步
  - 添加方式：「添加」屏顶部新增「普通生词 / 默写标记」模式切换（`S.addMode`），切到默写模式后，PDF 双击单词 / 选中文字（含连字符如 absent-minded）会弹窗要求填周数+释义后加入默写库；选中内容含空格（短语/句子）会被拒绝
  - 「📝 默写」为新增第5个底部导航tab：按周筛选词条列表，支持多选批量删除
  - 复习：只有一种题型——看中文释义拼写英文单词，提交后立即显示对错+正确拼写。结果页按当轮答错的词提供「🔁 重练错题」（`S.dictRetryWrongWords`），以及「重新开始（全部）」（`S.dictRetryWords`）。~~模拟测试模式~~（提交不给反馈、交卷后统一显示结果）v1.10.0 已按需求移除，只保留复习模式
  - OCR候选导入（`#s-dictimport`）：默写库页「导入候选」按钮选取 JSON 文件（格式 `[{"word","meaning","page"}]`）→ 审核页逐条勾选/编辑/删除（删除可撤销一步）/手动加空行 → 指定周数后批量导入；导入后默写库列表页顶部有「撤销本次导入」整批撤销条

## OCR 提取工具（不在 index.html 内，独立本地脚本）

- **脚本**：`ocr_extract_headwords.py`（项目根目录，纯 Python，不是 index.html 的一部分，不受"单文件原则"约束）
- **用途**：对 `名校名师高考英语词汇全攻略（新）.pdf`（326页，纯扫描图片、无文字层，258MB）跑 OCR，识别每页的粗体/蓝色（墨迹密度+像素颜色启发式）候选词条，按连续页码分块输出为「导入候选」screen 能直接吃的 JSON
- **用法**：`python ocr_extract_headwords.py <book.pdf> <output_dir> [start_page] [end_page] [chunk_size默认20]`（页码从1开始，含头含尾），每 chunk_size 页写一个 `候选_p{a}-{b}.json`
- **依赖**：需要 pymupdf(`fitz`) + opencv-python + numpy + rapidocr-onnxruntime；本机全局 pip（`python3`）装不上这些包会 `ModuleNotFoundError`，要用 `C:\Users\jun\AppData\Local\Programs\Python\Python312\python.exe` 这个解释器（已装好上述依赖）。国内网络装包用 `-i https://pypi.tuna.tsinghua.edu.cn/simple` 镜像，直连 pypi.org 经常卡死/断线
- **准确率**：已在第4页、第285页两个随机样本上人工核对，过滤后精确率都是100%（4/4、9/9），但会漏掉少量格式特殊的真实词条（召回不是100%），审核页里可以手动加漏掉的词
- **进度**：脚本已就绪并跑通冒烟测试（第4-8页），**全书326页尚未跑过**——单页约5秒，326页预计跑约28-30分钟，建议整本一次性跑完（按页码分chunk，不影响之后按周挑着导入），跑的时候丢后台、跑完再检查各chunk文件
- 提取出的候选 JSON 文件应放在项目目录下（如 `候选_p1-20.json` 这类命名），用户在词记「默写」页点「导入候选」逐个文件导入，导入时再指定对应周数

## 进行中

无

## 待完成

无（需求已全部实现）

## 下次继续的切入点

- 入口文件：`index.html`（约 1250 行）
- 关键函数行号（以当前文件为准）：
  - 生词本渲染：`renderVocab()` ~661
  - 批量删除：`batchDelete()` / `doBatchDelete()`
  - 单词详情（含删除）：`showDetail()`
  - PDF 文本清洗：`cleanPDFText()`
  - PDF 解析：`loadPDF()`，`renderPDFText()`
  - Word 解析：`loadDocx()`，`parseDocxXml()`，`parseDocxHtml()`
  - 待添加列表：`addPend()`，`clearPDF()`
  - 模式切换：`setGenMode()`
  - 手动模式提示词生成：`genManualPrompt()`
  - 手动模式 JSON 导入：`importManualJSON()`
  - 手动录入：`addManualWord()`
  - 词组选中悬浮按钮：`setupPhraseSelect()`
  - Claude API 调用：`claudeChunk()`
  - 复习题目生成：`buildQs()`
  - 连胜更新：`updateWordStreak()`
  - 四选一判题：`checkAns()`
  - 拼写题判题：`checkSpell()`
  - 数据导入/导出：`importJSON()`，`exportJSON()`
  - 默写库管理：`renderDictScreen()`，`addDictWord()`/`confirmAddDictWord()`
  - 默写复习：`startDictReview()`/`startDictSession(words)`，`buildDictQs()`，`renderDictQ()`，`submitDictAns()`，`renderDictResult()`（含重练错题）
  - 默写候选导入：`onDictImportFile()`，`renderDictImportScreen()`，`confirmDictImport()`，`undoDictImportBatch()`

## 版本管理

- **当前版本**：v2.0.0
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

## 单词数据结构

```json
{
  "word": "run",
  "headword": "run",
  "phonetic": "/rʌn/",
  "proficiency": "完全不会",
  "chineseDefinition": "跑；运行",
  "englishDefinition": "to move fast using your legs",
  "usage": "v. 不及物/及物动词",
  "morphology": "runs / ran / run / running",
  "examples": "She runs every morning.",
  "exampleTranslation": "她每天早晨跑步。",
  "target": "四级核心词",
  "priority": "1",
  "irregular": "run / ran / run",
  "reviewStats": {},
  "addedAt": "2026-03-13T00:00:00.000Z"
}
```

- `headword`：词目原形（通常与 word 相同，词形变化时可能不同）
- `phonetic`：音标
- `morphology`：词形变化（三单/过去式/分词/比较级等）
- `exampleTranslation`：例句中文译文
- `target`：学习目标/分类标签
- `priority`：优先级（数字或文字）
- `irregular`：不规则变化形式，仅不规则动词/名词有此字段
