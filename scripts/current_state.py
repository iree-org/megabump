from typing import Tuple

import megabump_utils as mb

LLVM_REPO_DIR = mb.llvm_submodule_path
TRACK_PATHS = ("mlir", "utils/bazel")

class CurrentState:
    """Current state of the llvm-project integrate."""

    def __init__(self, args):
        self.args = args
        self.current_commit, self.current_summary = mb.git_current_commit(
            repo_dir=LLVM_REPO_DIR
        )
        # The common commit between the llvm-project submodule and upstream.
        self.merge_base_commit = mb.git_merge_base(
            self.current_commit, "upstream/main", repo_dir=LLVM_REPO_DIR
        )
        # Whether the current llvm-project commit is clean (True) or
        # carries patches (False).
        self.is_clean = self.merge_base_commit == self.current_commit
        # List of (commit, desc) tuples in reverse chronological order for
        # commits that upstream is ahead.
        self.new_commits = mb.git_log_range(
            refs=("upstream/main", f"^{self.merge_base_commit}"),
            paths=TRACK_PATHS,
            repo_dir=LLVM_REPO_DIR,
        )

    def find_next_commit(self) -> Tuple[str, str]:
        """Finds the next LLVM commit to advance to.

        Returns (commit, desc).
        """
        if self.args.advance_to:
            for commit, desc in self.new_commits:
                if commit == self.args.advance_to:
                    return commit, desc
            else:
                print(
                    f"WARNING: Commit is not in recommended requested range. You may want to return to {self.current_commit} if this isn't right."
                )
                return commit, mb.git_commit_summary(commit, repo_dir=LLVM_REPO_DIR)
        else:
            if not self.new_commits:
                raise ValueError(f"No new commits")
            else:
                return next(reversed(self.new_commits))

    def index_of_next_commit(self, needle_commit: str) -> int:
        for i, (new_commit, desc) in enumerate(reversed(self.new_commits)):
            if new_commit == needle_commit:
                return i
        return -1
