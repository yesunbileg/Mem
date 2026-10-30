# Mem — AI урт хугацааны санах ойн загвар v0.2

Төлөв: хэрэглэгч main дээр хэрэгжүүлэлт эхлүүлэхийг зөвшөөрсөн; үр дүнгээр сайжруулах загвар. Огноо: 2026-10-30.

## 1. Зорилго ба шийдвэрийн эх сурвалж

AI өмнөх ажил, хэрэглэгчийн нөхцөл, зорилго, бодит үр дүнг хэрэгтэй үед нь олж, эх сурвалжтайгаар ашигладаг хувийн санах ой байгуулна. Хэрэглэгч уншиж, засварлаж чадна. Тусгай UI (ю-ай) хийхгүй.

Эх сурвалж: хэрэглэгчийн хавсаргасан `Pasted text.txt`, энэ чат дахь гурван хариулт, “эх төлөвлөгөө бол ерөнхий чиглэл, сайжруулж болно; just plan” гэсэн сүүлийн заавар. Хавсралтын давхардсан хэсгүүдийг нэгтгэв. Тэндхүү “архитектур зөвшөөрөгдсөн” гэдгийг энэ шинэ загварын зөвшөөрөл гэж тооцоогүй.

Шалгасан одоогийн байдал: `/workspace/Mem` дотор хэрэгжүүлэлтийн файл, dependency manifest, тест байхгүй. Доорх бүтэц, API, технологийн нарийвчлал нь шинээр санал болгож буй шийдэл.

### Хэрэглэгчийн өгсөн чиглэл

- L3/L2: Markdown (маркдаун), шууд уншиж/засварлаж болох үндсэн эх.
- L1: SQLite (эс-кью-лайт) үндсэн database (дэйтабэйс); MCP (эм-си-пи)-ээр хайх, унших, бичлэг болон засварын тайлбар нэмэх.
- Нэгдсэн индекс: L3/L2 **болон L1 database**-аас дахин үүсэх cache (кэш).
- Эхний хувилбар: нэг компьютер. Obsidian (обсидиан) хэрэглэх боломжтой, түүнээс систем хамаарахгүй.
- AI хэрэгтэй үед санах ойг ашиглах бүрдээ тусгай зөвшөөрөл асуухгүй. Гэхдээ ард байнга Inbox ажиглаж, өөрөө шинэ memory (мэмори) үүсгэхгүй. “Байнга ажиллана” гэсэн сонголтыг дагалдах тайлбараар нь ингэж тодруулсан.
- L1 бол бодит болсон, чухал, хэрэглэгч/төслийн онцлог түүх. Энгийн асуулт, AI-ийн хэрэгжээгүй санал, интернэтээс хуулсан ерөнхий мэдээлэл биш.
- 2026-10-30: хэрэглэгч төлөвлөгөөний дагуу main дээр хэрэгжүүлэлт эхлүүлэхийг хүссэн. Remote push энэ хүсэлтэд ороогүй.

### Энэ хувилбарт санал болгосон сонголтууд

Python 3.12+, албан ёсны Python MCP SDK, stdio (стүдио) холболт, SQLite FTS5 (эф-ти-эс-файв), долоон MCP хэрэгсэл. Python 3.12-ыг эхний баталгаажуулах суурь болгоно; бодит OS/client тодорхой болмогц нийцлийг шалгана. SDK болон dependency-ийн яг хувилбарыг хэрэгжүүлэх үед нийцлээр сонгож `uv.lock`-д тогтооно. Backend дотор өөрийн LLM/API key шаардахгүй: холбогдсон AI agent утга, ач холбогдлыг шийднэ.

Нэр томьёо: canonical (каноникал) — үндсэн эх; journal (журнал) — үйлдлийг сэргээх бүртгэл; patch (пэтч) — нэг багц өөрчлөлт; idempotency (айдемпотенси) — ижил хүсэлтийг дахин явуулахад үр дүн давхардахгүй байх; backup/restore (бэкап/ристор) — нөөцлөх/сэргээх; checkpoint (чекпойнт) — үр дүнгээр төлөвлөгөөг дахин үнэлэх цэг.

## 2. Хамрах хүрээ

Амжилт гэдэг нь AI одоогийн нөхцөлийг L3/L2-оос ойлгож, өмнөх бодит үр дүнг L1-аас эх сурвалжтай олж, шинэчлэлтийг давхардуулахгүй хадгалж, архивлаад, тасалдлын дараа сэргээж чаддаг болохыг хэлнэ.

