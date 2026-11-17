"""Command line: python -m access_review [serve|report] [--llm mock|claude]"""
import argparse
from pathlib import Path

from .agent import run_review, write_report
from .server import serve

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    p = argparse.ArgumentParser(prog="access_review",
                                description="Read-only AI access review agent")
    p.add_argument("command", nargs="?", default="serve", choices=["serve", "report"])
    p.add_argument("--llm", default="mock", choices=["mock", "claude"],
                   help="mock = no key needed; claude = uses ANTHROPIC_API_KEY")
    p.add_argument("--data", default=str(ROOT / "data"))
    p.add_argument("--out", default=str(ROOT / "out"))
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args(argv)

    review = run_review(a.data, llm=a.llm)
    if a.command == "report":
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text(write_report(review))
        print(f"{len(review['findings'])} items flagged -> {out / 'report.md'}")
    else:
        serve(review, a.out, a.port)


if __name__ == "__main__":
    main()
