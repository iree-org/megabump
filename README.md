# IREE Megabump Automation

This is a collection of scripts built by stellaraccident to help automate
an incremental LLVM update of the IREE project. She used to run this
manually and acreted scripts to help with key part -- so they are somewhat
organic.

## General Flow

The goal of an integrate is to traverse a sequence of affecting LLVM commits
between where we are and upstream HEAD. 

At each step, we do a light-weight
local build and coarse validation that there are no egregious compiler bugs
that crash or make the build unusable. When this smoketest fails, we break
from the loop and call for help by pushing the branch to the main repo to
trigger CI and posting a message on Discord.

The integrate can be stopped at any point, adjusted and landed. Typically
if up against an egregious commit, we manually back off by one commit,
push and land that. Then pick up the work to fix.

## Starting an integrate

Run `./scripts/start_integrate` to reset `work/iree` to the main branch,
fast-forward to upstream HEAD and create a new date-based integrate branch.
This will start the branch with an empty commit with a description.

TODO: Add a script to push this branch to the repo and create a draft PR.

Then, it usually helps to plan your angle of attack. Run 
`./scripts/llvm_revision status` to see a list of all commits estimated to
have some impact on the project (reverse chronological, with the next commit
last). It's also a good idea at this point to look at the 
`third_party/llvm-project` submodule log and see what local patches we are
carrying, etc. Correlate those with what is coming to plan.

If the submodule is clean, you can just proceed. Otherwise, apply any reverts,
cherry-picks, or resets to get to the starting state you want.

## Main integrate loop

Run `./scripts/loop.sh` to run the main integrate smoketest/advance loop. At
the conclusion of each successful smoketest, the submodule will be advanced and
a descriptive commit added to the `iree` repo.

This can be done manually with:

```
./scripts/llvm_revision next [--advance-to=<commit>]
```

This will take the next affecting commit (see `./scripts/llvm_revision status`)
and rebase the submodule onto it. Finally, if this results in local patches
being carried, `./scripts/export_submodule_head` will be called, which will
advance the `sm-iree-{integrate_branch_name}` branch in the https://github.com/shark-infra/llvm-project
repository. This is done by creating special merge commits which ensure that
all prior rebases on the branch remain reachable, allowing this to be a persistent
submodule pointer that everyone can access.

## On Failure

When a smoketest fails or it is otherwise deemed necessary, break the loop and
run:

```
./scripts/gen_iree_llvm_error_report
```

This will summarize the compiler error log and call for help on Discord.

TODO: Do this automatically when the loop fails.

From here, do what is necessary to fix. For API breaks, this often just
involves adding a commit to the branch to fix it.

When ready to resume:

```
cd work/iree
git pull --ff-only
git submodule update
```

TODO: Automate this part, and also automate merging from main.

The flow tries to keep branch state such that forward progress is persistent.
If things go bad, just rewind and choose what to do. It's just git and a
CMake build of IREE underneath.

# Playbook for Handling Breakages

## API Changes / Compile Breaks

These can range from simple, one-line fixes to build file/path changes, 
to massive breaking changes, etc.
Usually, I'll have a look at the breaking patch and decide whether to just
fix inline on the integrate machine or page out. If fixing locally, just
commit a "fixups for XXXX" style commit and restart the loop.

## TensorFlow impacting ASM format changes

TensorFlow interfaces to IREE with some unstable dialects and there is a
chicken/egg issue. We don't have good solutions for this, but it doesn't
happen often. As an example: https://github.com/llvm/llvm-project/pull/67816

The path of least resistance for simple things like this is to just
carry a local revert of that patch for an integrate cycle or two. Then
pick in an update to the next TF nightly pip package when you decide to
drop the revert. Things will often have aligned by then.

This may not always be possible, and in that case, we need to have a discussion
to decide what to do (probably disable tests/benchmarks and mark the project
as not ok to stable release).

## Upstream Bug in MLIR

As an example, we found that https://github.com/llvm/llvm-project/pull/67809
broke some e2e tests. Upon investigation, we decided that the patch was incomplete.
In this case, it is preferable to:

* Revert the commit upstream, being polite and helpful to the author. Often as
  part of diagnosing, you may already have a partial commit or repro. Offer that.
* Revert the commit locally in the integrate branch and commit the submodule
  update to the main `iree` project on the integrate branch.
* Re-land, help the author, etc.

The reason that we prefer reverts versus fixes forwards is that it helps everyone
and it becomes very clear when people are looking at commit logs that there is a
problem to be worked around. Most integration automation will automatically drop
a local revert once it catches up, and a partial fix forward is not automatic,
requiring manual intervention by anyone who hits the bug.

