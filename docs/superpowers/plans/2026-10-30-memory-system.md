# Mem Memory System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Нэг компьютер дээр AI-д хэрэгтэй хувийн нөхцөл, зорилго, бодит түүхийг эх сурвалжтай хадгалж, MCP-ээр ашигладаг санах ойн эхний хувилбар байгуулах.

**Architecture:** L1/L2 Markdown ба L3 SQLite нь canonical эх. Тусдаа SQLite FTS5 индекс нь дахин үүсдэг cache. Нэг writer, durable operation journal, idempotent patch, explicit Inbox completion нь файл/database/archive хоорондын тасалдлыг сэргээнэ.

**Tech Stack:** Python 3.12+, SQLite/FTS5, official Python MCP SDK/stdio, Pydantic 2, PyYAML safe loader, filelock, pytest, uv. Dependency-ийн нийцсэн хувилбарыг хэрэгжүүлэх үед `uv.lock`-д тогтооно.

**Spec:** [Mem design v0.2](../specs/2026-10-30-memory-system-design.md). Executor хоёр баримтыг хамтад нь уншина.

**Төлөв:** 2026-10-30 хэрэглэгч main дээр хэрэгжүүлэхийг зөвшөөрсөн. Доорх нь анхны төлөвлөгөө; бодит үр дүн, өөрчлөлтийг docs/memory-acceptance.md болон implementation update-ээс харна.

## Global Constraints

- L1/L2: Markdown (маркдаун), шууд уншиж/засварлаж болох үндсэн эх.
- L3: SQLite (эс-кью-лайт) үндсэн database (дэйтабэйс); MCP (эм-си-пи)-ээр хайх, унших, бичлэг болон засварын тайлбар нэмэх.
- Нэгдсэн индекс: L1/L2 **болон L3 database**-аас дахин үүсэх cache (кэш).
- Эхний хувилбар: нэг компьютер. Obsidian (обсидиан) хэрэглэх боломжтой, түүнээс систем хамаарахгүй.
- Тусгай UI, embeddings/vector search, cloud sync, олон компьютерийн merge, scheduler, Inbox watcher байхгүй. Tool ашиглах бүрд permission dialog нэмж хийхгүй.
- L3 бол бодит үйл явдлын append-only түүх; correction нь шинэ бичлэг. AI-ийн санал, энгийн асуултыг event болгож хадгалахгүй.
- Backend өөрөө LLM дуудахгүй; agent утгын сонголт, backend бүтэц/хадгалалтын баталгааг хариуцна.
- Бүх утгын өөрчлөлт `memory_apply_patch` application service-ээр явна. Cache rebuild ба explicit restore нь тусдаа maintenance ажиллагаа.
- SQLite: `foreign_keys=ON`, WAL, `synchronous=FULL`, `busy_timeout=5000`. `schema_version: 1`.
- Default: document 1 MiB, Inbox text 10 MiB, source excerpt 64 KiB, patch 20 documents/100 events/50 MiB материалжсан bytes, query 500 тэмдэгт, result limit 1..100/default 20.
- Цаг: backend `recorded_at` UTC; `occurred_at` мэдэгдэхгүй бол null. `user_reported` ба `tool_observed` ялгаатай.
- Git commit/push-ийг ажиллаж буй memory backend хийхгүй. Хөгжүүлэгчийн feature commit нь өөр зүйл; доорх commit алхмууд зөвхөн ирээдүйн implementation-д хамаарна.
- Cloud task аль хэдийн тусгаарлагдсан: одоогийн checkout ашиглана. User тусгайлан хүсээгүй бол Git worktree шинээр үүсгэхгүй.
- Repository одоогоор code-гүй. Энэ баримтын бүх app/module/test path нь **Create**, байгаа implementation мэт үзэхгүй.

## Review Focus

1. **Retry ба process crash:** file/DB/ZIP завсрын бүх цэгт нэг л логик өөрчлөлт гарч, эх алдагдахгүй байх — Task 3/4.
2. **Хүн гаднаас засах, зөөх, давхардсан ID:** хуучин hash-тай patch overwrite хийхгүй, шинэ агуулга хайгдах, боломжгүй revision history амлахгүй байх — Task 2/3/5.
3. **Буруу эсвэл дараа нь засагдсан түүх:** session evidence хадгалагдах, correction хуучин үр дүнг current truth мэт гаргахгүй байх — Task 2/5/8.
4. **Монгол/English ба untrusted input:** Ө/Ү/Ё, punctuation, query injection, path/symlink/ZIP traversal, илт credential pattern — Task 2/4/5/7.
5. **Backup ба зэрэг ажиллах client:** cache/DB-г андуурахгүй, хоёр дахь writer татгалзах, WAL-тай DB-г backup API-аар бүрэн сэргээх — Task 1/3/7.

