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
