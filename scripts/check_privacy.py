"""检查可提交的源码；报告位置和规则，不打印匹配到的私密内容。"""

import argparse
import fnmatch
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
PRIVATE_FIELDS = {
    "QQ_APP_ID", "QQ_APP_SECRET", "LLM_API_KEY", "DEEPSEEK_API_KEY", "QQ_ALLOWED_GROUPS",
}
PRIVATE_DIRS = {
    ".git", ".venv", ".cache", ".idea", ".vscode", "__pycache__",
    "private", "secrets", "credentials", "runtime", "logs", "data", "conversations",
}
PRIVATE_NAMES = (
    "*.env", "*.pem", "*.key", "*.p12", "*.pfx", "*.sqlite*", "*.db", "*.log*",
    "*.bak", "*.backup", "*.zip", "*.jsonl", "credentials.json", "token.json",
    "tokens.json", "client_secret*.json", "chat_history*",
)
PATTERNS = (
    ("API 凭证格式", re.compile(
        r"sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
        r"|AKIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{30,}"
    )),
    ("私钥", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("明文密钥赋值", re.compile(
        r"(?:app_?secret|client_?secret|api_?key|access_?token)"
        r"[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_/-]{20,})", re.I
    )),
    ("个人主目录路径", re.compile(
        r"[A-Z]:[\\/]+Users[\\/]+(?!Public\b|Default\b|example\b|<)[^\s\\/\"']+"
        r"|/(?:Users|home)/(?!runner\b|user\b|example\b|<)[^\s/\"']+", re.I
    )),
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str


def private_path(relative: str) -> bool:
    path = PurePosixPath(relative)
    if any(part.lower() in PRIVATE_DIRS for part in path.parts):
        return True
    name = path.name.lower()
    if name == ".env.example":
        return False
    return name.startswith(".env") or any(fnmatch.fnmatch(name, p) for p in PRIVATE_NAMES)


def inspect_text(relative: str, text: str, known: tuple[str, ...] = ()) -> list[Finding]:
    findings = []
    if PurePosixPath(relative).name == ".env.example":
        from io import StringIO

        template = dotenv_values(stream=StringIO(text), interpolate=False)
        if any(template.get(field) for field in PRIVATE_FIELDS):
            findings.append(Finding(relative, 1, "公开示例的凭证和群标识字段必须留空"))
    for number, line in enumerate(text.splitlines(), 1):
        if any(value in line for value in known):
            findings.append(Finding(relative, number, "包含本机凭证或账号/群标识"))
        for rule, pattern in PATTERNS:
            if pattern.search(line):
                findings.append(Finding(relative, number, rule))
    return findings


def git(root: Path, *arguments: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "--git-dir=" + str(root / ".git"), "--work-tree=" + str(root), *arguments],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        raise RuntimeError("无法读取 Git 文件清单；请在 Git 仓库中运行检查。") from None


def local_private_values(root: Path) -> tuple[str, ...]:
    # 只在内存中用于匹配，不打印或保存这些值。
    values = dotenv_values(root / ".env", interpolate=False) if (root / ".env").is_file() else {}
    private = []
    for source in (values, os.environ):
        for field in PRIVATE_FIELDS:
            for value in (source.get(field) or "").split(","):
                if len(value.strip()) >= 4:
                    private.append(value.strip())
    return tuple(set(private))


def check_project(root: Path, *, staged: bool = False) -> tuple[list[Finding], int]:
    root = root.resolve()
    known = local_private_values(root)
    options = ("--cached",) if staged else ("--cached", "--others", "--exclude-standard")
    files = sorted(set(filter(None, git(root, "ls-files", "-z", *options).decode("utf-8").split("\0"))))
    findings = []
    for relative in files:
        if private_path(relative):
            findings.append(Finding(relative, 1, "本机私密文件不应加入提交"))
            continue
        path = root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            findings.append(Finding(relative, 1, "符号链接需人工确认目标和数据范围"))
            continue
        if staged:
            data = git(root, "show", ":" + relative)
        elif path.is_file():
            data = path.read_bytes()
        else:
            continue
        findings.extend(inspect_text(relative, data.decode("utf-8", errors="replace"), known))
    return findings, len(files)


def safe_path(path: str, known: tuple[str, ...]) -> str:
    for value in sorted(known, key=len, reverse=True):
        path = path.replace(value, "[私密值已隐藏]")
    for _, pattern in PATTERNS:
        path = pattern.sub("[私密内容已隐藏]", path)
    return path.replace("\r", "").replace("\n", "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="检查 Git 暂存区中的实际内容")
    args = parser.parse_args()
    try:
        findings, count = check_project(ROOT, staged=args.staged)
        known = local_private_values(ROOT)
    except (RuntimeError, OSError):
        print("隐私检查未完成：无法读取文件或 Git 清单；未输出文件内容。")
        return 2
    for finding in findings:
        print(f"{safe_path(finding.path, known)}:{finding.line}：{finding.rule}（内容已隐藏）")
    if findings:
        print(f"隐私检查未通过：{len(findings)} 项，请修正后再发布。")
        return 1
    print(f"隐私检查通过：已扫描 {count} 个公开候选文件，未发现规则命中的私密内容。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