## Хийх дараалал, бүтцийн зураг

`1 Суурь → 2 Canonical read → 3 Patch/recovery → 4 Inbox/archive → 5 Search → 6 MCP → 7 Backup → 8 Acceptance`

Task 3-ийн дараа Checkpoint A, Task 6-ийн дараа Checkpoint B, Task 8-ийн дараа Checkpoint C. Шат бүрийн нотолгоогоор дараагийн хэсгийг засна. Хамаарал их учраас эхний гүйцэтгэлийг нэг үндсэн implementer дарааллаар хийхийг санал болгоно; execution арга энэ plan-only turn-д сонгогдоогүй.

| Файл/багц | Хариуцлага |
|---|---|
| `Backend/src/mem/models.py`, `errors.py` | Хуваалцах typed contract, тогтвортой error code |
| `store.py`, `locking.py`, `Backend/migrations/001_initial.sql` | Root, SQLite schema, process lock, эхлүүлэх |
| `paths.py`, `documents.py`, `events.py`, `sources.py`, `read.py` | Safe path, canonical Markdown/event/provenance унших |
| `journal.py`, `apply.py`, `recovery.py` | Prepared operation, mutation, retry, recovery |
| `inbox.py`, `archive.py` | Raw эх, explicit processing, verified immutable ZIP |
| `index.py`, `search.py` | Сэргээгдэх index, freshness, literal хайлт |
| `server.py`, `cli.py` | MCP adapters, stdio, CLI entrypoint |
| `health.py`, `backup.py` | Integrity, backup/restore |
| `Backend/tests/` | Unit, process crash, MCP, restore, acceptance тест |
| `Backend/skills/memory/SKILL.md` | Agent хэзээ/юуг/яаж санах заавар |
| `README.md`, `Backend/README.md`, `L0/Archive/README.md` | Ашиглах, эхлүүлэх, recovery/backup тайлбар |

`Store` нь root/db/index path болон lock handle-ийг эзэмшинэ. Consumer нь database connection эсвэл cache path-ийг дур мэдэн тойрч өөрчлөхгүй. Public library function-ууд нь typed model буцаана, MCP adapter л JSON болгоно.

## Task 1: Store, schema, contract, нэг writer

**Files — Create:** `Backend/pyproject.toml`, `Backend/uv.lock`, `Backend/src/mem/__init__.py`, `models.py`, `errors.py`, `store.py`, `locking.py`, `Backend/migrations/001_initial.sql`, `Backend/tests/conftest.py`, `Backend/tests/test_store.py`, `.gitignore`.

**Interfaces**

- `init_store(root: Path) -> Store`; `open_store(root: Path) -> Store`; `Store.close() -> None`. `open_store` шинэ DB чимээгүй үүсгэхгүй.
- `MemoryError(code: str, message: str, details: dict)`; message/details-д memory body эсвэл credential хэвлэхгүй.
- `MemoryPatch(idempotency_key, topics, documents, events, sources, close_inbox)` — unknown field хориглосон Pydantic models. Key: 1..128 тэмдэгт. `topics/documents/events` create нь patch-local `new:<name>` ref авч backend UUID-д map хийнэ.
- `TopicChange(action=create|rename, ref, title, expected_revision)`: create-д түр ref, rename-д canonical UUID/ref ба current revision заавал. Rename ID-г өөрчлөхгүй.
- `DocumentChange`: `create|replace|move`, `ref`, `layer`, `topic_refs`, `title`, `path`, `markdown`, `expected_sha256`, `source_refs`. `markdown` нь frontmatter-гүй body; create/replace үед backend stable ID, metadata, UTC updated_at бүхий frontmatter үүсгэнэ. Replace нь бүтэн logical content, layer-ийг хэвээр өгнө; source refs заавал. Move нь ref/path/hash л шаардаж bytes-ийг хэвээр зөөнө. Create-д expected hash байхгүй; replace/move-д заавал байна. Нэг patch нэг document-ийг нэг л удаа өөрчилнө; destination давхцахгүй.
- `EventDraft`: `ref`, `topic_refs`, `kind=action|result|test|decision|change|correction`, `summary`, `details`, nullable `occurred_at`, `evidence_kind`, `source_refs`, nullable `corrects_event_id`.
- `SourceDraft`: `ref`, `kind=inbox|session|artifact`, `origin_ref`, optional `relative_path/expected_sha256`, `excerpt`. Session/artifact-д excerpt заавал; Inbox raw snapshot-ийг backend уншиж батална. Гаднах artifact path/URL-г өөрөө дагаж fetch хийхгүй.
- `InboxCompletion(relative_path, expected_sha256, archive_filename, outcome=recorded|no_memory, reason)`; `recorded` нь source-той холбоотой өөрчлөлттэй, `no_memory` нь reason-той. `archive_filename` нь агуулгын сэдэвт тохирсон basename; `.md` эхэд `.md` өргөтгөлтэй. Backend өөрөө LLM дуудаж нэр өгөхгүй.
- `ApplyResult(operation_id, state=PREPARED|APPLIED|DONE, id_map, document_etags, archive_status, index_dirty)`.
- `SearchRequest(query, layers, topic_ids, limit=20)`; `SearchPage(items, index_revision)`; `ReadResult(ref, kind, data, source_etag)`; `HealthReport(ready, issues, source_revision, index_revision, pending_operations)`.

