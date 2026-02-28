from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
from pathlib import Path


def parse_pair(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Expected format app_id=plain_key")
    app_id, plain_key = value.split("=", 1)
    app_id = app_id.strip()
    plain_key = plain_key.strip()
    if not app_id:
        raise argparse.ArgumentTypeError("app_id is empty")
    if not plain_key:
        raise argparse.ArgumentTypeError("plain_key is empty")
    return app_id, plain_key


def hash_key(plain_key: str) -> str:
    return "sha256:" + hashlib.sha256(plain_key.encode("utf-8")).hexdigest()


def load_pairs_file(path: Path) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            app_id, plain_key = line.split("=", 1)
        elif ":" in line:
            app_id, plain_key = line.split(":", 1)
        else:
            raise ValueError(
                f"{path}:{line_no} invalid format, expected app_id=plain_key or app_id:plain_key"
            )
        app_id = app_id.strip()
        plain_key = plain_key.strip()
        if not app_id or not plain_key:
            raise ValueError(f"{path}:{line_no} app_id and plain_key must be non-empty")
        pairs.append((app_id, plain_key))
    return pairs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate CLIENT_KEYS_JSON with sha256 hashes for backend config."
    )
    parser.add_argument(
        "--pair",
        action="append",
        type=parse_pair,
        default=[],
        help="Pair in format app_id=plain_key. Can be repeated.",
    )
    parser.add_argument(
        "--pairs-file",
        type=Path,
        help="File with lines app_id=plain_key (or app_id:plain_key).",
    )
    parser.add_argument(
        "--generate",
        action="append",
        default=[],
        metavar="APP_ID",
        help="Generate random key for app_id (32 bytes urlsafe). Can be repeated.",
    )
    parser.add_argument(
        "--shared-key",
        type=str,
        help="Optional shared plain key for all apps, stored under '*' entry.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    pairs: list[tuple[str, str]] = list(args.pair)
    if args.pairs_file:
        if not args.pairs_file.exists():
            print(f"File not found: {args.pairs_file}", file=sys.stderr)
            return 2
        pairs.extend(load_pairs_file(args.pairs_file))

    generated_plain: dict[str, str] = {}
    for app_id in args.generate:
        app_id = app_id.strip()
        if not app_id:
            print("Empty app_id in --generate", file=sys.stderr)
            return 2
        generated_plain[app_id] = secrets.token_urlsafe(32)
        pairs.append((app_id, generated_plain[app_id]))

    if args.shared_key:
        pairs.append(("*", args.shared_key))

    if not pairs:
        print("No input provided. Use --pair, --pairs-file or --generate.", file=sys.stderr)
        return 2

    output: dict[str, list[str]] = {}
    for app_id, plain_key in pairs:
        output.setdefault(app_id, []).append(hash_key(plain_key))

    if args.pretty:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))

    if generated_plain:
        print("\nGenerated plain keys (save once, do not commit):", file=sys.stderr)
        for app_id, plain_key in generated_plain.items():
            print(f"{app_id}={plain_key}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
