from typing import List, Union

import io
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen
import shlex
import subprocess
from typing import Optional, Tuple

scripts_path = Path(__file__).resolve().parent
repo_path = scripts_path.parent.resolve()
work_path = repo_path / "work"
iree_path = work_path / "iree"
llvm_submodule_path = iree_path / "third_party" / "llvm-project"

BOUNDARY = "gc0p4Jq0M2Yt08j34c0p"


class DiscordStatusBuilder:
    def __init__(self, message: str):
        self.payload = {
            "content": message,
            "attachments": [],
        }
        self.parts: List[bytes] = []

    def add_attachment(
        self,
        filename: str,
        description: str,
        content_type: str,
        contents: Union[bytes, str],
    ):
        index = len(self.payload["attachments"])
        self.payload["attachments"].append(
            {
                "id": index,
                "description": description,
                "filename": filename,
            }
        )
        out = io.BytesIO()
        out.write(
            f'Content-Disposition: form-data; name="files[{index}]"; filename="{filename}"\r\n'.encode()
        )
        out.write(f"Content-Type: {content_type}\r\n\r\n".encode())
        out.write(contents.encode() if isinstance(contents, str) else contents)
        self.parts.append(out.getvalue())

    def generate(self) -> bytes:
        CRLF = b"\r\n"
        payload_json = json.dumps(self.payload)
        part_out = io.BytesIO()
        part_out.write(
            'Content-Disposition: form-data; name="payload_json"\r\n'.encode()
        )
        part_out.write("Content-Type: application/json\r\n\r\n".encode())
        part_out.write(payload_json.encode())
        self.parts.insert(0, part_out.getvalue())

        out = io.BytesIO()
        for i, part in enumerate(self.parts):
            if i > 0:
                out.write(CRLF)
            out.write(f"--{BOUNDARY}".encode())
            out.write(CRLF)
            out.write(part)
        out.write(CRLF)
        out.write(f"--{BOUNDARY}--".encode())
        out.write(CRLF)
        return out.getvalue()

    def post(self):
        webhook_path = repo_path / ".discord_webhook"
        try:
            with open(webhook_path, "rt") as f:
                webhook_url = f.read().strip()
        except IOError as e:
            raise RuntimeError(
                f"Could not read discord webhook URL from {webhook_path}"
            )
        payload = self.generate()
        request = Request(webhook_url, payload, method="POST")
        request.add_header("Content-Type", f"multipart/form-data;boundary={BOUNDARY}")
        # Discord seems to block the default Python UA with Forbidden.
        request.add_header(
            "User-Agent",
            "Mozilla/5.0 (X11; U; Linux i686) Gecko/20071127 Firefox/2.0.0.11",
        )
        print("*** REQUEST ***")
        print(request.headers)
        print(request.data)
        response_json = urlopen(request).read().decode()
        print(response_json)


def git_setup_remote(remote_alias, url, *, repo_dir=None):
    needs_create = False
    try:
        existing_url = git_exec(
            ["remote", "get-url", remote_alias],
            capture_output=True,
            repo_dir=repo_dir,
            quiet=True,
        )
        existing_url = existing_url.strip()
        if existing_url == url:
            return
    except subprocess.CalledProcessError:
        # Does not exist.
        needs_create = True

    if needs_create:
        git_exec(["remote", "add", "--no-tags", remote_alias, url], repo_dir=repo_dir)
    else:
        git_exec(["remote", "set-url", remote_alias, url], repo_dir=repo_dir)