- [ ] **1. RED:** `test_store.py`-д FTS5 capability, schema version, FK, repeated init өгөгдөл хадгалах, unsupported schema татгалзах, хоёр process нэг root барихад `STORE_BUSY`, model limits-ийн boundary тест бичнэ.

  Гол assertions: `schema_version == 1`, `foreign_keys == 1`, second writer `code == "STORE_BUSY"`; нэг retry init дараа өмнөх topic count өөрчлөгдөхгүй. `limit=100` зөв, `limit=101` буруу; 64 KiB excerpt зөв, нэг byte илүү буруу.
- [ ] **2. RED run:** `cd /workspace/Mem/Backend && uv run pytest tests/test_store.py -q`. Эхэндээ шаардлагатай interface байхгүй учраас fail болохыг шалгана.
- [ ] **3. Implement:** pyproject package entrypoint `mem = mem.cli:main`, migration schema, бүх shared model, lock болон init/open-г хийнэ. FTS5 дэмжихгүй бол ямар runtime хэрэгтэйг тодорхой алдаагаар өгнө. SQLite migration-ийг transaction-д, destructive implicit upgrade-гүй хийнэ. Dependency install/lock энэ үед л хийгдэнэ.
- [ ] **4. GREEN:** дээрх тестүүд pass; `uv run python -c 'import sqlite3; c=sqlite3.connect(":memory:"); c.execute("CREATE VIRTUAL TABLE f USING fts5(text)")'` exit 0. Runtime/OS-ийг тэмдэглэнэ.
- [ ] **5. Commit:** зөвхөн Task 1-ийн code/config/test файлууд; `feat: initialize memory store and shared contracts`. Runtime DB, raw memory, cache track хийхгүй.

## Task 2: Canonical read, stable ID, provenance, history

**Files — Create:** `Backend/src/mem/paths.py`, `documents.py`, `events.py`, `sources.py`, `read.py`, `Backend/tests/test_documents.py`, `test_events.py`, `test_sources.py`, `test_paths.py`, `Backend/tests/fixtures/`.

**Interfaces**

- Consumes: Task 1 `Store`, shared models.
- `load_documents(store: Store) -> list[DocumentRecord]`; `DocumentRecord(document_id, layer, topic_ids, title, updated_at, path, markdown, sha256)`.
- `resolve_safe_path(root: Path, relative_path: str, allowed_area: str) -> Path`.
- `read_memory(store: Store, ref: str) -> ReadResult`; ref нь `mem://topic|document|event|source/<uuid>`.
- `capture_source(draft: SourceDraft, raw_bytes: bytes | None) -> SourceRecord`; `SourceRecord(source_id, kind, origin_ref, excerpt, sha256)`.
- `read_event_chain(store: Store, event_id: UUID) -> EventChain`; `EventChain(original, corrections, effective_event)`.
- `DocumentRecord`, `SourceRecord`, `EventChain`-ийг `models.py`-д нэмнэ. Low-level DB insert нь дараагийн Task 3-ийн unit-of-work дотроос л дуудагдах internal API байна.

