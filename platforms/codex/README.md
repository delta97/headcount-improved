# Headcount for Codex and Agent Skills

Headcount's canonical form is a Claude Code plugin marketplace: departments under `plugins/`,
each with its skills and its charter. A runtime that reads a flat `AGENTS.md` plus `skills/` and
`agents/` directories — Codex, and anything else following the Agent Skills layout — cannot read
that tree directly. So the tree is projected into a **package**, and the package is installed.

Two programs, deliberately separate:

| Step | Program | Runs where |
| --- | --- | --- |
| Build a package from this repository | `scripts/package/codex.py` | on a checkout of this repo |
| Install that package into a runtime | `scripts/install/cli.py` | on the machine that runs the agent |

The split exists because the second half runs on somebody's laptop, in a directory that already
holds their own files. It never reads the repository, and it never needs to: everything it
installs, and every hash it verifies, is inside the package.

Python 3 standard library only. Nothing to install first.

---

## Build a package

```
python3 scripts/package/codex.py --output ~/headcount-codex
python3 scripts/package/validate.py ~/headcount-codex
```

The result is a directory:

```
headcount-package.json     manifest: version, source commit, build id, and a sha256 per file
AGENTS.md                  routing preamble
README.md
agents/<name>.md           one file per charter
skills/<bare-name>/...     one directory per skill
```

`headcount-package.json` lists a hash for every other file in the package. The installer rehashes
all of them before it writes anything, so a package that lost a file in transit, or was edited
after it was built, is refused rather than half-installed. See the builder's own documentation for
its flags; the installer cares only about the format above.

---

## Install

```
python3 scripts/install/cli.py plan      --package ~/headcount-codex --target ~/.codex
python3 scripts/install/cli.py install   --package ~/headcount-codex --target ~/.codex
python3 scripts/install/cli.py update    --package ~/headcount-codex --target ~/.codex
python3 scripts/install/cli.py uninstall --target ~/.codex
```

Flags:

| Flag | Applies to | Meaning |
| --- | --- | --- |
| `--dry-run` | install, update, uninstall | Do the whole calculation, write nothing. |
| `--force` | install, update, uninstall | Resolve collisions by overwriting, after a backup. |
| `--no-backup` | install | With `--force`, skip the backup. Unrecoverable; see below. |
| `--update` | plan | Plan an update over the existing install instead of a fresh one. |

Exit codes, because scripts act on them:

| Code | Meaning |
| --- | --- |
| `0` | The target matches the package. For `--dry-run` and `plan`, it would. |
| `1` | Refused, or applied with something left alone. The target does not match the package. |
| `2` | The command was called wrongly: bad flags, or a package directory that is not there. |

Nothing prompts. Every destructive step needs `--force` on the command line, which is what makes
this safe to run unattended: without that flag, the worst outcome is exit 1 and an untouched target.

`plan` and `--dry-run` print the same block as a real run, so what you read in a rehearsal is what
the real run acts on:

```
plan: install
  package    /home/you/headcount-codex
  target     /home/you/.codex
  version    2.3.4 (codex, build 9a599a8fd188)
  add        61
  replace    0
  remove     0
  collision  1
  unmanaged  4
  backup     required
  collision: AGENTS.md (unmanaged-exists)
```

---

## The safety model

The target directory belongs to the user. Headcount may delete or overwrite only the bytes it
wrote itself, and it knows which those are because it wrote them down.

**The install manifest is the sole authority.** `~/.codex/.headcount-install.json` records the
format, the Headcount version, the source commit, the build id, the runtime, and a sha256 for
every installed file. A path listed there whose content still matches is Headcount's to replace.
Everything else in the target is somebody else's.

**Two kinds of collision, and neither is resolved silently.**

- `unmanaged-exists` — the package wants to write a path that already exists and was never
  recorded as ours. This is what an install into a directory with a hand-built `agents/` tree
  hits. An install refuses; so does an update.
- `locally-modified` — a path we did install, whose content has since changed. Somebody edited it.
  An install refuses. An update and an uninstall skip that one file, finish the rest, and report
  it, which is the outcome that loses no work.

A refused run changes nothing at all: no files, no directories, no manifest.

**`--force` is the only destructive path, and it takes a backup first.** Before overwriting or
removing anything it did not write, the installer copies the current content into
`<target>/.headcount-backups/<UTC timestamp>/`, preserving the relative paths, and prints the
directory. Unmodified managed files are not copied there — they are byte-for-byte reproducible
from the package, and including them would bury the files that actually matter. Backups are never
removed by any later operation, including `uninstall`. `--force --no-backup` together mean "I know,
overwrite it, keep no copy"; that combination is the one way to lose content here.

**Unmanaged files always survive.** Install, update, and uninstall alike. `uninstall` removes the
files the manifest records and then the directories that held them, if those are now empty; a
directory still holding one of your files stays, with your file in it.

**An interrupted run leaves whole files, never half-written ones.** Files are copied into a
staging directory inside the target, rehashed there against the package manifest, then moved into
place with an atomic rename. A crash mid-install leaves some files placed and some not — none
truncated — and no manifest, so the next run sees the placed ones as collisions and stops instead
of assuming they are ours.

**The manifest is written last.** The failure mode that leaves untracked files, which the next run
reports, is preferred over one that leaves a manifest claiming files that were never written.

**Local edits stay flagged.** When an update skips a modified file, the manifest keeps the hash
originally recorded for it, not the edited one. Adopting your bytes as ours would let the *next*
update overwrite them without a word. Instead the file stays flagged until you resolve it — revert
it, or re-run with `--force` and take the backup.

**A plan is a description, not a permit.** Applying re-derives the plan from disk rather than
trusting one computed earlier, so a target that changed in between is caught rather than acted on
from stale facts.

---

## Graphical installer

```
python3 platforms/codex/installer_gui.py [--package DIR] [--target DIR]
```

For anyone who would rather not use a terminal. It shows the target, the version, the count of new
and updated files, anything in the way, and where the backup would go — then asks. It contains no
copy or delete logic of its own: it calls the same planning and applying functions the CLI does, so
the two cannot disagree about what is safe.

tkinter ships with many Python builds but not all of them, and a server has no display. In either
case the GUI prints the equivalent command line and exits nonzero rather than failing with a
traceback. The GUI is optional; the CLI is the supported path.

---

## Recovering

| Situation | What to do |
| --- | --- |
| Install refused, `unmanaged-exists` | Move your files aside, or re-run with `--force` and read the backup path it prints. |
| Update skipped a file you edited | Keep the edit and ignore the report, or `--force` to take the package's version, with your copy kept in the backup directory. |
| You forced an overwrite you regret | Copy the file back from `<target>/.headcount-backups/<timestamp>/`. |
| The manifest is corrupt or unreadable | Move `.headcount-install.json` aside. The target is then unmanaged: nothing will be deleted, and a fresh install reports every existing path as a collision. |
| You want it all gone | `uninstall` removes exactly what was recorded. Your own files and every backup stay. |

## Working on the installer

```
python3 -m unittest discover -s tests -t . -q
```

`tests/test_install_core.py` and `tests/test_install_cli.py` build throwaway packages and targets
in temporary directories and assert the guarantees above one at a time — an aborted install
deleting nothing, a forced install backing content up first, an update preserving an unmanaged
file, an uninstall leaving one. Each is a case where a regression would destroy somebody's work,
which is why they are asserted against fabricated trees rather than a healthy one.
