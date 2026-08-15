# -*- coding: utf-8 -*-
r"""이 클론이 `origin/main` 을 따라잡았는지 **쓰기 전에** 본다.

## 왜 있나

2026-08-15, 지피 씬 6장이 회색 스튜디오 배경으로 나왔다. 프롬프트가 틀린 게
아니라 **낡은 판본의 코드가 프롬프트를 만들었다** — 이 클론이 `origin/main`
보다 2커밋 뒤처져 있었고, 그 사이 머지된 PR #9 가 배경을 «실제 공간»으로
바꾸고 `place` 인자를 넣었다. 클론이 뒤처졌다는 신호는 **아무 데도 없었다.**

같은 계열이 같은 날 세 번 났다.
  ① 스킬 라이브 정본이 링크라서 feature 브랜치 규칙으로 스케줄이 돌았다.
  ② 드리프트 감사가 낡은 클론과 비교해 «갈라졌다»고 오경보를 냈다(PR #42).
  ③ 이 건 — 낡은 클론이 크레딧을 쓰는 생성을 잘못 만들었다.

①②는 각각 막았는데 ③이 또 났다. 공통 원인은 하나다 — **낡은 판본으로 도는
경로가 조용하다.** 정관 §0 이 말하는 그 경로라, 시끄럽게 만든다.

## 어디에 붙나

`card.py` 가 임포트될 때 자동으로 돈다. 빌드 스크립트마다 한 줄씩 넣는 방식은
**넣는 것을 잊은 스크립트가 곧 구멍**이 된다 — 그리고 구멍이 있는지 아무도 모른다.
`content-ops/cards` 를 쓰는 모든 빌드가 `card` 를 임포트하므로 여기 한 곳이면 된다.

## main 과 feature 브랜치를 다르게 대한다

`main` 에서 뒤처진 것은 **그냥 안 당긴 것**이라 고칠 방법이 하나뿐이다 → 죽인다.
feature 브랜치가 뒤처진 것은 **스택 작업 중이면 정상**이다 → 크게 경고만 한다.
둘을 같이 죽이면 진행 중인 브랜치가 전부 멈추고, 그러면 사람이 우회로를 찾는다.

## 우회로를 감추지 않는다

네트워크가 없으면 신선도를 «알 수 없다». 알 수 없는 것을 통과로 넘기지 않는다
(§0) — 죽이되 탈출구 이름을 메시지에 같이 적는다. 막기만 하고 길을 안 알려주면
세션이 스스로 우회로를 찾고, 그 우회로는 로그에 안 남는다. `TOMANGCHI_SKIP_FRESHNESS`
로 끄면 **끌 때마다 배너가 찍힌다.**
"""
import io
import os
import subprocess
import sys

#: 이 파일이 들어 있는 저장소. `cards/` 의 한 단계 위다.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENV_SKIP = "TOMANGCHI_SKIP_FRESHNESS"
REMOTE_REF = "origin/main"


def _git(repo, *args, timeout=60):
    return subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, timeout=timeout)


def _out(p):
    return p.stdout.decode("utf-8", "replace").strip()


def check(repo=None, remote_ref=REMOTE_REF, fetch=True):
    """`(코드, 메시지)` — 코드는 ok / behind / behind-branch / no-fetch / no-repo.

    `fetch=False` 는 역검증에서 «이미 받아 둔 ref 로 판정만» 볼 때 쓴다.
    """
    repo = repo or REPO
    if not os.path.isdir(os.path.join(repo, ".git")) and not os.path.isfile(
            os.path.join(repo, ".git")):
        return "no-repo", f"git 저장소가 아니다: {repo}"

    if fetch:
        try:
            p = _git(repo, "fetch", "--quiet", "origin")
        except Exception as e:
            return "no-fetch", f"git fetch 실패 ({type(e).__name__}: {e})"
        if p.returncode != 0:
            return "no-fetch", f"git fetch 실패: {_out(p) or p.stderr.decode('utf-8', 'replace').strip()}"

    p = _git(repo, "rev-list", "--count", f"HEAD..{remote_ref}")
    if p.returncode != 0:
        return "no-fetch", f"{remote_ref} 를 읽을 수 없다"
    behind = int(_out(p) or 0)
    if behind == 0:
        return "ok", f"{remote_ref} 와 같다"

    branch = _out(_git(repo, "rev-parse", "--abbrev-ref", "HEAD"))
    code = "behind" if branch == "main" else "behind-branch"
    return code, (f"이 클론이 {remote_ref} 보다 {behind}커밋 뒤처졌다 "
                  f"(현재 {branch}) — git -C {repo} pull --ff-only")


_BANNER = "=" * 72