- [ ] **1. RED:** fixture-ээр L1 `devices`, L2 project context, L3 actual test result, session excerpt, correction chain үүсгэнэ. `test_rename_keeps_document_ref`, `test_duplicate_document_id_fails`, `test_unknown_topic_fails`, `test_read_event_includes_corrections`, `test_session_excerpt_survives_reopen`, `test_escape_paths_rejected` бичнэ.

  ```python
  chain = read_event_chain(store, original_id)
  assert chain.original.summary == "Тест PASS"
  assert chain.effective_event.summary == "Тест FAIL — өмнөх дүн буруу"
  assert len(chain.corrections) == 1
  ```

  `occurred_at is None` хэвээр; captured excerpt hash нь `sha256(excerpt.encode("utf-8"))`; basename өөрчлөгдсөн ч `document_id` ижил. Absolute/`../`/escaping symlink, unsafe YAML, invalid UTF-8, duplicate field/ID, 1 MiB+1 byte document → тодорхой error.
- [ ] **2. RED run:** `uv run pytest tests/test_documents.py tests/test_events.py tests/test_sources.py tests/test_paths.py -q`.
- [ ] **3. Implement:** YAML safe loader, schema validation, canonical ID resolver, UUID generation ба source capture, original/correction chain уншилт. Correction нэг node-д нэг successor-той; cycle/branch/reference алдааг хориглоно. Direct Markdown өөрчлөлтийг харахдаа event зохиохгүй.
- [ ] **4. GREEN:** бүх дээрх тест pass. Fixture-ийн L3 record content/hash reopen дараа өөрчлөгдөхгүй. Credential-pattern validation-ийн false positive-ийг яг жишээгээр шалгаж, бүх хувийн өгөгдлийг ерөнхийд нь хориглохгүй.
- [ ] **5. Commit:** `feat: read canonical memory with stable identities and provenance`.

## Task 3: Idempotent patch, journal, process recovery

**Files — Create:** `Backend/src/mem/journal.py`, `apply.py`, `recovery.py`, `Backend/tests/test_apply.py`, `test_recovery.py`, `helpers.py`. **Modify:** `models.py`, `store.py`, `documents.py`, `events.py`, `sources.py`.

**Interfaces**

- Consumes: Tasks 1/2 models, read/validation/path functions.
- `apply_patch(store: Store, patch: MemoryPatch) -> ApplyResult`.
- `recover_pending(store: Store) -> RecoveryReport`; `RecoveryReport(recovered_operation_ids, conflicts)`.
- `prepare_operation(store: Store, patch: MemoryPatch) -> PreparedOperation`; `PreparedOperation` нь materialized IDs, expected/desired file bytes, captured sources, pending events, request fingerprint агуулна.
- Private failpoints: `after_prepare`, `after_document_replace`, `after_apply_commit`. Тестийн subprocess hook; public MCP параметр болгохгүй.

- [ ] **1. RED:** `test_apply_is_idempotent`, `test_same_key_different_body_conflicts`, `test_changed_etag_does_not_overwrite`, `test_validation_has_no_partial_writes`, `test_old_document_bytes_preserved`, `test_unknown_time_not_invented`, `test_new_refs_resolve_once`.

  ```python
  first = apply_patch(store, patch)
  again = apply_patch(store, patch)
  assert first.operation_id == again.operation_id
  assert first.id_map == again.id_map
  assert event_count(store) == 1
  assert stored_revision_bytes(store, doc_id) == original_bytes
  ```

  `helpers.py`-д deterministic factory, event count/revision read, subprocess controller байна; production behavior-ийг mock-оор орлуулахгүй. Validation failure үед source tree hashes ба event count огт өөрчлөгдөхгүйг шалгана.
- [ ] **2. RED run:** `uv run pytest tests/test_apply.py tests/test_recovery.py -q`. Recovery тест child process-ийг failpoint бүрт kill хийж дараа нь шинэ process нээнэ; зөвхөн exception throw хийхээр орлуулахгүй.
- [ ] **3. Implement:** spec §6-ийн PREPARED → файлууд → APPLIED → DONE. Fingerprint нь normalized request бөгөөд generated ID/timestamp ороогүй байна. Journal before/after bytes болон raw Inbox snapshot-ийг source DB-д durable хадгална. Цэвэр reopen үед pending recovery-г хийгээд read/write нээнэ; conflict үед health л ажиллаж болно. Source revision нь APPLIED commit-тэй хамт өснө.
- [ ] **4. GREEN:** 3 failpoint бүрт хоёр дахь retry/reopen хийсний дараа яг нэг event, зөв documents, тогтвортой ID mapping. Before/after-аас өөр external bytes байвал `RECOVERY_CONFLICT`, bytes хэвээр. Move target exists, swap-like conflicting paths, stale correction target → overwrite-гүй татгалзах.
- [ ] **5. Checkpoint A ба commit:** journal/recovery үр дүнг design change log-д нэмээд `feat: apply memory patches with restart recovery`. Process-crash тестийг power-loss баталгаа гэж нэрлэхгүй. Failpoint аль нэг нь үндсэн өгөгдөл алдаж байвал дараагийн шат руу орохгүй.