## Upstream bug in LLVM

Because when we advance through the integrate branch, we do not stop at every
LLVM commit, it is possible that a bug in an LLVM backend sneaks in without
us having stopped on the exact commit. As an example, consider 
[this patch](https://github.com/llvm/llvm-project/pull/67178)
to the RISC-V backend which broke our X86 codegen. In this case, the failure
was in an e2e compilation test, which we validate on every affecting commit,
so the integrate loop broke on the first MLIR commit after this which exhibited
the failure.

Since I had two commits on the branch with a trivial repro, I proceeded to
bisect the LLVM commits. It only took 3 steps and pinpointed the exact issue.
I noted that the failure was clearly a bug upstream and not related to us,
asked the author if it was ok to revert, and then did so. We ended up going
the extra mile and [also providing an exact repro](https://github.com/openxla/iree/issues/15127)
and helped the author roll forward. This is almost always what you want to do
for these kinds of issues, especially one like this where one backend was
causing failures on another. If the author hadn't responded immediately, in this
case, I would have pushed a revert shortly after anyway. In other cases, I may
have waited. Judgment calls.

Bisecting a patched LLVM submodule is not trivial. We should write a script,
but here is the basic approach I used:

```
merge_base="$(git merge-base HEAD origin/main)"
cp_head="$(git rev-parse HEAD)"


# Re-apply cherry-picks
git cherry-pick ${merge_base}..${cp_head}

function bisect() {
  git reset --hard "$(git merge-base HEAD origin/main)" && \
  git bisect "$@" && \
  git cherry-pick ${merge_base}..${cp_head}
}

bisect start
bisect bad $merge_base
bisect good ...
```

The idea is that you have to reset the submodule to a pristine upstream
commit before running any bisect command. Then re-apply the stack of
cherry-picks after.

## Bug or regression in the full presubmit

Because we only run short smoketests on each upstream change, it is possible that
real failures in the full test suite can materialize and be missed for many
dozens of MLIR commits (or hundreds of LLVM commits). This does happen but is
relatively rare, so we don't optimize for it being anything but a manual process.

The usual approach I use is:

* Scan the integrate branch commit history and see if I can spot a likely
  culprit or two. `git reset --hard` once or twice and verify by pushing to a
  new draft PR and running automation. Note that this has always worked for me
  to date.
* Bisect the integrate branch. `git bisect` should mostly work here because
  we apply fixup patches per commit, so the branch is pretty densely/consistently
  free of gross build breakages. The main step you need to take after each `bisect`
  step is to run `git submodule update`. Depending on how tricky the issue is,
  you may have a local repro (easiest) or need to push to a temporary PR and run
  full automation.

If the failure is recent, I will usually choose to land the integrate just before
the breakage and then start a fresh one at that point, but judgment calls all
around. It is usually good to lock in forward progress vs firefighting a huge
integrate.

## Broken bazel build files

I don't spend any time at all on this. The Google team has to fix the Bazel build
pretty quickly so there are almost always patches ahead which apply cleanly and
unblock. Before readying an integrate to land, if there are Bazel patches needed
then, just find and pull them in on demand. Often times, this just lets us skip
any Bazel interventions needed. I never make Bazel fixes myself... just wait for
a patch from Google before proceeding to land.

## Trivially broken LIT tests.

We don't run exhaustive lit tests as part of the patch-by-patch smoke tests. If
material things change, they often come with a compilation break and get fixed
in-situ. For other trivial stuff, I just batch it up at the end or a big break
point where automation has run and ask someone to fix them. Once can obviously
envision this spiraling out of control and failures cascading, etc, but it hardly
ever happens. If it does, just bisect the branch and don't waste time otherwise.

## Incompatible MLIR Dependency

MLIR changes can break StableHLO and Torch-MLIR just like they break us. However,
since we just use basic features from both of those projects it is rare (I've
measured O(months) between affecting breakages on these projects). As such, I
never optimize for this case and just deal with it when it comes up. If a trivial
patch, I just make it in-situ and `export_submodule_head` to push it to our
patch repositories. When reconciling to land the whole integrate, I can choose to
do one of:

* Just carry the patch and fix forward: I'll land the integrate with a patched
  dependency, then land an LLVM version bump to the dependency upstream, patching
  my carried change in. Then on the main branch, bump the dependency that is
  now fixed.
* Bump the dependency to HEAD and see if that helps: StableHLO sometimes is
  tracking LLVM head somewhat closely and this can work. Torch-MLIR is usually
  updated *based on what we find* so this typically won't magically fix
  things there.

These issues tend to be rare. Ask.
