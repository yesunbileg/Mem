# Backend API ба ажиллагаа

Python 3.12+, SQLite FTS5, official MCP Python SDK, Pydantic 2, PyYAML, filelock. `uv.lock` dependency-ийг тогтооно. `src/mem/migrations` нь wheel дотор хамт багцлагдана. Store schema version 1; мэдэхгүй шинэ schema-г чимээгүй өөрчлөхгүй.

## Долоон хэрэгсэл

| Нэр | Оролт/үр дүн |
|---|---|
| `memory_search` | query, optional L3/L2/L1 layers, bare topic UUIDs, limit 1..100; snippets, stable refs, correction status |
| `memory_read` | `mem://topic/document/event/source`-оос тухайн төрлийн UUID бүхий ref; canonical content + etag |
| `memory_apply_patch` | structured patch; operation ID, new ref→UUID map, document hashes, state, archive_status |
| `memory_inbox_list` | cursor/limit; root-relative paths, bytes, SHA-256 |
| `memory_inbox_read` | path + expected hash; exact UTF-8 source text |
| `memory_reindex` | canonical эхийг өөрчлөхгүйгээр cache-ийг сэргээнэ |
| `memory_health` | canonical integrity, cache warning, pending operation |

Literal үгийн AND хайлт хэрэглэнэ; semantic search, Монгол үгийн хувилал/латин галигийг автоматаар тэлэхгүй. Ө/О, Ү/У нь өөр үсэг. Raw Inbox/ZIP болон техникийн document revisions default хайлтад орохгүй. Source ref-ээр архивласан эхийг уншиж болно.

## Patch жишээ

Доорх нь **зохиомол жишээ**; өөрийн бодит evidence-ээр солино. Topic, source, document/event тус бүрт unique patch-local `new:` ref өгнө. Backend stable UUID үүсгэнэ.

```json
{
  "idempotency_key": "session-42-turn-3",
  "topics": [{"ref": "new:project", "title": "Example project"}],
  "sources": [{"ref": "new:evidence", "kind": "session", "origin_ref": "session:42/message:3", "excerpt": "User wants Windows support."}],
  "documents": [{"ref": "new:context", "layer": "L2", "topic_refs": ["new:project"], "title": "Example project goals", "path": "L2/example/context.md", "markdown": "Хэрэглэгч Windows дэмжлэг хүссэн.", "source_refs": ["new:evidence"]}]
}
```

Document `markdown` нь body; frontmatter-ийг backend үүсгэнэ. Replace-д `action=replace`, өмнөх canonical ref, одоогийн `expected_sha256`, бүрэн logical content өгнө. Move-д `action=move`, ref, шинэ path, expected hash өгнө; bytes/ID хэвээр. Topic rename-д expected revision өгнө.

L1 event: `kind=action|result|test|decision|change|correction`, summary/details, topic_refs, source_refs, evidence_kind (`user_reported|tool_observed`), optional occurred_at (timezone-тай, мэдэхгүй бол null). Correction-ийн `corrects_event_id` нь chain-ийн latest event ref. Read нь original/corrections/effective_event буцаана. Search-д хуучин үр дүн таарвал corrected label болон шинэ үр дүн хамт харагдана.

Inbox source нь `kind=inbox`, relative_path, expected_sha256-тай. Хэсэгчлэн ашиглахад close_inbox өгөхгүй. Бүрэн боловсруулбал:

```json
{"relative_path":"L0/Inbox/chat-001.md","expected_sha256":"<from inbox read>","archive_filename":"Mem-MCP-холболтын-шийдвэр.md","outcome":"recorded"}
```

`recorded` нь тухайн source-той холбоотой өөрчлөлттэй байна. Санах зүйлгүй эхэд `outcome=no_memory`, `reason` өгч болно. Архивын өмнөх staging хуулбарыг сонгосон сэдэвтэй нэртэй болгож ZIP үүсгэнэ. Inbox эхийг verification дуустал хэвээр хадгална. Final ZIP-ийн bytes өөрчлөгдөхгүй; journal raw snapshot нь ZIP verified/cleanup дууссаны дараа цэвэрлэгдэнэ. Source hash давхардвал дахин event үүсгэхгүй, duplicate input-ийг үлдээнэ.

## Хязгаар ба алдааны дүрэм

Document 1 MiB, Inbox 10 MiB UTF-8, excerpt 64 KiB, patch 20 documents/100 events/50 MiB материалжсан bytes. Хязгаар давбал эхийг таслахгүй, алдаа өгнө. Source excerpt ба memory body-д илт credential pattern хориглоно; энэ нь бүх secret-ийг таних баталгаа биш. L0 эхийг 1:1 хадгалдаг тул raw текст нууц агуулж болно.

`VALIDATION_ERROR`, `NOT_FOUND`, `CONFLICT`, `STORE_BUSY`, `IDEMPOTENCY_CONFLICT`, `SOURCE_ALREADY_PROCESSED`, `RECOVERY_CONFLICT`, `INDEX_INVALID`, `SCHEMA_UNSUPPORTED` нь ялгаатай. CLI алдаанд nonzero exit, MCP tool алдаанд isError өгнө. Үндсэн write APPLIED боловч архив pending бол амжилтгүй шинэ write хийхгүй; яг ижил key/payload-ийг retry хийнэ. Нэг компьютерийн хоёр MCP process зэрэг root нээхэд хоёр дахь нь STORE_BUSY; нэг client-ийн tool calls serialize хийгдэнэ.

`health` cache missing/stale warning-тай ч canonical data healthy бол ready байж болно. PREPARED operation/conflict нь хэвийн read/write-ийг блоклоно. `verify` нь archive checksum ба DB integrity-г гүн шалгана. `recover`-ийг өөрийн writer process-ийг хаасны дараа ажиллуулна.

Git/backup/startup командууд [үндсэн README](../README.md)-д байна. Backend stdout нь serve үед зөвхөн MCP protocol, log stderr. HTTP listener, automatic timer, shell execution, external fetch, Git commit байхгүй.
