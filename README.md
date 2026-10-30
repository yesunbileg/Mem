# Mem — хувийн AI санах ой

Нэг компьютер дээр AI хэрэгтэй үедээ MCP (эм-си-пи)-ээр хайж, уншиж, эх сурвалжтай өөрчлөлт хадгална. Inbox watcher, тусгай UI, backend LLM/API key байхгүй.

| Хэсэг | Үүрэг |
|---|---|
| `L0/Inbox` | Боловсруулаагүй UTF-8 эх, bytes 1:1 |
| `L0/Archive` | Сэдэвтэй нэр бүхий эх + manifest-тай, өөрчлөхгүй ZIP |
| `L1` | Товч одоогийн баримт |
| `L2` | Topic/project-ийн зорилго, нөхцөл, шийдвэр, дараагийн алхам |
| `L3/history.sqlite3` | Бодит үйл явдал, эх сурвалж, correction, ажиллагааны journal |
| `Backend/.state/search.sqlite3` | L1/L2/L3-аас сэргээгдэх нэгдсэн хайлтын cache |

Энгийн асуулт, хэрэгжээгүй AI санал L3-ийн үйл явдал болохгүй. Юуг санахыг agent шийдэж, backend нь формат, эх сурвалж, давхардал, зөрчил, хадгалалтыг хамгаална. L3 correction нь өмнөх мэдээллийг дарж устгахгүй.

## Суулгах, эхлүүлэх

Python 3.12+, [uv](https://docs.astral.sh/uv/) шаардлагатай. Linux дээр туршсан; Windows/macOS дээр тусад нь баталгаажуулаагүй.

```bash
cd Backend
uv sync --frozen
uv run mem --root .. init
uv run mem --root .. verify
uv run mem --root .. serve
```

`serve` нь stdio (стүдио) MCP client-д зориулагдсан, web server биш. `--root`-д бүх MCP тохиргоонд **absolute path** хэрэглэнэ. MCP client хүсэлт явуулах үед ажиллана; idle үед санах ой өөрөө үүсэхгүй.

## MCP client холбох

Жишээ JSON — өөрийн executable/root path-аар солино:

```json
{
  "mcpServers": {
    "mem": {
      "command": "/absolute/path/Mem/Backend/.venv/bin/mem",
      "args": ["--root", "/absolute/path/Mem", "serve"]
    }
  }
}
```

Windows-ийн executable нь `Backend/.venv/Scripts/mem.exe`. Codex CLI ашиглавал:

```bash
codex mcp add mem -- /absolute/path/Mem/Backend/.venv/bin/mem --root /absolute/path/Mem serve
```

Client/agent-ийн зааварт [memory skill](Backend/skills/memory/SKILL.md)-ийг уншихыг заана; энэ файл байгаагаараа client-д автоматаар суухгүй. [Backend API жишээ ба ажиллагааны заавар](Backend/README.md).

## SQLite-ийг Git-ээр хувилбарчлах

Live DB/WAL/cache ignored. **Consistent L3 snapshot** (снэпшот) нь Git-д track хийх зориулалттай:

```bash
cd Backend
uv run mem --root .. snapshot
cd ..
git add L3/history.snapshot.sqlite3
# L1/L2 өөрчлөлт байвал тэдгээрийг мөн stage хийнэ.
git commit -m "memory: checkpoint"
```

Snapshot үүсгэх/commit хийх хооронд өөр session эсвэл editor-оор memory-г зэрэг өөрчлөхгүй. Backend өөрөө Git commit/push хийхгүй. Binary snapshot-ийн мөр тус бүрийн diff/merge ажиллахгүй; нэг компьютерийн дараалсан хувилбаруудад зориулсан. Snapshot дотор түүх, нотолгоо, өмнөх Markdown хувилбар зэрэг хувийн мэдээлэл бий; Git remote-ийн харагдах байдлыг хэрэглэгч сонгоно.

Шинээр clone хийсэн, live DB байхгүй үед (L1/L2 нь Git-ээс ирсэн байх):

```bash
cd Backend
uv sync --frozen
uv run mem restore-snapshot --snapshot ../L3/history.snapshot.sqlite3 --destination ../L3/history.sqlite3
uv run mem --root .. reindex
uv run mem --root .. verify
```

`restore-snapshot` байгаа DB-г дарж бичихгүй. Git snapshot нь L3-ийн хувилбар, **бүх сангийн backup биш**: raw Inbox/ZIP нь Git default-д орохгүй.

## Бүх санг нөөцлөх, сэргээх

```bash
cd Backend
uv run mem --root .. backup --output /absolute/outside-repo/mem-backup.zip
uv run mem restore --backup /absolute/outside-repo/mem-backup.zip --destination /absolute/new-empty/Mem
```

Backup нь L1/L2, live L3-ийн consistent copy, Inbox, бүх ZIP/архивын тайлбарыг checksum manifest-тай хадгална. Cache орохгүй, restore дээр rebuild хийнэ. Destination шинэ/хоосон байх ёстой. v0.1 backup-ийн өгөгдлийн хязгаар 1 GiB, restore member-ийн хязгаар 100,000. Off-device хуулбарыг өөрийн backup системд хадгална.

## Тасалдал, зөрчил

```bash
cd Backend
uv run mem --root .. verify
uv run mem --root .. recover
uv run mem --root .. reindex
```

Бичилт process restart үед journal-аас сэргээнэ. `RECOVERY_CONFLICT` бол файлын өнөөгийн bytes нь хүлээсэн өмнөх/дараах хувилбарын аль нь ч биш гэсэн үг; өгөгдлийг дарж бичихгүй. Health-аас operation ID, journal-ийн before/after хувилбаруудыг хөгжүүлэгчээр шалгуулж, external edit-ийг тусад нь хадгалсны дараа зөрчлийг шийдэж `recover` дахин ажиллуулна. Journal-ийг устгаж хүчээр нээхгүй.

Obsidian/editor-оор Markdown засаж болно; дараагийн search дээр индекс шинэчлэгдэнэ. MCP write/backup явагдах агшинд нэг файлыг гаднаас зэрэг засахгүй. Watcher байхгүй учраас гаднын editor-ийн бүх завсрын хувилбар backend-д хадгалагдахгүй; Git/editor history хэрэглэнэ. Local filesystem шаардлагатай; network drive болон дурын power/disk failure-д алдагдалгүй гэсэн баталгаа байхгүй.

## Хөгжүүлэлт

```bash
cd Backend
uv sync --frozen
uv run pytest -q
```

Тестүүд temporary store ашиглана, хэрэглэгчийн memory-д demo өгөгдөл оруулахгүй. Async MCP smoke нь OS-ийн local socketpair/thread wakeup шаардана; хатуу sandbox түүнийг хориглосон бол зөвшөөрөгдсөн runtime-д тестийг ажиллуулна, assertion-ийг disable хийхгүй.

[Загвар](docs/superpowers/specs/2026-10-30-memory-system-design.md) · [Ажлын төлөвлөгөө](docs/superpowers/plans/2026-10-30-memory-system.md) · [Шалгалтын нотолгоо](docs/memory-acceptance.md)