Эхний хувилбарт тусгай UI, embeddings/vector search, cloud sync, олон компьютерийн merge, scheduler, Inbox watcher, автоматаар гаднын сервисээс мэдээлэл татах ажиллагаа орохгүй. Client MCP серверийг session-ийн турш нээлттэй байлгаж болно; сервер зөвхөн хүсэлт ирэхэд ажил хийнэ.

Зайлсхийх үр дүн: ярьсан бүхнийг memory болгох; AI-ийн таамгийг баримт гэж тэмдэглэх; эвдэрсэн индексийг өгөгдөл алдагдсан гэж андуулах; шинэчлэлтээр хуучин түүхээ алдах; архивласан эхээ давхар боловсруулж шинэ түүх үүсгэх.

## 3. Сонгож болох архитектурууд

| Хувилбар | Давуу тал | Сул тал / дүгнэлт |
|---|---|---|
| Markdown + SQLite руу дараалан шууд бичих | Анхны код бага | Дундаа тасарвал хэсэгчилсэн төлөв үлдэнэ. Зөвхөн throwaway туршилтад тохиромжтой. |
| Markdown + SQLite + durable operation journal | Хэрэглэгчийн хадгалалтын сонголтыг дагана; retry/recovery тодорхой | Бичилтийн урсгал илүү нарийн. **Энэ төлөвлөгөөний санал болгосон сонголт.** |
| Бүгдийг SQLite-д хадгалаад Markdown export хийх | Нэг database transaction хялбар | L3/L2 үндсэн Markdown, шууд засварлах шаардлагыг өөрчилнө. Одоогийн чиглэлд тохирохгүй. |

Хэрэглэгч төлөвлөгөөний дагуу эхлүүлэхийг зөвшөөрсөн; хэрэгжүүлэлтийн нотолгоогоор энэ загварыг шинэчилнэ.

## 4. Давхаргуудын үүрэг

| Хэсэг | Юуг хадгалах | Юуг хадгалахгүй |
|---|---|---|
| L0 Inbox | Оруулсан эхийн bytes-ийг 1:1, боловсруулаагүй харилцан яриа/өгөгдөл | Чимээгүй өөрчилсөн, дутуу эх |
| L0 Archive | Боловсруулсан эх, hash, холбоос, үр дүнтэй immutable ZIP | Нэг хуучин ZIP-ийг байнга дахин бичих |
| L3 | Товч одоогийн зураг: device, OS, app, project, ерөнхий зорилго, хэрэглэгч өөрөө өгсөн чухал нөхцөл | Дэлгэрэнгүй log, үндэслэлгүй эрүүл мэнд/зан төлөвийн дүгнэлт |
| L2 | Topic/project тус бүрийн зорилго, хүссэн үр дүн, constraints, шийдвэр, мэдсэн зүйл, дараагийн алхам, agent анхаарах зүйл | Харилцан яриаг бүхэлд нь хуулсан текст |
| L1 | Бодит үйлдэл, үр дүн, тестийн дүн, хэрэгжсэн өөрчлөлт, бодитоор гаргасан чухал шийдвэр; correction холбоостой | Зүгээр асуусан асуулт, хэрэгжээгүй AI санал, ерөнхий интернэт мэдлэг |

“Интернэтээс олдохгүй” гэдгийг хувийн нөхцөл, тухайн төсөл дээр яг юу болсон гэдгээр ойлгоно. Нийтэд мэдэгддэг аргыг энэ төсөл дээр хэрэглэсэн бодит үр дүн L1-д орж болно.

Үнэн эсэх ба ач холбогдлыг код дангаараа батлахгүй. Agent сонгоно; код required metadata, эх сурвалж, формат, холбоос, idempotency, хувилбарын зөрчлийг шалгана. L1 evidence нь `user_reported` эсвэл `tool_observed`; user хэлснийг өөрөө шалгасан мэт бичихгүй. `occurred_at` тодорхойгүй бол `null`, `recorded_at`-ыг backend UTC-ээр өгнө. Эдгээрийг андуурахгүй.

