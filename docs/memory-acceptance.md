# Mem v0.1 шалгалтын нотолгоо

2026-10-30, Linux cloud, Python 3.12.14. Энэ файл нь бодит командын үр дүнгээр шинэчлэгдэнэ; desktop client болон Windows/macOS-ийг туршсан гэж үзэхгүй.

| Шаардлага | Нотолгоо |
|---|---|
| Layer/эх сурвалжийн сонгомол хэрэглээ | memory skill-ийн baseline + guided зургаан scenario: Windows хүсэлт L2, хэрэгжээгүй санал skip, бодит test L3, correction, retry, no watcher, untrusted Inbox |
| Өмнөх document хадгалах, мэдэхгүй хугацаа | test_apply.py, test_events.py |
| Stable ID, rename, duplicate/ref/path алдаа | test_documents.py, test_paths.py, test_invariants.py |
| Ижил patch retry давхцахгүй | test_apply.py, actual stdio test_mcp.py |
| Process crash/restart | test_recovery.py-ийн PREPARED/file/APPLIED failpoints; test_archive.py ZIP→unlink failpoint |
| Archive raw bytes, сэдэвтэй нэр, no_memory | test_archive.py; ZIP error retry, input changed, duplicate source, original name manifest |
| Cache rebuild, Монгол/English, corrected hit | test_search.py; Ө/Ү/Ё, AND literal, manual edit, layer/topic filters |
| Бодит stdio MCP session, idle safety | test_mcp.py official SDK client → initialized subprocess → 7 tools/write/retry/search/read/health; idle source revision unchanged |
| Backup/restore, consistent Git snapshot | test_backup.py; WAL-aware backup API, fresh restore, raw archive hashes, corrupt/traversal/nonempty/conflict/source-copy race |
| Нэгдсэн end-to-end | test_acceptance.py; Inbox→L2/L3→archive→correction→cache rebuild→snapshot→backup→fresh restore→read/retry |

App нь memory-ийн ач холбогдол/үнэн эсэхийг дан кодоор тогтоохгүй. Agent skill scenario review нь semantic guidance-ийн жишээ шалгалт; бүх AI model/client дээр чанарыг бүрэн баталсан гэсэн үг биш.

1 GiB backup cap, local filesystem, no concurrent external edits during writes/backup, process-crash durability гэсэн v0.1 хүрээг README-д баримтжуулсан. Off-device backup хэрэглэгчийн системийн үүрэг. Энэ build-д custom UI/cloud sync/watchers ороогүй.

## Одоогийн ажиллуулсан үр дүн

- `Backend/.venv/bin/pytest Backend/tests -q --tb=short`: **68 passed**, 4.71s (local socketpair зөвшөөрсөн runtime).
- Ruff lint: all checks passed; format: 38 files already formatted.
- `uv sync --frozen --offline`: амжилттай.
- `uv build --offline`: sdist + wheel үүссэн; wheel дотор schema migration байгааг шалгасан.
- Бодит `/workspace/Mem`: init → reindex → snapshot → verify амжилттай; source revision 0, documents/events 0, issues байхгүй. Хувийн баримт зохиож seed хийгээгүй.
- Live DB/cache ignored, `L3/history.snapshot.sqlite3` Git-д track хийхэд бэлэн.
- Skill guided scenario review: зургаан scenario зөв; baseline дээр topic-based archive rename бодлого байхгүйгээс хуучин нэрийг хадгалж байсныг шинэ reference зассан.
