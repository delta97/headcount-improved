#!/usr/bin/env python3
"""Non-interactive front end for the install engine.

Nothing here decides anything: it parses arguments, calls core, and prints. That matters
because this is what a script calls, and a front end that made its own judgment about when
an overwrite is acceptable would be a second answer to a question core already answers.

  python3 scripts/install/cli.py plan      --package DIR --target DIR [--update]
  python3 scripts/install/cli.py install   --package DIR --target DIR [--dry-run] [--force]
                                           [--no-backup]
  python3 scripts/install/cli.py update    --package DIR --target DIR [--dry-run] [--force]
  python3 scripts/install/cli.py uninstall --target DIR [--dry-run] [--force]

Exit codes, because callers act on them:

  0  the target now matches the package (or, for a dry run and a plan, it would)
  1  refused, or applied with something left alone — the target does not match the package
  2  the command was called wrongly: bad flags, or a package directory that is not there

There is never a prompt. Anything destructive needs --force on the command line, which is
also what makes this safe to run from CI: without the flag the worst case is exit 1.
"""
import argparse
import os
import sys

if __package__ in (None, ""):
    # Invoked as a path (`python3 scripts/install/cli.py`), so the package is not importable
    # yet; scripts/ is the import root for both entry points.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from install import core
else:
    from . import core

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2


def _row(label, value):
    return f"  {label:<11}{value}"


def summarize(plan):
    """The block printed by every subcommand, in the same shape for a dry run and a real one."""
    lines = [f"plan: {plan.operation}"]
    if plan.package_dir:
        lines.append(_row("package", plan.package_dir))
    lines.append(_row("target", plan.target_dir))
    lines.append(_row("version", f"{plan.headcount_version} ({plan.runtime}, build "
                                 f"{(plan.build_id or '')[:12]})"))
    lines.append(_row("add", len(plan.adds)))
    lines.append(_row("replace", len(plan.replacements)))
    lines.append(_row("remove", len(plan.removals)))
    lines.append(_row("collision", len(plan.collisions)))
    lines.append(_row("unmanaged", len(plan.unmanaged)))
    lines.append(_row("backup", "required" if plan.backup_required else "not required"))
    for collision in plan.collisions:
        lines.append(f"  collision: {collision.path} ({collision.reason})")
    return lines


def report(result):
    lines = ["result: " + ("dry run (nothing was written)" if result.dry_run
                           else f"{result.plan.operation} applied")]
    lines.append(_row("written", len(result.written)))
    lines.append(_row("removed", len(result.removed)))
    lines.append(_row("skipped", len(result.skipped)))
    lines.append(_row("backup", result.backup_dir or "none"))
    for path in result.skipped:
        lines.append(f"  skipped: {path} (edited locally — left as it is)")
    return lines


def build_parser():
    parser = argparse.ArgumentParser(
        prog="install/cli.py",
        description="Install, update, or remove a Headcount runtime package.")
    subcommands = parser.add_subparsers(dest="command", metavar="COMMAND")

    def add(name, help_text):
        return subcommands.add_parser(name, help=help_text, description=help_text)

    def package_argument(sub):
        sub.add_argument("--package", required=True, metavar="DIR",
                         help="package directory built by scripts/package")

    def target_argument(sub):
        sub.add_argument("--target", required=True, metavar="DIR",
                         help="directory to install into, such as ~/.codex")

    def dry_run_argument(sub):
        sub.add_argument("--dry-run", action="store_true",
                         help="report the plan and change nothing")

    def force_argument(sub):
        sub.add_argument("--force", action="store_true",
                         help="resolve collisions by overwriting, after taking a backup")

    plan = add("plan", "Report what an install would do. Writes nothing.")
    package_argument(plan)
    target_argument(plan)
    plan.add_argument("--update", action="store_true",
                      help="plan an update over the existing install instead")

    install = add("install", "Install a package into a target directory.")
    package_argument(install)
    target_argument(install)
    dry_run_argument(install)
    force_argument(install)
    install.add_argument("--no-backup", dest="backup", action="store_false",
                         help="with --force, overwrite without keeping a copy first")

    update = add("update", "Move an existing install to a newer package.")
    package_argument(update)
    target_argument(update)
    dry_run_argument(update)
    force_argument(update)

    remove = add("uninstall", "Remove the files this install recorded, and nothing else.")
    target_argument(remove)
    dry_run_argument(remove)
    force_argument(remove)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_usage(sys.stderr)
        print("error: a subcommand is required", file=sys.stderr)
        return EXIT_USAGE
    package = getattr(args, "package", None)
    if package is not None and not os.path.isdir(package):
        parser.error(f"--package: {package} is not a directory")  # argparse exits 2
    backup = getattr(args, "backup", True)
    force = getattr(args, "force", False)

    try:
        if args.command == "plan":
            plan = (core.plan_update(package, args.target) if args.update
                    else core.plan_install(package, args.target))
            print("\n".join(summarize(plan)))
            return EXIT_REFUSED if plan.collisions else EXIT_OK
        if args.command == "install":
            result = core.apply_install(package_dir=package, target_dir=args.target,
                                        force=force, backup=backup, dry_run=args.dry_run)
        elif args.command == "update":
            result = core.update_install(package_dir=package, target_dir=args.target,
                                         force=force, backup=backup, dry_run=args.dry_run)
        else:
            result = core.uninstall(args.target, force=force, backup=backup,
                                    dry_run=args.dry_run)
    except core.InstallError as error:
        print(f"refused: {error}", file=sys.stderr)
        return EXIT_REFUSED

    print("\n".join(summarize(result.plan) + report(result)))
    return EXIT_OK if result.complete else EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