## Task 4: Explicit Inbox processing, immutable ZIP archive

**Files — Create:** `Backend/src/mem/inbox.py`, `archive.py`, `Backend/tests/test_inbox.py`, `test_archive.py`, `L0/Archive/README.md`. **Modify:** `apply.py`, `recovery.py`, `models.py`.

**Interfaces**

- `list_inbox(store: Store, cursor: str | None, limit: int = 20) -> InboxPage`; `InboxPage(items, next_cursor)`.
- `read_inbox(store: Store, relative_path: str, expected_sha256: str) -> InboxItem`; `InboxItem(relative_path, size_bytes, sha256, raw_bytes)`.
- `complete_archives(store: Store, operation_id: UUID) -> ArchiveResult`; `ArchiveResult(status, archive_refs, retained_changed_sources)`.
- Consumes: Task 3 operation snapshot, source mapping, APPLIED state. MCP adapter raw bytes-ийг validated UTF-8 text болгож буцаана; invalid input-ийг чимээгүй decode-ignore хийхгүй.

- [ ] **1. RED:** exact bytes ба SHA-256, `no_memory`, partial input use, duplicate source hash, input өөрчлөгдөх, archive write/verify error, final ZIP exists retry, final ZIP mismatch, 10 MiB+1 input, unsafe ZIP member name-ийг тестлэнэ. `test_archive_uses_topic_filename`, `test_rename_preserves_source_bytes`, `test_retry_keeps_archive_filename`, `test_archive_filename_collision_rejected` нэмнэ. `chat-001.md` эх `Mem-MCP-холболтын-шийдвэр.md` нэрээр ZIP-д орж, ZIP нь `Mem-MCP-холболтын-шийдвэр.zip`, manifest-ийн original filename нь `chat-001.md` байхыг шалгана.

  ```python
  result = apply_patch(store, complete_inbox_patch)
  assert result.state == "DONE"
  assert read_archived_original(store, source_ref) == original_bytes
  assert not original_inbox_path.exists()
  assert event_count(store) == expected_meaningful_event_count
  ```

  `no_memory` дээр `expected_meaningful_event_count == 0`; хадгалалт/ZIP verification fail үед Inbox эсвэл canonical raw snapshot заавал үлдэнэ. Input солигдсон бол шинэ bytes Inbox-д хэвээр, анхны bytes ZIP-д байна.
- [ ] **2. RED run:** `uv run pytest tests/test_inbox.py tests/test_archive.py tests/test_recovery.py -q`.
- [ ] **3. Implement:** source hash-ийг patch validation дээр батална; `close_inbox` нь completed source бүрт explicit. PREPARED journal-д original name/path → archive filename mapping хадгална. Архивын өмнөх staging-д raw snapshot-ийг сэдэвтэй `.md` нэртэй болгоно; агуулга хувиргахгүй. ZIP ба доторх эх ижил name stem-тэй, manifest хоёр нэртэй байна. Inbox original нь ZIP verification дуустал хэвээр үлдэнэ. Шинэ ZIP-д raw bytes + manifest бичиж CRC/SHA шалгаад final болгоно; final-ийг overwrite хийхгүй. Archive pending нь APPLIED patch-ийг rollback/reapply хийхгүй. ZIP final болсон ба Inbox unlink хийхийн хооронд crash failpoint нэмнэ.
- [ ] **4. GREEN:** ZIP final дараах kill/reopen үед нэг ZIP, нэг set events, эх алдагдахгүй. `SOURCE_ALREADY_PROCESSED` нь өмнөх archive ref өгч duplicate raw input-ийг хэвээр үлдээнэ. `recorded` боловч эхтэй холбоотой өөрчлөлтгүй completion татгалзагдана.
- [ ] **5. Commit:** `feat: process selected inbox items and verify immutable archives`.

## Task 5: Нэгдсэн сэргээгдэх хайлт

**Files — Create:** `Backend/src/mem/index.py`, `search.py`, `Backend/tests/test_index.py`, `test_search.py`. **Modify:** `models.py`, `read.py`, `apply.py`.

**Interfaces**