MCP-ээр L3/L2-г өөрчлөхөд өмнөх хувилбар L1 database-ийн `document_revisions` техникийн хүснэгтэд хадгалагдана. Энэ нь хайлт дээр бодит үйл явдлын түүхтэй холилдохгүй. Утгатай бодит өөрчлөлтийг agent тусад нь L1 event болгон оруулна. Хэрэглэгч Markdown-ийг гаднаас зассан бол хайлт хүсэлт дээр өөрчлөлтийг индексэлнэ; автоматаар утгын тайлбар/event үүсгэхгүй. Хоёр хүсэлтийн хооронд гаднын editor-оор хийсэн бүх завсрын хувилбарыг watcher-гүй систем сэргээж чадахгүй. Тэдгээрийн хувилбарын хяналт нь Obsidian Git/editor history-ийн үүрэг; backend-ийн before-image амлалт нь зөвхөн MCP-ээр хийсэн бичилтээс эхэлнэ.

Одоогийн session-оос шууд memory бичихэд Inbox заавал шаардахгүй. Patch нь evidence төрөл, `origin_ref` (session/message/tool-result locator), тухайн баримтыг дэмжих хамгийн бага `excerpt` өгнө. Backend excerpt-ийн SHA-256-ийг өөрөө тооцож, L1 `sources`-д excerpt ба locator-ийг тогтвортой хадгална; `event_sources` нь event-тэй холбох хүснэгт. Нэг excerpt дээд тал нь 64 KiB; бүтэн яриаг далдуур хуулж хадгалахгүй. Зөвхөн locator өгөөд дараа нь олдохгүй provenance үүсгэхийг зөвшөөрөхгүй. Энэ нь agent-ийн нотолгооны хуулбар болохоос гаднын tool дээрх үнэн байдлыг криптографаар баталсан гэсэн үг биш. Document change-ийн source refs нь мөн revision record-д хадгалагдана.

## 5. Файл ба өгөгдлийн бүтэц

```text
Mem/
  L0/Inbox/                         # эх файлууд; filename + hash-ээр сонгоно
  L0/Archive/README.md              # нэг ерөнхий тайлбар
  L0/Archive/YYYY/MM/<operation-id>/<topic-matching-name>.zip
  L3/devices.md                     # жишээ нэр; тухайн мэдээлэл байвал үүсгэнэ
  L3/projects.md
  L3/profile.md
  L2/<readable-topic-name>/context.md
  L1/history.sqlite3               # ҮНДСЭН өгөгдөл, устгаж rebuild хийхгүй
  Backend/pyproject.toml
  Backend/uv.lock
  Backend/src/mem/                  # MCP, storage, validation, recovery
  Backend/migrations/
  Backend/tests/
  Backend/skills/memory/SKILL.md
  Backend/.state/search.sqlite3    # зөвхөн сэргээгдэх индекс
  Backend/.state/                  # lock, түр staging, ажиллагааны туслах файлууд
  docs/superpowers/specs/
  docs/superpowers/plans/
```

`topic_id`, `document_id`, `event_id` нь backend үүсгэсэн UUID (ю-ю-ай-ди). Файлын нэр, slug, замаас гаргахгүй. Шинэ объектууд нэг patch дотор `new:device-main` зэрэг түр ref-ээр харилцан холбогдож болно; хадгалахдаа UUID болгож, mapping буцаана. Retry нь өмнөх mapping-ийг буцаана.

Markdown frontmatter (фронтмэттер): `schema_version: 1`, `document_id`, `layer: L3|L2`, `topic_ids`, `title`, `updated_at`. UTF-8, Unicode NFC. `expected_sha256` нь файлын бодит bytes-ийг хэшилнэ; хүн гаднаас зассан өөрчлөлтийг revision дугаараар анзааралгүй алдахгүй. `updated_at` нь зохиогчийн өгсөн хугацаа; индексийн `observed_at` тусдаа.

Логик холбоос: `mem://topic/<uuid>`, `mem://document/<uuid>`, `mem://event/<uuid>`. Backend ID → одоогийн байрлалыг resolve хийнэ. Obsidian-ийн relative link-ийг нэмэлтээр ашиглаж болно; ердийн Obsidian ийм `mem://` холбоосыг өөрөө нээх ёстой гэж үзэхгүй. MCP-ээр зөөсөн файлд document ID хэвээр; эх үүсвэрт давхардсан ID байвал индекс чимээгүй сонгохгүй, алдаа гаргана.

