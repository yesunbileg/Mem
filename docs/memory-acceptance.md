# Mem v0.1 шалгалтын нотолгоо

2026-10-30, Linux cloud, Python 3.12.14. Энэ файл нь бодит командын үр дүнгээр шинэчлэгдэнэ; desktop client болон Windows/macOS-ийг туршсан гэж үзэхгүй.

| Шаардлага | Нотолгоо |
|---|---|
| Layer/эх сурвалжийн сонгомол хэрэглээ | memory skill-ийн baseline + guided зургаан scenario: Windows хүсэлт L2, хэрэгжээгүй санал skip, бодит test L1, correction, retry, no watcher, untrusted Inbox |
| Өмнөх document хадгалах, мэдэхгүй хугацаа | test_apply.py, test_events.py |
| Stable ID, rename, duplicate/ref/path алдаа | test_documents.py, test_paths.py, test_invariants.py |
| Ижил patch retry давхцахгүй | test_apply.py, actual stdio test_mcp.py |
| Process crash/restart | test_recovery.py-ийн PREPARED/file/APPLIED failpoints; test_archive.py ZIP→unlink failpoint |
| Archive raw bytes, сэдэвтэй нэр, no_memory | test_archive.py; ZIP error retry, input changed, duplicate source, original name manifest |
| Cache rebuild, Монгол/English, corrected hit | test_search.py; Ө/Ү/Ё, AND literal, manual edit, layer/topic filters |
| Бодит stdio MCP session, idle safety | test_mcp.py official SDK client → initialized subprocess → 7 tools/write/retry/search/read/health; idle source revision unchanged |
| Backup/restore, consistent Git snapshot | test_backup.py; WAL-aware backup API, fresh restore, raw archive hashes, corrupt/traversal/nonempty/conflict/source-copy race |
| Нэгдсэн end-to-end | test_acceptance.py; Inbox→L2/L1→archive→correction→cache rebuild→snapshot→backup→fresh restore→read/retry |

App нь memory-ийн ач холбогдол/үнэн эсэхийг дан кодоор тогтоохгүй. Agent skill scenario review нь semantic guidance-ийн жишээ шалгалт; бүх AI model/client дээр чанарыг бүрэн баталсан гэсэн үг биш.

1 GiB backup cap, local filesystem, no concurrent external edits during writes/backup, process-crash durability гэсэн v0.1 хүрээг README-д баримтжуулсан. Off-device backup хэрэглэгчийн системийн үүрэг. Энэ build-д custom UI/cloud sync/watchers ороогүй.

## Одоогийн ажиллуулсан үр дүн

- `Backend/.venv/bin/pytest Backend/tests -q --tb=short`: **68 passed**, 4.71s (local socketpair зөвшөөрсөн runtime).
- Ruff lint: all checks passed; format: 38 files already formatted.
- `uv sync --frozen --offline`: амжилттай.
- `uv build --offline`: sdist + wheel үүссэн; wheel дотор schema migration байгааг шалгасан.
- Бодит `/workspace/Mem`: init → reindex → snapshot → verify амжилттай; source revision 0, documents/events 0, issues байхгүй. Хувийн баримт зохиож seed хийгээгүй.
- Live DB/cache ignored, `L1/history.snapshot.sqlite3` Git-д track хийхэд бэлэн.
- Skill guided scenario review: зургаан scenario зөв; baseline дээр topic-based archive rename бодлого байхгүйгээс хуучин нэрийг хадгалж байсныг шинэ reference зассан.

## Independent review ба эцсийн баталгаажуулалт

Тусдаа read-only reviewer зургаан Important асуудал олсон; Critical/Minor үлдсэн finding байгаагүй. Бүгдийг нэг fix pass-д 10 regression test эхлээд унагаж, дараа нь амжилттай болгож зассан:

1. `.mem-` нэртэй хүчинтэй Markdown/Inbox backup-аас орхигдож байсныг зассан.
2. `L3/./x.md`, `L3//x.md`, file-as-parent collision-ийг PREPARED-ээс өмнө татгалздаг болгосон.
3. `.md`/`.txt` өөр боловч ижил ZIP stem үүсгэх хоёр эхийг урьдчилан барьдаг болгосон.
4. Өмнө хэсэгчлэн ашигласан Inbox эхийг дараа нь архивлахад хуучин evidence ref мөн raw archive-аа resolve хийнэ.
5. Render хийсэн document-ийг canonical parser-аар PREPARED-ээс өмнө шалгана; whitespace-only title санг эвдэхгүй.
6. Backup creator/restore хоёр DB bytes-ийг багтаасан нийт өгөгдөл, member count, manifest-size хязгаарыг ижил мөрдөнө.

Эцсийн команд: `Backend/.venv/bin/pytest Backend/tests -q --tb=short` → **78 passed, 6.98s**. Ruff lint pass; 39 файлын format check pass; sdist/wheel rebuild pass. Бодит root `mem verify` → ready=true, issues=[], source_revision=0. Reviewer-ийн дараа дахин reviewer ажиллуулаагүй; засваруудыг RED→GREEN болон бүтэн suite-ээр баталсан.

### Хийсэн шийдвэр ба хязгаар

- Хэрэглэгчийн хүсэлтээр тусгаарлагдсан cloud checkout-ийн main дээр ажилласан; local commits хадгалсан, push/PR хийгээгүй.
- Git-д L1-ийн consistent snapshot орно; live DB/WAL/cache ignored. Git дангаараа raw түүхийн бүтэн backup биш.
- Cloud skill-ийн helper scripts local executable биш тул task/commit/test ledger-ийг ижил gate-тайгаар гараар хөтөлсөн; бодит command outputs-оор баталгаажуулсан.
- ZIP баталгаажсаны дараа transient raw DB snapshot-ийг цэвэрлэнэ; архивыг алдвал raw эхийг зөвхөн L1 Git snapshot-оос сэргээхгүй, бүтэн backup хэрэгтэй.
- Async stdio тест cloud-ийн local socketpair эрх шаардсан тул supported escalation ашигласан; гаднын network bypass хийгээгүй.
- v0.1 backup нийт data cap 1 GiB, ZIP member cap 100,000, manifest cap 10 MiB. Үүнээс том санг дэмжихэд тусдаа streaming/storage өөрчлөлт шаардлагатай.
- Windows/macOS, хэрэглэгчийн desktop client дээр хараахан шалгаагүй. Reviewer stdio-г давтан ажиллуулаагүй; controller official SDK client-ээр бүтэн suite-д шалгасан.
- Power/disk failure, network drive, зэрэг external edit-ийг бүрэн хамгаалах амлалт байхгүй. Agent-ийн семантик сонголтыг backend баталж чадахгүй.
- Minor finding deferred хийгээгүй.

Environment install/start instructions draft-д хадгалагдсан, install script одоогийн instance дээр амжилттай ажилласан. Draft save нь publish биш; environment settings-д review/save/publish хэрэглэгчийн flow-оор хийгдэнэ.

## Clone дахь хавтасны засвар

2026-10-30: Git хоосон хавтас хадгалдаггүй тул `L3`, `L2`, `L0/Inbox`-д tracked `.gitkeep` нэмэв. Inbox marker-ийг raw source гэж list/read хийхгүй; бодит Inbox файлууд ignored хэвээр. Хоёр regression test RED→GREEN. Бүтэн suite: **80 passed, 4.19s**; Ruff lint pass.
