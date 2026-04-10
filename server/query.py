#!/usr/bin/env python3
"""CLI 질의 도구 — Mem0 메모리 검색.

Usage:
    python query.py "RAG 얘기 누가 했어?"
    python query.py --user 철수 "링크"
    python query.py --all
    python query.py --all --user 철수
    python query.py --room AI스터디 "RAG"
"""
import argparse
import json
import sys

from app.config import load_config
from app.memory import search_memory, get_all_memories

load_config()


def main():
    parser = argparse.ArgumentParser(description="KakaoChat AI 메모리 검색")
    parser.add_argument("query", nargs="?", help="검색 쿼리")
    parser.add_argument("--user", help="특정 사용자 필터")
    parser.add_argument("--room", help="특정 방 필터")
    parser.add_argument("--all", action="store_true", help="전체 메모리 조회")
    parser.add_argument("--limit", type=int, default=10, help="결과 수 (기본: 10)")
    args = parser.parse_args()

    if args.all:
        results = get_all_memories(user_id=args.user, room=args.room, limit=args.limit)
        if isinstance(results, dict) and "results" in results:
            results = results["results"]
        print(f"\n=== 전체 메모리 ({len(results)}개) ===\n")
        for r in results:
            memory = r.get("memory", r.get("text", ""))
            user = r.get("user_id", "?")
            print(f"  [{user}] {memory}")
        return

    if not args.query:
        parser.print_help()
        sys.exit(1)

    results = search_memory(args.query, user_id=args.user, room=args.room, limit=args.limit)
    if isinstance(results, dict) and "results" in results:
        results = results["results"]

    print(f"\n=== 검색: \"{args.query}\" (결과 {len(results)}개) ===\n")
    for i, r in enumerate(results, 1):
        memory = r.get("memory", r.get("text", ""))
        score = r.get("score", 0)
        user = r.get("user_id", "?")
        print(f"  {i}. [{user}] (score: {score:.3f}) {memory}")


if __name__ == "__main__":
    main()