- `rebuild_index(store: Store) -> IndexReport`; `IndexReport(documents, events, source_revision, invalid_sources)`.
- `ensure_index_current(store: Store) -> IndexReport`; request-driven source scan, background loop биш.
- `search_memory(store: Store, request: SearchRequest) -> SearchPage`.
- `SearchHit(ref, layer, topic_ids, title, snippet, source_etag, score, record_status, latest_correction_ref, effective_summary)`-ийг `models.py`-д нэмнэ.

- [ ] **1. RED:** `test_rebuild_from_markdown_and_l3`, `test_external_edit_visible_next_search`, `test_cyrillic_and_english_literal_search`, `test_corrected_hit_is_not_presented_as_current`, `test_query_syntax_is_literal`, `test_invalid_source_blocks_complete_results`.

  Cache-гүй rebuild-ийн өмнө/дараа result **ID set ба content** ижилг шалгана; cache timestamp-ийг адил байхыг шаардахгүй. `Өгөгдөл`, `Үр дүн`, `Ёс`, `SQLite smoke` жишээг case variation-тай хайна; Ө/О, Ү/У-г дур мэдэн ижил болгохгүй. Хуучин `PASS` query нь corrected label ба одоогийн `FAIL` summary-тай буцна. Correction-ийн шинэ үгээр мөн олдоно.
- [ ] **2. RED run:** `uv run pytest tests/test_index.py tests/test_search.py -q`.
- [ ] **3. Implement:** temp index үүсгэж шалгаад swap хийх, SHA-256 inventory/source revision freshness, FTS5 unicode61, parameterized literal tokens, BM25 + ref tie-break. L0 raw болон technical revisions default search-д орохгүй. Source file malformed байхад хуучин cache-аас бүрэн мэт үр дүн буцаахгүй.
- [ ] **4. GREEN:** cache файлыг устгасан ч source DB/documents byte hash өөрчлөгдөхгүй; rebuild ажиллана. Query хоосон, 501 тэмдэгт, limit 0/101 дээр validation. Manual rename, deleted document, duplicate ID, stale read ref бүгд тодорхой төлөвтэй.
- [ ] **5. Commit:** `feat: search canonical memory through a rebuildable index`.

## Task 6: Долоон MCP tool ба agent-ийн хэрэглээний заавар

**Files — Create:** `Backend/src/mem/server.py`, `cli.py`, `health.py` (basic report; Task 7-д өргөжүүлнэ), `Backend/tests/test_mcp.py`, `test_agent_policy.py`, `Backend/skills/memory/SKILL.md`, `Backend/README.md`. **Modify:** `models.py`.

**Interfaces**

- `create_server(root: Path) -> FastMCP`; `main() -> int`; `get_health(store: Store, deep: bool = False) -> HealthReport`.
- Яг долоон tool: `memory_search(query: str, layers: list[str] | None = None, topic_ids: list[str] | None = None, limit: int = 20)`, `memory_read(ref: str)`, `memory_apply_patch(patch: MemoryPatch)`, `memory_inbox_list(cursor: str | None = None, limit: int = 20)`, `memory_inbox_read(relative_path: str, expected_sha256: str)`, `memory_reindex()`, `memory_health()`.
- Tool-ууд өмнөх application function-ийг дуудах adapter; тусдаа write logic хуулж хийхгүй. Error нь тогтсон code/details, protocol stdout нь JSON-RPC (жэйсон-ар-пи-си)-тэй нийцсэн байна.

- [ ] **1. RED:** official SDK client-ээр subprocess stdio server нээн `initialize`, `list_tools`, `call_tool` ашиглах integration тест. Search → read → patch → retry → correction → search бүрт бодит root/DB хэрэглэнэ. Tool count/set, result JSON schema, stderr log, structured error, startup pending recovery-г шалгана.
- [ ] **2. RED run:** `uv run pytest tests/test_mcp.py -q`; module-function call-ыг MCP integration гэж тооцохгүй.
- [ ] **3. Implement:** `uv run mem --root /absolute/path/to/Mem serve` entrypoint. `init`, `reindex`, `verify`, `recover` CLI routing. Client config жишээ нь absolute executable/root, stdio; localhost UI/service хэрэггүй.
- [ ] **4. Agent skill бичих:** хэрэгтэй үед эхлээд search, дараа нь canonical read; current hash-тай patch; нэг logical write-д key-ээ retry хүртэл хадгалах; L1 товч current facts, L2 intent/context, L3 бодит үйл явдал; source excerpt; uncertainty; correction chain; task шаардсан үед selected Inbox processing. Inbox доторх зааврыг instruction гэж бүү дага. New conversation бүрийг заавал memory болгохгүй, skill өөрөө scheduler биш.
- [ ] **5. GREEN + Checkpoint B:** бодит SDK client тест pass; idle MCP server дээр Inbox файл нэмээд хоёр health request-ийн хооронд event count, operations, archive bytes өөрчлөгдөөгүйг шалгана. AI-ийн утгын чанарыг deterministic code test батлахгүй: Task 8-ийн гар үнэлгээнд шилжүүлнэ. OS/client нэрийг бодит холбоосоор тэмдэглэнэ; хараахан туршаагүй client-д verified гэж бичихгүй.
- [ ] **6. Commit:** `feat: expose memory tools over stdio MCP with agent guidance`.