L1 үндсэн хүснэгтүүд: `topics`, `events`, `event_topics`, `sources`, `event_sources`, `document_revisions`, `operations`, `operation_documents`, `operation_sources`, `processed_sources`, `metadata`. Event нь immutable; correction нь өмнөх event-ийг заасан шинэ event. Topic нэр өөрчлөгдөж болно, ID өөрчлөгдөхгүй; topic revision-ийг optimistic concurrency шалгалтад ашиглана. `operations` ба before/after snapshot нь cache биш: тасалдлын дараах сэргээх өгөгдөл учраас L1 backup-д хамт орно.

## 6. Нэг бичилтийн хаалга, тасалдлаас сэргээх урсгал

`memory_apply_patch` нь утгын өөрчлөлтийн нэгдсэн хаалга. Бүх өөрчлөлт бүр L3, L2, L1 гурвууланд бичих шаардлагагүй; тухайн patch-д хэрэгтэй өөрчлөлтүүдийг бүхэлд нь амжилттай хадгална. Архивын cache шинэчлэлт нь үндсэн хадгалалтын баталгаа биш.

1. Нэг process/thread-ийн serialize ажиллагаа болон компьютер дээрх **нэг writer-ийн lock** авна. Хоёр MCP process нэг root нээхэд хоёр дахь нь тодорхой `STORE_BUSY` алдаа авна. Maintenance команд ч ижил lock ашиглана.
2. Хүлээгдэж буй recovery-г гүйцэтгэнэ. Schema, зөвшөөрөгдсөн зам, source hash, document hash, topic/event холбоос, UTF-8, хэмжээг шалгана. Бүх validation амжилттай болохоос өмнө үндсэн өгөгдөл өөрчлөхгүй.
3. `idempotency_key`-г шалгана. Ижил key + ижил normalized request → өмнөх үр дүн/ID. Ижил key + өөр request → `IDEMPOTENCY_CONFLICT`.
4. L1 SQLite transaction-д `PREPARED` operation, шинэ UUID mapping, before/after document bytes, эх Inbox snapshot, manifest-ийг хадгална. `foreign_keys=ON`, WAL, `synchronous=FULL`, `busy_timeout=5000` ашиглана.
5. Файлыг нэг filesystem дотор temp file + flush/fsync + atomic replacement-аар суулгана. Дарж солихын яг өмнө hash-ийг дахин шалгана. Move-ийн destination байгаа бол дарж бичихгүй. Recovery нь тухайн замын bytes before/after-ийн альтай тохирч байгааг харж үргэлжилнэ.
6. Бүх document зөв байрласны дараа L1 events, corrections, revisions болон operation-ийн `APPLIED` төлөвийг **нэг SQLite transaction**-аар commit хийнэ. Тэр хүртэл гаднах MCP read/search нь хэсэгчилсэн үр дүн үзүүлэхгүй.
7. Тодорхой тэмдэглэсэн Inbox item-уудыг архивлана. Дуусвал `DONE`; алдаа гарвал `APPLIED` хэвээр, `archive_status=pending` буцаана. Retry шинэ event үүсгэхгүй. Cache update алдаа гарсан нь үндсэн өгөгдлийг буцааж бичих шалтгаан болохгүй.

Энэ бол filesystem + SQLite-г хамарсан жинхэнэ ACID transaction биш. Дэмжигдэх амлалт нь: нэг writer, durable journal, дахин оролдож болох үйлдэл, process restart үед сэргээх, эргэлзээтэй төлөвт чимээгүй overwrite хийхгүй байх. Эхний баталгаажуулалт нь local filesystem дээрх process termination/retry; network drive дэмжихгүй. Disk/power loss-ын баталгаа нь OS/filesystem-ийн flush semantics-ээс хамаарна, энэ хувилбар дурын hardware failure-д өгөгдөл алдагдахгүй гэж амлахгүй. Startup integrity check болон тусдаа backup нь энэ эрсдэлийг илрүүлж/сэргээхэд хэрэглэгдэнэ.

Recovery үед path нь before ч биш after ч биш бол `RECOVERY_CONFLICT`; snapshot-уудыг хадгалж, хэвийн read/write/search-ийг зогсооно. `health` болон оношлох команд ажиллана. Хэрэглэгч/хөгжүүлэгч зөрчлийг шийдвэрлэсний дараа recovery-г дахин ажиллуулна; backend өөрөө тааж overwrite хийхгүй.

