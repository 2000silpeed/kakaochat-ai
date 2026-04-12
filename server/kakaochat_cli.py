#!/usr/bin/env python3
"""KakaoChat AI CLI — 방 오너용 토큰 등록/관리 도구.

사용법:
    # 1. Claude Code 장기 토큰 발급 (브라우저 OAuth)
    claude setup-token

    # 2. 토큰을 서버에 등록
    python kakaochat_cli.py register --room "AI스터디" --token "발급된_토큰" --server "http://localhost:8765"

    # 3. 등록된 방 목록 확인
    python kakaochat_cli.py list --server "http://localhost:8765"

    # 4. 토큰 삭제
    python kakaochat_cli.py remove --room "AI스터디" --server "http://localhost:8765"

    # 5. 원스텝: 토큰 발급 + 등록 (setup-token 실행 후 바로 등록)
    python kakaochat_cli.py setup --room "AI스터디" --server "http://localhost:8765"
"""
import argparse
import json
import subprocess
import sys
import urllib.request
import urllib.error


def _api_call(server: str, method: str, path: str, data: dict | None = None) -> dict:
    url = f"{server.rstrip('/')}{path}"
    body = json.dumps(data).encode() if data else None
    headers = {"Content-Type": "application/json"} if data else {}

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"status": "error", "message": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"status": "error", "message": f"Connection failed: {e.reason}"}


def cmd_register(args):
    token = args.token
    if not token:
        token = input("Claude OAuth 토큰을 붙여넣으세요: ").strip()
    if not token:
        print("토큰이 비어있습니다.", file=sys.stderr)
        sys.exit(1)

    result = _api_call(args.server, "POST", "/auth/register", {
        "room": args.room,
        "token": token,
        "email": args.email or "",
    })
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_remove(args):
    result = _api_call(args.server, "DELETE", f"/auth/{args.room}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_list(args):
    result = _api_call(args.server, "GET", "/auth/rooms")
    if result.get("status") == "ok":
        rooms = result.get("rooms", [])
        if not rooms:
            print("등록된 방이 없습니다.")
        else:
            print(f"\n등록된 방 ({len(rooms)}개):\n")
            for r in rooms:
                email = f" ({r['email']})" if r.get("email") else ""
                print(f"  - {r['room']}{email}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_setup(args):
    """토큰 발급 + 등록을 한번에."""
    print("Claude Code 장기 토큰을 발급합니다...")
    print("브라우저에서 OAuth 인증을 완료하세요.\n")

    try:
        proc = subprocess.run(
            ["claude", "setup-token"],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            print(f"setup-token 실패: {proc.stderr}", file=sys.stderr)
            sys.exit(1)

        token = proc.stdout.strip()
        if not token:
            print("토큰이 출력되지 않았습니다. 수동으로 등록하세요:", file=sys.stderr)
            print(f"  python kakaochat_cli.py register --room \"{args.room}\" --server \"{args.server}\"")
            sys.exit(1)

        print(f"\n토큰 발급 완료! 서버에 등록합니다...")
        result = _api_call(args.server, "POST", "/auth/register", {
            "room": args.room,
            "token": token,
            "email": args.email or "",
        })
        print(json.dumps(result, ensure_ascii=False, indent=2))

    except FileNotFoundError:
        print("claude CLI가 설치되어 있지 않습니다.", file=sys.stderr)
        print("설치: https://docs.anthropic.com/en/docs/claude-code")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("토큰 발급 타임아웃 (120초).", file=sys.stderr)
        sys.exit(1)


def cmd_status(args):
    result = _api_call(args.server, "GET", "/sessions")
    if result.get("status") == "ok":
        sessions = result.get("sessions", [])
        if not sessions:
            print("활성 세션이 없습니다.")
        else:
            print(f"\n활성 세션 ({len(sessions)}개):\n")
            for s in sessions:
                status = "활성" if s["alive"] else "비활성"
                print(f"  - {s['room']}: {status}, 메시지 {s['message_count']}개")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="KakaoChat AI — 방 오너용 토큰 등록/관리",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 토큰 발급 + 등록 (원스텝)
  python kakaochat_cli.py setup --room "AI스터디" --server http://localhost:8765

  # 수동 등록
  python kakaochat_cli.py register --room "AI스터디" --token "토큰값" --server http://localhost:8765

  # 방 목록
  python kakaochat_cli.py list --server http://localhost:8765
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # setup (원스텝)
    p_setup = sub.add_parser("setup", help="토큰 발급 + 등록 (원스텝)")
    p_setup.add_argument("--room", required=True, help="오픈챗방 이름")
    p_setup.add_argument("--server", default="http://localhost:8765", help="서버 주소")
    p_setup.add_argument("--email", help="이메일 (선택)")
    p_setup.set_defaults(func=cmd_setup)

    # register
    p_reg = sub.add_parser("register", help="토큰 수동 등록")
    p_reg.add_argument("--room", required=True, help="오픈챗방 이름")
    p_reg.add_argument("--token", help="Claude OAuth 토큰 (생략 시 입력 프롬프트)")
    p_reg.add_argument("--server", default="http://localhost:8765", help="서버 주소")
    p_reg.add_argument("--email", help="이메일 (선택)")
    p_reg.set_defaults(func=cmd_register)

    # remove
    p_rm = sub.add_parser("remove", help="토큰 삭제")
    p_rm.add_argument("--room", required=True, help="오픈챗방 이름")
    p_rm.add_argument("--server", default="http://localhost:8765", help="서버 주소")
    p_rm.set_defaults(func=cmd_remove)

    # list
    p_ls = sub.add_parser("list", help="등록된 방 목록")
    p_ls.add_argument("--server", default="http://localhost:8765", help="서버 주소")
    p_ls.set_defaults(func=cmd_list)

    # status
    p_st = sub.add_parser("status", help="세션 상태 조회")
    p_st.add_argument("--server", default="http://localhost:8765", help="서버 주소")
    p_st.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
