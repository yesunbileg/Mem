import json
import sys
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mem.store import init_store, open_store

from .helpers import sample_patch


async def test_stdio_tools_and_memory_workflow(tmp_path):
    root = tmp_path / "memory"
    init_store(root).close()
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "mem.cli", "--root", str(root), "serve"]
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(
            reader, writer, read_timeout_seconds=timedelta(seconds=10)
        ) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {t.name for t in tools.tools} == {
                "memory_search",
                "memory_read",
                "memory_apply_patch",
                "memory_inbox_list",
                "memory_inbox_read",
                "memory_reindex",
                "memory_health",
            }
            p = sample_patch().model_dump(mode="json")
            first = await session.call_tool("memory_apply_patch", {"patch": p})
            assert not first.isError
            a = first.structuredContent
            again = await session.call_tool("memory_apply_patch", {"patch": p})
            assert again.structuredContent["operation_id"] == a["operation_id"]
            search = await session.call_tool("memory_search", {"query": "smoke"})
            assert len(search.structuredContent["items"]) == 3
            read = await session.call_tool(
                "memory_read", {"ref": "mem://event/" + a["id_map"]["new:e"]}
            )
            assert read.structuredContent["data"]["original"]["occurred_at"] is None
            health = await session.call_tool("memory_health", {})
            assert health.structuredContent["ready"]
            (root / "L0/Inbox/idle.md").write_text("Just a question")
            health2 = await session.call_tool("memory_health", {})
            assert (
                health2.structuredContent["source_revision"]
                == health.structuredContent["source_revision"]
            )
            assert not list((root / "L0/Archive").rglob("*.zip"))
            bad = await session.call_tool("memory_read", {"ref": "not-a-ref"})
            assert bad.isError and "VALIDATION_ERROR" in bad.content[0].text
    with open_store(root) as s:
        assert s.db.execute("SELECT count(*) FROM events").fetchone()[0] == 1


def test_cli_init_verify(tmp_path):
    import subprocess

    root = tmp_path / "m"
    a = subprocess.run(
        [sys.executable, "-m", "mem.cli", "--root", str(root), "init"],
        capture_output=True,
        text=True,
    )
    assert a.returncode == 0, a.stderr
    b = subprocess.run(
        [sys.executable, "-m", "mem.cli", "--root", str(root), "verify"],
        capture_output=True,
        text=True,
    )
    assert b.returncode == 0 and json.loads(b.stdout)["ready"]