Obsidian зэрэг гаднын editor энэ lock-ийг дагахгүй. Хамгаалалт нь optimistic hash check; дурын editor яг replace мөчид зэрэг бичихийг бүрэн хориглож чадахгүй. Дэмжигдэх ажлын горим: MCP бичилт үргэлжилж байх богино хугацаанд нэг файлыг гаднаас зэрэг засахгүй. Илүү хүчтэй live-edit coordination хэрэгтэй бол тусдаа дараагийн дизайн болно.

## 7. Inbox ба архив

Inbox-ийг AI зөвхөн тухайн session/task дотор хэрэгтэй үед list/read хийнэ. Backend утгыг хураангуйлахгүй, timer/polling ажиллуулахгүй.

Patch нь сонгосон source бүрийн `relative_path`, `expected_sha256`, processing outcome-ийг агуулна. `recorded` outcome нь түүнтэй холбоотой дор хаяж нэг document/event өөрчлөлттэй; `no_memory` нь яагаад санах зүйлгүйг товч тайлбарласан operational тэмдэглэлтэй. Чухал зүйлгүй яриаг зохиомол L1 event үүсгэж байж архивлахгүй. Source-ийг хэсэгчлэн ашигласан бол `close_inbox`-д оруулахгүй.

Архивлахаас **өмнө `.md` эхийн архивлагдах нэрийг агуулгын сэдэвтэй нь тохируулна**. Жишээ: `chat-001.md` → `Mem-MCP-холболтын-шийдвэр.md`. Agent нь completion-д `archive_filename` өгнө; backend нэрийг шалгаж, journal-д анхны path/name болон шинэ archive name-ийг хадгална. Олон сэдэвтэй эхэд агуулгыг бүхэлд нь төлөөлөх нэр сонгоно; нэрлэхийн тулд эхийг таслах/хураангуйлахгүй. Нэр нь ID биш, эх bytes өөрчлөгдөхгүй. Markdown биш эхэд өргөтгөлийг нь хадгална.

APPLIED-ийн дараа raw snapshot-ийн staging хуулбарыг энэ нэрээр нэрлээд шинэ ZIP үүсгэнэ. Inbox дахь эхийг ZIP баталгаажтал анхны байранд нь хадгална. ZIP дотор сэдэвт тохирсон нэртэй эх файл, `manifest.json` байна; ZIP ч ижил нэрийн stem-тэй байна. Manifest: source hash, operation ID, original filename/path, archive filename, processing outcome, холбогдох document/event ID, archived_at. Нэр нь basename байх бөгөөд зам, escaping нэр, нэг operation доторх давхардсан destination-ийг зөвшөөрөхгүй. Retry journal-д хадгалсан нэрийг ашиглаж шинэ нэр зохиохгүй. ZIP CRC болон задласан эхийн SHA-256-ийг шалгаж байж final байрлалд тавина. Нэг final ZIP-ийг өөрчлөхгүй; байгаа ZIP таарч байвал retry-ийн өмнөх үр дүн гэж үзнэ, зөрвөл алдаа.

Final ZIP зөв болсон үед л Inbox дахь эхийг устгана, мөн түүний hash анхны hash хэвээр эсэхийг шалгана. Хэрэглэгч файлыг өөрчилсөн бол шинэ хувилбар Inbox-д үлдэнэ, уншсан хуучин snapshot архивлагдана. ZIP бүтэлгүйтвэл snapshot болон Inbox-ийг алдахгүй.

Нэг source hash-ийг шинэ key-ээр дахин бүхэлд нь боловсруулахад `SOURCE_ALREADY_PROCESSED` гэж буцаана. Дахин оруулсан duplicate файл Inbox-д үлдэж, өмнөх archive ref-ийг харуулна; backend өөрөө чимээгүй устгахгүй. Source hash нь provenance-ийн давхардлыг барина, төстэй утгатай хоёр event-ийн үнэн эсэхийг автоматаар нэгтгэхгүй.

## 8. Хайлт ба MCP

Индекс: `Backend/.state/search.sqlite3`; SQLite FTS5 `unicode61`, NFC текст, case-insensitive literal үгийн хайлт, Монгол кирилл/English хосолсон агуулга. Эхний хувилбарт morphology, transliteration expansion, semantic search амлахгүй. SQL/MATCH raw syntax-ийг хэрэглэгчийн query болгон шууд ажиллуулахгүй. Хоосон query → validation error. Дээд хязгаар: `query=500` тэмдэгт, `limit=1..100` (default 20).

