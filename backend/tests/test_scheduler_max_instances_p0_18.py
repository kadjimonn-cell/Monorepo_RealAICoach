from pathlib import Path


SOURCE_PATH = Path("/app/backend/scheduler.py")


def _extract_add_job_calls(source: str) -> list[tuple[int, str]]:
    calls: list[tuple[int, str]] = []
    idx = 0
    marker = "scheduler.add_job("

    while True:
        start = source.find(marker, idx)
        if start == -1:
            break

        cursor = start + len(marker)
        depth = 1
        in_str = False
        quote = ""
        escaped = False

        while cursor < len(source) and depth > 0:
            ch = source[cursor]

            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    in_str = False
            else:
                if ch in ('"', "'"):
                    in_str = True
                    quote = ch
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1

            cursor += 1

        line = source.count("\n", 0, start) + 1
        calls.append((line, source[start:cursor]))
        idx = cursor

    return calls


def test_every_coalesced_scheduler_job_is_single_instance() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    calls = _extract_add_job_calls(source)

    coalesced = [(line, block) for line, block in calls if "coalesce=True" in block]
    assert len(coalesced) == 18

    missing_max_instances = [line for line, block in coalesced if "max_instances=1" not in block]
    assert not missing_max_instances, f"Missing max_instances=1 in coalesced add_job blocks at lines: {missing_max_instances}"