def assert_fresh(repo=None, stream=sys.stderr):
    """낡은 판본으로 도는 것을 막는다. 통과하면 조용하다."""
    if os.environ.get(ENV_SKIP):
        print(f"{_BANNER}\n[신선도 검사 꺼짐] {ENV_SKIP} 이 설정돼 있다.\n"
              f"낡은 판본으로 만든 산출물일 수 있다 — 크레딧을 쓰는 생성에는 끄지 말 것.\n"
              f"{_BANNER}", file=stream)
        return "skipped"

    code, msg = check(repo)
    if code == "ok":
        return code
    if code == "behind-branch":
        print(f"{_BANNER}\n[신선도 경고] {msg}\n"
              f"feature 브랜치라 멈추지는 않는다. 스택 작업이 아니라면 당길 것.\n"
              f"{_BANNER}", file=stream)
        return code

    raise SystemExit(
        f"\n{_BANNER}\n"
        f"[신선도 검사 실패] {msg}\n\n"
        f"낡은 판본의 코드로 만든 산출물은 규격을 지킨 것처럼 보이면서 틀린다.\n"
        f"2026-08-15 지피 씬 6장이 이 경로로 회색 스튜디오 배경으로 나왔다.\n\n"
        f"고치는 법:  git -C {repo or REPO} pull --ff-only\n"
        f"정말 넘겨야 하면:  set {ENV_SKIP}=1   (끌 때마다 배너가 찍힌다)\n"
        f"{_BANNER}")


# ── 역검증 (정관 §0) ─────────────────────────────────────────────────
# 통과만 확인하는 검사는 헛돌아도 통과처럼 보인다. 그래서 **일부러 뒤처진 클론**을
# 만들어 실제로 걸리는지 본다. 케이스는 서로 걸리지 않게 분리한다 — 「따라잡은
# 클론」이 ok 를 내는 것까지 같이 봐야 «전부 걸리는 고장»과 구분된다.


def _synth(root):
    """`(origin, 따라잡은 클론, 뒤처진 클론)` 을 만든다. 네트워크를 쓰지 않는다."""
    origin = os.path.join(root, "origin")
    os.makedirs(origin)
    env = ["-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false"]

    def run(repo, *a):
        p = subprocess.run(["git", "-C", repo, *env, *a], capture_output=True)
        if p.returncode != 0:
            raise RuntimeError(f"git {' '.join(a)}: "
                               f"{p.stderr.decode('utf-8', 'replace')}")
        return p

    run(origin, "init", "--quiet", "--initial-branch=main", ".")
    with open(os.path.join(origin, "a.txt"), "w") as f:
        f.write("1\n")
    run(origin, "add", "a.txt")
    run(origin, "commit", "--quiet", "-m", "c1")

    behind = os.path.join(root, "behind")
    subprocess.run(["git", "clone", "--quiet", origin, behind], capture_output=True)

    # origin 만 한 커밋 더 나아간다 → behind 는 뒤처진다.
    with open(os.path.join(origin, "a.txt"), "w") as f:
        f.write("2\n")
    run(origin, "add", "a.txt")
    run(origin, "commit", "--quiet", "-m", "c2")

    fresh = os.path.join(root, "fresh")
    subprocess.run(["git", "clone", "--quiet", origin, fresh], capture_output=True)
    return origin, fresh, behind


def self_test():
    """`[(이름, 기대, 실제, 통과)]`."""
    import tempfile

    out = []
    with tempfile.TemporaryDirectory(prefix="fresh_") as td:
        _, fresh, behind = _synth(td)
        for name, repo, expect in (("따라잡은 클론", fresh, "ok"),
                                   ("뒤처진 클론", behind, "behind")):
            got, _msg = check(repo)
            out.append((name, expect, got, got == expect))

        # `check` 가 맞게 판정해도 `assert_fresh` 가 그 판정을 안 쓰면 소용없다.
        # **막는 것까지** 본다 — 판정과 차단은 다른 일이다.
        try:
            assert_fresh(behind, stream=io.StringIO())
            out.append(("뒤처짐 차단", "SystemExit", "통과시킴", False))
        except SystemExit as e:
            ok = "pull --ff-only" in str(e)
            out.append(("뒤처짐 차단", "SystemExit", "죽음+대안제시" if ok else "죽음",
                        ok))
        try:
            assert_fresh(fresh, stream=io.StringIO())
            out.append(("따라잡음 통과", "통과", "통과", True))
        except SystemExit:
            out.append(("따라잡음 통과", "통과", "죽음", False))
    # 저장소가 아닌 경로도 조용히 통과하면 안 된다.
    got, _ = check(os.path.dirname(os.path.abspath(__file__)) + os.sep + "__없음__")
    out.append(("저장소 아님", "no-repo", got, got == "no-repo"))
    return out


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    print("[신선도 검사 역검증]")
    allgood = True
    for name, expect, got, ok in self_test():
        allgood &= ok
        print(f"  {'OK  ' if ok else 'FAIL'} {name:14} 기대={expect:9} 실제={got}")

    code, msg = check()
    print(f"\n[이 클론] {code} — {msg}")
    sys.exit(0 if allgood else 1)