Нэгдсэн индексийн зориулалт нь нэг асуултаар L3, L2, L1 гурваас холбогдох мэдээллийн байрлалыг олох. Жишээ нь “Mem MCP” хайлт L3-ийн project товч, L2-ийн зорилго/шийдвэр, L1-ийн бодит тестийн үр дүнг нэг дор олно. Индекс өөрөө шинэ memory үүсгэхгүй, үндсэн эхийг орлохгүй; олдсон үр дүнгээс MCP эх document/event-ийг уншина. Маш жижиг санд хүсэлт бүрээр бүх эхийг уншиж хайж болох ч хэмжээ өсөхөд хүсэлт бүрийн давтагдах parse/search ажлыг индекс багасгана. Raw Inbox/ZIP default нэгдсэн хайлтад орохгүй.

Search хүсэлт бүрт L3/L2 inventory + SHA-256, L1 `source_revision`-ийг шалгаж шаардлагатай cache refresh хийнэ. Тиймээс Obsidian-аар шинээр нэмсэн үг дараагийн хүсэлтээс хайгдана. Эхний хувилбар бага хэмжээний хувийн сан гэж үзсэн; томроход хэмжилтээр incremental optimization хийнэ. Timer байхгүй. Malformed Markdown, duplicate IDs, broken required refs-ийг бүтэн сангийн шалгалтаар ил тод мэдээлж, дутуу индексийг бүрэн мэт буцаахгүй.

Search result: төрөл, ID/ref, topic ID, title, snippet, `source_etag`, evidence төрөл, score. L3/L2 current text ба L1 original/correction history ялгаатай тэмдэглэгээтэй байна. Correction нь `corrects_event_id`-аар өмнөх event эсвэл хамгийн сүүлийн correction-ийг заасан нэг шугаман chain байна; аль хэдийн correction-той node-д шинэ салбар залгахыг `CONFLICT` гэж буцаана. `memory_read` original болон бүтэн chain, `effective_event` болгон chain-ийн сүүлчийн бичлэгийг өгнө. Хуучин үгээр search хийсэн үед хуучин event олдож болно, гэхдээ `record_status=corrected`, `latest_correction_ref`, шинэ үр дүнгийн товч тайлбар заавал дагалдана. Хуучирсан event-ийг ганцааранг нь current truth гэж гаргахгүй. Өөр төрлийн score-уудыг “үнэн байх магадлал” гэж тайлбарлахгүй.

| MCP tool | Үүрэг |
|---|---|
| `memory_search(query, layers, topic_ids, limit)` | L3/L2/L1 нэгдсэн literal хайлт |
| `memory_read(ref)` | Topic/document/event/source-ийг canonical эхээс унших; hash ба холбоос буцаах |
| `memory_apply_patch(patch)` | Topic/doc/event үүсгэх, doc шинэчлэх/зөөх, correction нэмэх, сонгосон Inbox item дуусгах |
| `memory_inbox_list(cursor, limit)` | Inbox жагсаалт, path, хэмжээ, content hash |
| `memory_inbox_read(relative_path, expected_sha256)` | Сонгосон эхийг 1:1 унших, зөрүүтэй hash-д алдаа |
| `memory_reindex()` | Зөвхөн cache-ийг canonical эхээс бүрэн сэргээх |
| `memory_health()` | Schema, source/index төлөв, pending operation, conflict, integrity тайлан |

CLI (си-эл-ай): `mem init`, `mem serve`, `mem reindex`, `mem verify`, `mem recover`, `mem backup`, `mem restore`. Бүх командад `--root` тодорхой өгнө. Backup/restore нь MCP-ийн үндсэн долоон хэрэгсэлд нэмэгдэхгүй.

MCP stdio stdout-д зөвхөн protocol; log stderr-д. Error code: `VALIDATION_ERROR`, `NOT_FOUND`, `STORE_BUSY`, `CONFLICT`, `IDEMPOTENCY_CONFLICT`, `SOURCE_ALREADY_PROCESSED`, `RECOVERY_CONFLICT`, `INDEX_INVALID`, `ARCHIVE_PENDING`. Backend-ийн default хязгаар: document 1 MiB, Inbox text 10 MiB, patch 20 documents/100 events/50 MiB нийт материалжсан bytes. Том эхэд chunking тусдаа дараагийн ажил; эхний хувилбар тодорхой алдаа өгч эхийг хэвээр хадгална.

