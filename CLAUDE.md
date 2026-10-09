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

## OCR 候选词提取（不在 index.html 内，独立本地脚本）

- **数据源**：`名校名师高考英语词汇全攻略（新）.pdf`（326页，纯扫描图片、无文字层，258MB；只有 p187、p188 是横版，内容顺时针转了 90°）
- **脚本**：`ocr_candidates.py`（项目根目录，纯 Python，不受"单文件原则"约束，**必须提交到 git**）。原 `ocr_extract_headwords.py` 从未 commit、已丢失，不再使用
- **依赖**：系统 Python 3.14 已装 pymupdf、opencv-python、numpy、rapidocr_onnxruntime 1.2.3；拼写检查用 Windows 自带拼写检查（PowerShell + C# COM，无需安装）。rapidocr 默认 `text_score=0.5` 会静默丢掉整行，调用时必须改为 `text_score=0, box_thresh=0.3`
- **流程**（每批 10 页，**每批开一个新会话**，节省 token）：
  1. `python -I ocr_candidates.py extract <起页> <止页>`（放后台跑，约 40 秒/页）：机器提取。整页 200dpi 和 300dpi 重叠条带各识别一次，同位置比对；做拼写检查；对残余墨迹、未匹配的青色词头、字符过稀报警。每页输出到 `候选v2/work/pNNNN/`（`ocr.json` 缓存、`machine.json`、复核条带图 `rv_1~4.jpg`）。已有 `review.json` 的页会自动跳过（重做后处理会改变候选编号，导致裁决错位）。同一时间只跑一个 extract 进程（多个进程会同时写拼写缓存）
  2. Claude 逐页复核（见验收标准第 2 条）：`python -I ocr_candidates.py show <页>` 看候选清单和报警，Read 该页 `rv_1~4.jpg` 四段条带图逐段看（先找条带图里没画线的漏词，再核对每个编号的拼写和释义）；拿不准的用 `python -I ocr_candidates.py crop <页> <y0> <y1> [x0 x1] [dpi]` 放大原图（坐标是 200dpi 转正后的像素）。裁决写入 `候选v2/work/pNNNN/review.json`
  3. `python -I ocr_candidates.py build <起页> <止页>`：校验每个候选、报警、条带都有处置，以及同一行有没有漏并的词性；还有两道拼写校验：①最终收录的词必须过 Windows 拼写检查，过不了的（旧拼法、英式拼法、词缀、专有名词等）要看原图确认后登记到 `spell_confirmed`；②两路识别结果不一致的候选不许放进 ok，必须放进 fix 并写明 `word`（逼着对原图选定拼写）。通过后输出 `候选v2/候选_pA-B.json`（导入用）和 `候选v2/待核_pA-B.md`（复核记录、未决事项）。有 undecided 的批次状态是「未完成」，要把问题整理给用户裁决，裁决后改 review.json 再 build
- **review.json 格式**（每个候选编号必须在 ok / fix / reject / undecided 里恰好出现一次，否则 build 报错）：
  ```
  {"page": 94,
   "strips_checked": [1, 2, 3, 4],
   "ok": [1, 2],                                        // 原样收
   "fix": {"5": {"word": "…", "meaning": "…", "note": "…"}},   // 改后收，word/meaning 可只给一个
   "reject": {"理由": [3, 4]},                          // 不收，按理由分组
   "undecided": {"6": "问用户的问题"},                   // 交用户裁决，不进 JSON
   "added": [{"word": "…", "meaning": "…", "after": 2, "note": "…"}],   // 机器漏掉、复核补上，after 是排在哪个编号后
   "alarms": {"A1": "结论"},                            // 每个报警都要写结论
   "meaning_checked": [7],                              // 可选：build 报“同行词性没并进释义”但确认不属于该词时登记
   "spell_confirmed": ["embassador", "-ery"],           // 可选：过不了拼写检查、但已对原图确认拼写无误的最终词
   "notes": ""}
  ```
- **复核要点**（试跑总结）：
  - 标 ✓ 的候选也要核对词性和释义：OCR 常把 vt 认成 vi/vl，释义常只截到第一个词性（email、enjoy、disturb 的错都出在 ✓ 项上）
  - 报警多数是误报（页边扫描线、谚语图标、波浪下划线、释义续行开头的青色字），但「青色词头未匹配」要认真看，everything（p101）、low（p165）这两个漏掉的词头就是这样发现的
  - 页首常是上一页词条的短语/例句续行，不收；单词在本页末、释义在下页首的，归本页
  - `A/B a. 使人/感到…的` 这种两个词共用一个释义的，拆成两条，各配各的释义
  - 模糊页用 crop 放大到 400dpi 辨认；释义里有靠猜的字要在 note 里注明