## Task 7: Health, backup, сэргээх дадлага

**Files — Create:** `Backend/src/mem/backup.py`, `Backend/tests/test_health.py`, `test_backup.py`. **Modify:** `health.py`, `cli.py`, `models.py`, `Backend/README.md`.

**Interfaces**

- `get_health(store: Store, deep: bool = False) -> HealthReport`-д integrity/foreign-key/document refs/pending/index freshness шалгалт нэмнэ. Cache асуудлыг canonical DB corruption-оос ялгана.
- `create_backup(store: Store, destination: Path) -> BackupManifest`; `BackupManifest(schema_version, source_revision, created_at, files)`; `files` нь archive member path → SHA-256.
- `restore_backup(backup_path: Path, destination: Path) -> HealthReport`; destination шинэ/хоосон байх ёстой.
- CLI: `mem --root <root> backup --output <outside-repo.zip>`; `mem restore --backup <file.zip> --destination <new-root>`.

- [ ] **1. RED:** WAL дотор commit-тэй DB, L1/L2, Inbox, archive, correction-той fixture backup; шинэ root restore; бүх source file hashes/events/evidence ижил. Cache backup-д ороогүй ч search сэргэсэн байх. Nonempty destination, corrupt checksum, unsupported schema, escaping ZIP entries, pending conflict, external edit during copy → restore/backup fail, өмнөх store хэвээр.
- [ ] **2. RED run:** `uv run pytest tests/test_health.py tests/test_backup.py -q`.
- [ ] **3. Implement:** writer lock, pending recovery, SQLite `Connection.backup`, manifest, snapshot эхлэл/төгсгөлийн database-ээс бусад canonical файлын inventory/hashes. Inbox import дундаа орвол snapshot-ийг дахин авах шаардлагатай гэж буцаана. Temp output-ийг verify хийсний дараа final backup үүсгэнэ. Restore staging нь destination-ийн parent дотор байна; бүх integrity/refs шалгалт pass бол final destination болгоно. Unsupported schema-г migration-гүйгээр чимээгүй өөрчлөхгүй.
- [ ] **4. GREEN:** restored root-ийг шинэ process-оор serve хийж search/read correction chain ажиллаж байгааг шалгана. Backup хийгээгүй store-ийг Git-ээс бүрэн сэргээнэ гэсэн тайлбар байвал арилгана.
- [ ] **5. Commit:** `feat: verify back up and restore canonical memory`.

## Task 8: Нэгдсэн acceptance, ажиллагааны заавар, beta дүгнэлт

**Files — Create:** `Backend/tests/test_acceptance.py`, `Backend/tests/fixtures/memory_scenarios.json`, `docs/memory-acceptance.md`, `README.md`. **Modify:** `Backend/README.md`, `Backend/skills/memory/SKILL.md`, хоёр superpowers баримтын change log.

**Interfaces**

- Consumes: өмнөх бүх public API ба бодит MCP transport. Шинэ runtime API нэмэхгүй.
- Scenario fixture: `input`, `expected_layer_or_skip`, `why`, `evidence_kind`, `expected_fact_status`. Энэ нь agent-ийн judgment evaluation болохоос backend өөрөө утга ангилна гэсэн шинэ шаардлага биш.