## 9. Өгөгдлийн хамгаалалт, Git, backup

Замыг canonical root дотор шалгана; `..`, absolute path, escaping symlink, archive entry traversal, destination collision-ийг хориглоно. Inbox/raw text нь өгөгдөл; доторх “заавар”-ыг SKILL.md эсвэл системийн заавар гэж үзэхгүй. YAML safe parsing, bound SQL parameters хэрэглэнэ. Backend arbitrary shell/network tool өгөхгүй.

L3/L2/L1 руу API key/password зэрэг илт credential pattern оруулахыг validation-оор татгалзана; энэ нь нууц мэдээллийг төгс танина гэсэн баталгаа биш. Raw L0 эх 1:1 хэвээр тул нууц агуулж болохыг баримтжуулна; raw/log/DB-г автоматаар Git рүү нийтлэхгүй. Алдааны log-д бүтэн memory текст, credential утга хэвлэхгүй. Хувийн эрүүл мэнд зэрэг мэдээлэл хэрэглэгч өөрөө өгсөн, санах шаардлагатай үед л орно.

GitHub/Obsidian Git plugin (гит плагин)-ийг хүсвэл текст болон code-ийн хувилбарын хяналтад ашиглана. Backend Git commit/push хийхгүй. Санал болгосон default ignore: `L0/Inbox/**`, архивын ZIP-үүд, `L1/*.sqlite3*`, `Backend/.state/**`, `.venv/**`. Archive README болон код/баримт бичиг track хийнэ. Raw архивыг Git-д оруулах өөр сонголт гарвал тусад нь шийднэ. **Obsidian Git бол SQLite backup-ийн орлуулга биш.** `merge=union` L1-д хэрэглэхгүй.

`mem backup` нь writer lock дотор recovery дууссан тогтвортой төлөвөөс SQLite backup API-гаар DB snapshot авч, L3/L2, Inbox, бүх archive, source revision, schema version болон SHA-256 manifest-тай нэг backup үүсгэнэ. WAL/shm файлыг шууд copy хийхгүй. Cache-ийг оруулахгүй. Гаднын editor/importer lock-д орохгүй тул database-ээс бусад canonical файлын inventory ба hashes-ийг snapshot-ын эхэнд/төгсгөлд шалгаж өөрчлөгдвөл бүтэлгүйтүүлнэ; backup үед external edit/import хийхгүй гэсэн ижил хязгаар үйлчилнэ.

`mem restore` зөвхөн шинэ/хоосон destination-д сэргээнэ. Hash ба schema-ийг шалгаж, SQLite integrity/foreign key checks хийж, canonical эхээс index-ийг rebuild хийнэ. Одоогийн store-ийг дарж restore хийхгүй. Backup-ийг repo-гийн гадна хадгалж, бодит off-device copy-г хэрэглэгчийн backup систем хариуцна; энэ хувилбар өөрөө cloud upload хийхгүй.

## 10. Хүлээн авах шалгуур

1. Хэрэгтэй мэдээлэл зөв L3/L2/L1-д ордог сонгомол жишээ: бодит тестийн үр дүн хадгалагдана, энгийн асуулт/хэрэгжээгүй санал L1-д орохгүй.
2. MCP-ээр L3 шинэчлэгдэхэд өмнөх bytes сэргээгдэх; L1 correction эх event-ийг устгахгүй; мэдэгдэхгүй хугацааг зохиохгүй. Session-only evidence-ийн excerpt ба hash нь дараагийн session-д уншигдах.
3. Document folder/name өөрчлөгдөхөд ID resolve ажиллах; duplicate ID болон overwrite conflict ил тод алдаа өгөх.
4. Ижил patch retry event/archive давхардуулахгүй; key дахин өөр утгаар ашиглавал татгалзах.
5. PREPARED, эхний файл replacement, APPLIED, ZIP байршуулсны дараах цэг бүрт process таслаад restart хийхэд нэг л логик үр дүн гарах; зөрчил байвал өгөгдөл хамгаалж блоклох.
6. Архивын эх bytes нь оролттой 1:1 таарах, `.md` болон ZIP нэр нь сэдэвтэйгээ тохирох. Rename/retry үед нэрийн mapping хадгалагдах. Хадгалалт эсвэл ZIP verification бүтэлгүйтвэл эх алдагдахгүй. `no_memory` зам бодитой ажиллах.
7. Search cache-ийг устгаад L3/L2/L1-аас сэргээхэд ID, текст, source refs ижил байх. Монгол `Ө/Ү/Ё`, English, punctuation болон manual edit-ийг шалгах.
8. Бодит stdio MCP session-ээр list/read/write/search/correction урсгал ажиллах; tool discovery шалгагдах; idle үед Inbox file нэмэхэд memory өөрөө үүсэхгүй.
9. Backup-ийг тусдаа шинэ root-д restore хийж бүх canonical hash/event count/correction холбоос таарах, search ажиллах.
10. Сонгосон бодит OS/client дээр `mem serve` холболт шалгагдсан байх. Одоогийн cloud Linux-ийн үр дүнг Windows/macOS дээр шалгасан мэт тайлагнахгүй.

