from pathlib import Path

from tools.run_pc104_cross_layer_fault_sync import (
    process_tree_rss_kib_from_pid,
)


def write_process(
    proc_root: Path,
    pid: int,
    resident_pages: int,
    children: tuple[int, ...] = (),
) -> None:
    process_dir = proc_root / str(pid)
    task_dir = process_dir / "task" / str(pid)
    task_dir.mkdir(parents=True)
    (process_dir / "statm").write_text(
        f"100 {resident_pages} 0 0 0 0 0\n",
        encoding="ascii",
    )
    (task_dir / "children").write_text(
        " ".join(str(child) for child in children),
        encoding="ascii",
    )


def test_process_tree_rss_includes_recursive_descendants(tmp_path: Path) -> None:
    write_process(tmp_path, 100, 10, (101, 102, 101))
    write_process(tmp_path, 101, 20, (103,))
    write_process(tmp_path, 102, 30)
    write_process(tmp_path, 103, 40)

    assert process_tree_rss_kib_from_pid(
        100,
        proc_root=tmp_path,
        page_size_kib=4,
    ) == 400


def test_process_tree_rss_returns_minus_one_for_missing_root(
    tmp_path: Path,
) -> None:
    assert process_tree_rss_kib_from_pid(
        999,
        proc_root=tmp_path,
        page_size_kib=4,
    ) == -1