- [ ] **1. RED/acceptance fixture:** дор хаяж 8 сценарий: device-ийн хэлсэн бодит мэдээлэл→L1; project-ийн хүссэн үр дүн→L2; ажигласан test FAIL→L3; ердийн асуулт→skip; хэрэгжээгүй AI санал→skip; тодорхойгүй event time→null; буруу test result→correction; чухал зүйлгүй Inbox→no_memory/archive. Session excerpt эхтэйгээ нийцсэн эсэхийг хүн/agent review-ээр үнэлнэ.
- [ ] **2. Integration test бичих:** temporary root init → selected Inbox read → patch → archive → хайлт → canonical read → current fact update → correction → cache delete/rebuild → backup → шинэ root restore. Өмнөх ID, эх hash, event count, correction chain, source excerpt-ийг төгсгөлд батална.
- [ ] **3. Run:** `cd /workspace/Mem/Backend && uv sync --frozen && uv run pytest -q`. Тестийн count, failures/skips, OS/Python/SQLite/SDK versions-ийг үр дүнтэй хамт хадгална. Zero-test run pass гэж тооцохгүй.
- [ ] **4. Бодит client smoke:** хэрэглэгчийн ашиглах client дээр tool discovery болон нэг read/write/retry урсгал, archive-pending error, server restart recovery-г туршина. CI SDK smoke-ийн үр дүнгээс desktop client ажиллана гэж дүгнэхгүй.
- [ ] **5. Startup/recovery баримтжуулах:** root байрлал, `uv sync --frozen`, `mem init`, `mem serve`, `mem verify`, `mem recover`, backup/restore, log байрлал, external editor overlap-ийн хязгаар, no-watcher дүрэм. Cloud орчин ашиглавал дараагийн onboarding-д install/start instructions-ийг бодитоор туршсаны дараа хадгална; энэ plan-only үед environment configuration өөрчлөхгүй.
- [ ] **6. Checkpoint C ба commit:** spec-ийн 10 acceptance criterion тус бүрийн нотолгоо/үлдсэн хязгаарыг бичиж, v0.1 ашиглаж эхлэх эсэхийг шийднэ. `test: verify memory workflow and document recovery`. Баталгаагүй зүйлд “ready” шошго тавихгүй.

## Төлөвлөгөөний өөрчлөлт, хэмжилт, handoff

Энэ plan нь хөшүүн гэрээ биш. Task 3-ийн дараа journal-ын нарийвчлал, Task 6-ийн дараа MCP ergonomics, Task 8-ийн дараа acceptance coverage-ийг дахин засна. Шинэ хувилбар бүрт шалтгаан ба нотолгоо бичнэ. Хэрэглэгчийн санах ойн зорилгоос хазайж UI, autonomous watcher, cloud sync нэмэхийг “сайжруулалт” гэж далд оруулахгүй.

Хугацааг “20 өдөр” гэж урьдчилан батлахгүй. Task 1 ба Task 3-ийн үр дүн дээр тулгуурлан үлдсэн effort-ийг range-аар үнэлнэ. Эхлээд найдвартай бичилт/сэргээх, дараа нь хайлт/MCP, эцэст нь хэрэглээний чанар/backup; semantic search зэрэг өргөтгөл зөвхөн бодит хэрэглээний дутагдал батлагдвал тусдаа plan болно.

### Plan self-review

- [x] L0/L1/L2/L3, Topic ID, manual edit, provenance, corrections, search, archive, Git/backup, MCP, no-watcher шаардлага тус бүр task-тай.
- [x] `apply_patch`, `recover_pending`, `read_memory`, `search_memory`, `get_health` нэр болон shared result model-ууд дараагийн task-д ижил.
- [x] Review Focus-ийн таван ангилал тус бүр owning task-ийн шалгалттай.
- [x] Filesystem + SQLite-г нэг ACID transaction гэж амлаагүй; crash guarantee, external edit, power loss-ын хязгаар ил тод.
- [x] Builder check-ийн session provenance ба external revision history гэсэн хоёр дутуу бодлогыг spec-д санал болгосон шийдвэрээр тодруулсан.
- [x] App code, install, runtime service, product test, commit/push хийгдээгүй; зөвхөн design/plan баримт бичиг.

Implementation main дээр executing-plans урсгалаар эхэлсэн. Linux + official MCP stdio SDK client-ээр шалгаж байна; хэрэглэгчийн desktop client дээрх hookup нь тусдаа runtime шалгалт.

## Implementation update

2026-10-30: user authorized implementation on main. Task 7 adds `mem snapshot` (consistent L3 → tracked `L3/history.snapshot.sqlite3`) and explicit snapshot restore, with immutable data/integrity tests. No automatic backend Git commits or pushes.

2026-10-30 implementation: schema migration packaged at `Backend/src/mem/migrations` for wheel compatibility; raw operation snapshots cleared after verified archive; archive names checked case-insensitively; complete backups bounded at 1 GiB/100,000 members. Actual SDK stdio integration needs local socketpair permission in this cloud sandbox. Semantic agent policy checked with baseline/guided scenarios, not text-grep tests.