## 11. Төлөвлөгөөг сайжруулах дүрэм

Энэ хувилбарыг v0.2 гэж хадгална. Шат бүрийн бодит туршилтаас `ажиглалт → шийдвэр → шалтгаан → нөлөөлөх тест/ажил` гэсэн богино change log нэмнэ. Module нэр, task-ийн хэмжээ, tool-ийн жижиг параметрийг нотолгоогоор сайжруулж болно. Хэрэглэгчийн өгсөн үндсэн чиглэл өөрчлөгдөх бол ил тод шинэ хувилбар болгон танилцуулна.

Checkpoint A: storage/write/recovery туршилтын дараа найдвартай байдлыг дахин үнэлнэ. Checkpoint B: бодит MCP client ашигласны дараа хэрэгслийн тоо, agent-ийн SKILL.md зааврыг засна. Checkpoint C: acceptance ба restore туршилтын дараа v0.1 хэрэглээнд хангалттай эсэхийг үнэлнэ. Хуучин “20 өдөр” гэсэн тоог commitment болгохгүй; эхний ажил ба recovery туршилтын дараа л effort estimate шинэчилнэ.

Шийдээгүй боловч draft төлөвлөлтийг гацаахгүй зүйл: эхний бодит OS, MCP client, ойролцоох сангийн хэмжээ, off-device backup-ийн байршил. Суурь загвар нь local filesystem + client-ээс үл хамаарах stdio. Хэрэгжүүлэлтийн эхэнд эдгээрийг тухайн орчноос шалгаж startup зааварт тусгана.

### Builder review-ийн дараах тодруулга

2026-10-30: тусдаа reviewer provenance болон гаднын Markdown edit-ийн хувилбарын хязгаарыг тодруулах шаардлагатай гэж үзсэн. Энэ draft-д session evidence-ийн хамгийн бага excerpt-ийг canonical хадгалах, backend revision preservation-ийг MCP бичилтэд хязгаарлах санал оруулав. Эдгээр нь хэрэглэгчийн өмнөөс батлагдсан шийдвэр биш, шалгаж өөрчилж болох санал.

2026-10-30, хэрэглэгчийн дараагийн тодруулга: архивын өмнө Markdown эхийг агуулгын сэдэвт тохирсон нэртэй болгоно. Энэ нэрийг ZIP дотор болон ZIP-ийн нэрэнд ашиглах, анхны нэрийг manifest-д үлдээх, bytes-ийг хэвээр хадгалах байдлаар тусгав. Нэгдсэн индексийн зориулалтыг жишээгээр тодруулав.

## Git snapshot-ийн шинэчилсэн шийдвэр

Хэрэглэгч L1-ийг Git-ээр хянах боломжийг зөвшөөрсөн. Live `L1/history.sqlite3` болон WAL/shm ignored хэвээр; `mem snapshot` командаар SQLite backup API ашиглан `L1/history.snapshot.sqlite3` үүсгэж Git-д track хийнэ. Backend өөрөө commit/push хийхгүй. Snapshot нь зөвхөн L1-ийн хувилбар; бүрэн store backup-д Markdown/Inbox/ZIP бас орно. Шинэ root-д snapshot-оос L1-ийг explicit restore хийнэ; pending/conflicted operation-той snapshot үүсгэхгүй.