def git_is_porcelain(*, repo_dir=None):
    output = git_exec(
        ["status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        quiet=True,
        repo_dir=repo_dir,
    ).strip()
    return not bool(output)


def git_check_porcelain(*, repo_dir=None):
    output = git_exec(
        ["status", "--porcelain"],
        capture_output=True,
        quiet=True,
        repo_dir=repo_dir,
    ).strip()
    if output:
        actual_repo_dir = repo_dir
        raise SystemExit(
            f"ERROR: git directory {actual_repo_dir} is not clean. "
            f"Please stash changes:\n{output}"
        )


def git_fetch(*, repository=None, ref=None, repo_dir=None):
    args = ["fetch"]
    if repository:
        args.append(repository)
    if ref is not None:
        args.append(ref)
    git_exec(args, repo_dir=repo_dir)


def git_checkout(ref, *, repo_dir=None):
    git_exec(["checkout", ref], repo_dir=repo_dir)


def git_check_if_branch_exists(branch_name, remote=None, repo_dir=None):
    args = ["branch", "--all", "-l"]
    full_name = branch_name
    if remote is not None:
        args.append("--remote")
        full_name = f"{remote}/{full_name}"
    args.append(full_name)
    output = git_exec(args, capture_output=True, quiet=True, repo_dir=repo_dir).strip()
    if output:
        raise SystemExit(f"ERROR: {full_name} already exists.\n")


def git_create_branch(
    branch_name, *, checkout=True, ref=None, force=False, repo_dir=None, remote=None
):
    if not force:
        git_check_if_branch_exists(branch_name)
        git_check_if_branch_exists(branch_name, remote=remote)
    branch_args = ["branch"]
    if force:
        branch_args.append("-f")
    branch_args.append(branch_name)
    if ref is not None:
        branch_args.append(ref)
    git_exec(branch_args, repo_dir=repo_dir)

    if checkout:
        git_exec(["checkout", branch_name], repo_dir=repo_dir)


def git_push_branch(repository, branch_name, *, force=False, repo_dir=None):
    push_args = ["push", "--set-upstream"]
    if force:
        push_args.append("-f")
    push_args.append(repository)
    push_args.append(f"{branch_name}:{branch_name}")
    git_exec(push_args, repo_dir=repo_dir)


def git_branch_exists(branch_name, *, repo_dir=None):
    output = git_exec(
        ["branch", "-l", branch_name],
        repo_dir=repo_dir,
        quiet=True,
        capture_output=True,
    ).strip()
    return bool(output)


def git_submodule_set_origin(path, *, url=None, branch=None, repo_dir=None):
    if url is not None:
        git_exec(["submodule", "set-url", "--", path, url], repo_dir=repo_dir)

    if branch is not None:
        try:
            if branch == "--default":
                git_exec(
                    ["submodule", "set-branch", "--default", "--", path],
                    repo_dir=repo_dir,
                )
            else:
                git_exec(
                    ["submodule", "set-branch", "--branch", branch, "--", path],
                    repo_dir=repo_dir,
                )
        except subprocess.CalledProcessError:
            # The set-branch command returns 0 on change and !0 on no change.
            # This is a bit unfortunate.
            ...


def git_reset(ref, *, hard=True, repo_dir=None):
    args = ["reset"]
    if hard:
        args.append("--hard")
    args.append(ref)
    git_exec(args, repo_dir=repo_dir)


def git_rebase(ref, *, remote: str, repo_dir=None):
    args = ["pull", "--rebase", remote, ref]
    git_exec(args, repo_dir=repo_dir)


def git_current_commit(*, repo_dir=None) -> Tuple[str, str]:
    output = git_exec(
        ["log", "-n", "1", "--pretty=format:%H %s (%an on %ci)"],
        capture_output=True,
        repo_dir=repo_dir,
        quiet=True,
    )
    output = output.strip()
    parts = output.split(" ")
    # Return commit, full_summary
    return parts[0], output


def git_commit_summary(ref, repo_dir=None) -> str:
    output = git_exec(
        ["log", "-n", "1", "--pretty=format:%H %s (%an on %ci)", ref],
        capture_output=True,
        repo_dir=repo_dir,
        quiet=True,
    )
    output = output.strip()
    # Return full_summary
    return output


def git_log_range(refs=(), *, repo_dir=None, paths=()) -> List[Tuple[str, str]]:
    """Does a `git log ref1 ref2 -- paths.

    Returns a list of tuples of (commit, desc).
    """
    args = ["log", "--pretty=format:%H %s (%an on %ci)"] + list(refs)
    if paths:
        args.append("--")
        args.extend(list(paths))
    output = git_exec(args, repo_dir=repo_dir, capture_output=True)
    lines = output.splitlines()
    results = []
    for line in lines:
        commit, desc = line.split(" ", maxsplit=1)
        results.append((commit, desc))
    return results


def git_merge_base(ref1, ref2, *, repo_dir=None) -> str:
    return git_exec(
        ["merge-base", ref1, ref2], quiet=True, capture_output=True, repo_dir=repo_dir
    ).strip()


def git_create_commit(*, message, add_all=False, repo_dir=None):
    if add_all:
        git_exec(["add", "-A"], repo_dir=repo_dir)
    git_exec(["commit", "-m", message], repo_dir=repo_dir)


def git_ls_remote_branches(repository_url, *, filter=None, repo_dir=None):
    args = ["ls-remote", "-h", repository_url]
    if filter:
        args.extend(filter)
    output = git_exec(args, quiet=True, capture_output=True)
    lines = output.strip().splitlines(keepends=False)

    # Format is <commit> refs/heads/branch_name
    def extract_branch(line):
        parts = re.split("\\s+", line)
        ref = parts[1]
        prefix = "refs/heads/"
        if ref.startswith(prefix):
            ref = ref[len(prefix) :]
        return ref

    return [extract_branch(l) for l in lines]


def git_remote_head(remote: str, head: str, repo_dir=None) -> Optional[str]:
    # Get the remote head (i.e. "refs/heads/main") commit or None.
    args = ["ls-remote", "--heads", remote, head]
    output = git_exec(args, capture_output=True, repo_dir=repo_dir)
    lines = output.strip().splitlines(keepends=False)
    if not lines:
        return None

    def extract_commit(line):
        parts = re.split("\\s+", line)
        commit = parts[0]
        return commit

    return next(extract_commit(l) for l in lines)


def git_current_branch(*, repo_dir=None):
    return git_exec(
        ["rev-parse", "--abbrev-ref", "HEAD"],
        repo_dir=repo_dir,
        quiet=True,
        capture_output=True,
    ).strip()


def check_origin_update_help(repo_dir):
    existing_url = git_exec(
        ["remote", "get-url", "--push", "origin"],
        capture_output=True,
        repo_dir=repo_dir,
        quiet=True,
    )
    existing_url = existing_url.strip()
    if existing_url.startswith("https://github.com/"):
        new_url = existing_url.replace("https://github.com/", "git@github.com:", 1)
        print(
            "Your push URL is for GitHub HTTPS. You may need to switch to ssh for interactive use:"
        )
        print(f"  (cd {repo_dir} && git remote set-url --push origin {new_url})")
        return False
    return True


def git_exec(args, *, repo_dir, quiet=False, capture_output=False):
    full_args = ["git"] + args
    full_args_quoted = [shlex.quote(a) for a in full_args]
    if not quiet:
        print(f"  ++ EXEC: (cd {repo_dir} && {' '.join(full_args_quoted)})")
    if capture_output:
        return subprocess.check_output(full_args, cwd=repo_dir).decode("utf-8")
    else:
        subprocess.check_call(full_args, cwd=repo_dir)