- **复核模型**：由用户自己选（目前用 Opus，effort medium），文档不做规定。看不清的页用 crop 放大到 400dpi 辨认，仍认不清的写进 undecided 交用户裁决
- **省 token 做法**：每 10 页一个新会话，不要在一个会话里连做多批；一次调用并行读 2–3 页的 `show` 输出和条带图，裁决也成批写；不要整份 Read 脚本或大 JSON，用 `show` 看候选。不要省略清单里的 ✓ 项（理由见复核要点第一条）。条带图暂不缩小，是否缩小待实测
- **收词口径**（由 p44–93 人工结果反推）：
  - 收：行首青色加粗主词条（含 `*` 开头、前缀词条如 `eco-`、连字符词如 `e-book`）
  - 收：词条正文中有独立词性和释义的派生词，如 `disturbance n.`、`easily ad.`、`*economize vi.`、`*colonize /…/ vt.`。**派生词按位置和格式判断，不按颜色**：扫描件里派生词有暗青色也有近黑色
  - 范围存疑的也收进候选，由用户在审核页删除，例如缩进短语行里的 `easy-going a.`、前缀词条里的举例词 `ecology`
  - 不收：例句、含空格的词组（导入时也会被跳过）
  - `*` 是标记，不进答案；大小写、撇号、连字符一律按原图
  - 释义要包含该词的全部词性（同一行右侧另起的词性、下一行的续行都要并入）；build 会检查同一行有没有漏并的词性
  - 原书只有词性、没有中文释义的派生词（如 `energetically ad.`）：收，由 Claude 按词根补写释义，并在词性后标「（补）」，如 `ad.（补）精力充沛地`（用户 2026-10-09 裁决）
  - 词头带括号、括号里是可省字母的（`encyclop(a)edia`、`enrol(l)`、`fulfil(l)`）：去掉括号内容，只收一条（encyclopedia、enrol、fulfil）（用户 2026-10-09 裁决）
  - 原书用了旧拼法或非标准拼法的（如 `*embassador`）：原书拼法和标准拼法各收一条（embassador + ambassador），释义相同（用户 2026-10-09 裁决）
  - 合写的词缀词头（如 `en-/-en`）：拆成两条（en-、-en），释义相同（用户 2026-10-09 裁决）
  - 括号里是会改变词义的前缀（如 `(in)experienced a.（不）富有经验的`）：拆成两条（experienced a.富有经验的、inexperienced a.不富有经验的），释义各自对应（用户 2026-10-09 裁决）
- **验收标准**（与 codex 三轮 review 后定稿）：
  1. 收录行首主词条及正文中具有独立词性和释义的派生词，范围存疑者保留，星号标记不进入答案，大小写、撇号、连字符和前缀形式按原图核实。
  2. 每个目标页的全部正文须由模型逐段复核覆盖、拼写和释义归属，先独立查找遗漏再核对候选，保留无标记原图且模糊处查看高清局部，此流程以不漏为目标但不构成零遗漏证明。
  3. 每个候选及复核新增词均须记录编号、PDF 页序、原图位置、识别来源和裁决，跨条带及跨页内容须明确归属并避免重复。
  4. 两路识别须按实际图像变换映射到同一坐标系并处理拆框合框，重叠条带只算一路，识别一致、词典命中、词表命中和置信度均不得代替视觉验收。
  5. 形状过滤、方向异常、未匹配区域和无法解释的正文英文片段均须进入待核，排除项须记录理由，不得静默删除或凭词典建议猜改。
  6. 最终条目须确认拼写与原图一致、释义归属正确且完整到足以用于默写，无法辨清或疑似原书错误者保持未决并交用户裁决。
  7. 回归集、挑战集和独立盲测集须分别报告精确拼写召回、图像位置覆盖及条目正确率，模糊匹配不得计为准确命中，因测试结果调整规则后须另选盲测页验证。
  8. 新结果仅写入 `候选v2/` 并保留旧文件不动，候选 JSON 只包含完成视觉验收且满足导入限制的条目，待核报告保留复核记录、裁图引用和未决事项。
  9. 批次仅在全部目标页完成覆盖复核、报警均有结论、未决事项清零且候选处置数量对账通过后标记完成，明确排除项须保留裁决记录。
  10. 先试跑 p94–103 并验证挑战集、盲测集及 p187–188 的页面方向，报告每页候选数、待核数、噪声数、发现的错误和复核耗时，再决定是否全量运行。
- **进度**：
  - p44–93：用旧流程（逐词截图人工核对）完成，即项目根目录的 `候选_p44-63.json` … `候选_p84-93.json`，共 1003 条，作为回归集
  - p94–193：项目根目录的 `候选_p94-103.json` … `候选_p184-193.json`（共 1436 条）是 110dpi 整页看图转录的，没有逐词核对，也漏收了派生词，**已被 v2 流程取代**，只作对照，不动不删
  - v2 试跑（2026-10-09）：p94–103 已完成，`候选v2/候选_p94-103.json` 共 231 条（含之后拆分 en-/-en 等口径调整），待裁决项已全部由用户裁决。同时跑了挑战集（p60、p75、p165、p166、p187、p188）和盲测集（p119、p181、p229、p312，用种子 20261009 抽取）：复核后回归页精确命中 72/72，盲测页除当时待裁决的项外全部命中；机器漏掉 2 个词头，都靠报警找回。复核约 3 分钟/页
  - **已预先复核好的页**：p119、p165、p166、p181、p187、p188、p229、p312 已有 review.json。跑到它们所在的批次时 extract 会自动跳过，build 直接用。p60、p75、p86 的 review.json 只用于回归测试，不进正式输出
  - `候选v2/` 下的 `候选_p60-60.json`、`候选_p119-119.json` 这类单页文件是试跑副产品，**不要导入**（p60/75/86 已在旧批次导入；其余单页会包含在正式批次文件里）
  - **下一步**：从 p104–113 开始，每 10 页一批（p104–113、p114–123 … p314–323，最后一批是 p324–326），每批开一个新会话
  - 用户如果已经导入过项目根目录的旧 `候选_p94-103.json` … `候选_p184-193.json`，导入同页码的 v2 文件前要先撤销旧的那批，否则会重复
- 候选 JSON 格式为 `[{"word","meaning","page"}]`（page 是 PDF 页序），用户在词记「默写」页点「导入候选」逐个文件导入，导入时指定周数

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
