from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, List

from project.api.pdf_analysis import analyze_pdf_path, PDFAnalysisError


logger = logging.getLogger(__name__)


def _iter_pdfs(input_dir: Path) -> List[Path]:
    files = []
    for p in sorted(input_dir.iterdir()):
        if p.is_file() and p.suffix.lower() == ".pdf":
            files.append(p)
    return files


async def _process_one(path: Path, out_dir: Path, timeout: float) -> dict[str, Any] | dict:
    try:
        result = await analyze_pdf_path(str(path), timeout=timeout)
        # Save JSON
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{path.stem}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        return {"ok": True, "file": str(path), "result": result}
    except PDFAnalysisError as e:
        logger.error("Analysis failed for %s: %s", path, e)
        return {"ok": False, "file": str(path), "error": str(e)}
    except Exception as e:  # pragma: no cover
        logger.exception("Unexpected error for %s", path)
        return {"ok": False, "file": str(path), "error": str(e)}


def _fmt_summary(entry: dict[str, Any]) -> str:
    if not entry.get("ok"):
        return f"[FAIL] {entry['file']}: {entry.get('error')}"
    r = entry["result"]
    vol = r.get("volume", {})
    cmpx = r.get("complexity", {})
    cat = r.get("category", {})
    basis = cat.get("basis")
    return (
        f"[OK] {entry['file']} | lang={r.get('doc_language')} "
        f"pages={vol.get('page_count')} words={vol.get('word_count')} "
        f"t={vol.get('reading_time_min')}m | complexity={cmpx.get('level')}({cmpx.get('score')}) "
        f"| category={cat.get('label')}({cat.get('score')}) basis={basis}"
    )


async def main_async(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    files = _iter_pdfs(input_dir)
    if not files:
        print(f"Нет PDF файлов в {input_dir}")
        return 1

    print(f"Найдено {len(files)} PDF. Запуск анализа (timeout={args.timeout}s, concurrency={args.concurrency})…")

    sem = asyncio.Semaphore(args.concurrency)
    async def wrapped(p: Path):
        async with sem:
            return await _process_one(p, out_dir, args.timeout)

    results = await asyncio.gather(*(wrapped(p) for p in files))

    # Print per-file summary
    print("\nРезультаты:")
    for e in results:
        print(_fmt_summary(e))

    # Totals
    ok_count = sum(1 for e in results if e.get("ok"))
    print(f"\nИтого: OK={ok_count}, FAIL={len(results) - ok_count}. JSON сохранён в {out_dir}.")
    return 0 if ok_count == len(results) else 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Прогон анализа PDF из папки pdf_for_eval")
    parser.add_argument("--input-dir", default="pdf_for_eval", help="Директория с PDF (по умолчанию pdf_for_eval)")
    parser.add_argument("--out-dir", default="eval_results", help="Куда сохранять JSON результаты")
    parser.add_argument("--concurrency", type=int, default=3, help="Количество одновременных задач")
    parser.add_argument("--timeout", type=float, default=120.0, help="Таймаут анализа (сек)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
