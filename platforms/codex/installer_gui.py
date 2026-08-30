#!/usr/bin/env python3
"""Optional desktop front end for the installer. Everything it does, the CLI already does.

It exists for the person who downloaded a package and has no reason to own a terminal, and it
is deliberately thin: it calls plan_install, shows what the plan says, and calls apply_install
if the user agrees. It holds no copy, delete, or overwrite logic of its own — if it did, the
window and the command line could disagree about what is safe, and the window is the one no
test would be watching.

tkinter is imported inside main, never at module level, for two reasons: it is absent from
many Python builds (a headless server, a slim container), and an import at the top would make
this file unimportable there, so even a smoke test could not run. Without tkinter, or without
a display, it prints where to go instead and exits nonzero.

  python3 platforms/codex/installer_gui.py [--package DIR] [--target DIR]
"""
import argparse
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "scripts"))

from install import core  # noqa: E402

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_NO_GUI = 3

CLI_HINT = ("The graphical installer is unavailable here. The command line does the same "
            "work:\n\n"
            "  python3 scripts/install/cli.py plan    --package DIR --target DIR\n"
            "  python3 scripts/install/cli.py install --package DIR --target DIR\n")


def describe(plan):
    """The text shown before anything is written. Counts first, then what is in the way."""
    lines = [
        f"Target:      {plan.target_dir}",
        f"Package:     {plan.package_dir}",
        f"Version:     {plan.headcount_version} ({plan.runtime})",
        "",
        f"New files:      {len(plan.adds)}",
        f"Updated files:  {len(plan.replacements)}",
        f"Left untouched: {len(plan.unmanaged)} file(s) already in the target",
    ]
    if plan.collisions:
        lines += [
            "",
            f"{len(plan.collisions)} file(s) in the way. Headcount did not write these, or "
            "they were edited after it did:",
        ]
        lines += [f"  {c.path}  ({c.reason})" for c in plan.collisions[:12]]
        if len(plan.collisions) > 12:
            lines.append(f"  and {len(plan.collisions) - 12} more")
        lines += ["",
                  "Installing over them copies each one into a timestamped backup folder "
                  "inside the target first."]
    return "\n".join(lines)


def _build_window(tkinter, messagebox, package_dir, target_dir):
    window = tkinter.Tk()
    window.title("Headcount installer")
    package_var = tkinter.StringVar(value=package_dir or "")
    target_var = tkinter.StringVar(value=target_dir or os.path.expanduser("~/.codex"))
    output = tkinter.StringVar(value="Choose a package and a target, then Preview.")

    frame = tkinter.Frame(window, padx=12, pady=12)
    frame.pack(fill="both", expand=True)
    for row, (label, variable) in enumerate((("Package folder", package_var),
                                             ("Target folder", target_var))):
        tkinter.Label(frame, text=label).grid(row=row, column=0, sticky="w")
        tkinter.Entry(frame, textvariable=variable, width=52).grid(row=row, column=1,
                                                                   sticky="we", padx=6)
    detail = tkinter.Label(frame, textvariable=output, justify="left", anchor="w")
    detail.grid(row=2, column=0, columnspan=2, sticky="we", pady=(12, 12))

    def current_plan():
        return core.plan_install(package_var.get().strip(), target_var.get().strip())

    def preview():
        try:
            output.set(describe(current_plan()))
        except core.InstallError as error:
            output.set(str(error))

    def install():
        try:
            plan = current_plan()
        except core.InstallError as error:
            messagebox.showerror("Cannot install", str(error))
            return
        output.set(describe(plan))
        force = False
        if plan.collisions:
            # The only destructive path, and it is never reached without this answer.
            force = messagebox.askyesno(
                "Overwrite files Headcount did not write?",
                f"{len(plan.collisions)} file(s) in {plan.target_dir} will be replaced.\n\n"
                "A copy of each is kept in a timestamped backup folder inside the target. "
                "Files Headcount does not know about are left alone.\n\nContinue?")
            if not force:
                output.set("Nothing was changed.")
                return
        try:
            result = core.apply_install(plan, force=force)
        except core.InstallError as error:
            messagebox.showerror("Nothing was changed", str(error))
            return
        summary = (f"Installed {len(result.written)} file(s) into {plan.target_dir}.\n"
                   f"Version {plan.headcount_version}.")
        if result.backup_dir:
            summary += f"\nBackup: {result.backup_dir}"
        if result.skipped:
            summary += f"\nLeft alone: {', '.join(result.skipped)}"
        output.set(summary)
        messagebox.showinfo("Done", summary)

    buttons = tkinter.Frame(frame)
    buttons.grid(row=3, column=0, columnspan=2, sticky="e")
    tkinter.Button(buttons, text="Preview", command=preview).pack(side="left", padx=4)
    tkinter.Button(buttons, text="Install", command=install).pack(side="left", padx=4)
    tkinter.Button(buttons, text="Close", command=window.destroy).pack(side="left", padx=4)
    return window


def main(argv=None):
    parser = argparse.ArgumentParser(description="Graphical installer for a Headcount "
                                                 "runtime package.")
    parser.add_argument("--package", metavar="DIR", help="package directory to install from")
    parser.add_argument("--target", metavar="DIR", help="directory to install into")
    args = parser.parse_args(argv)

    try:
        import tkinter
        from tkinter import messagebox
    except ImportError:
        print("tkinter is not installed for this Python.\n\n" + CLI_HINT, file=sys.stderr)
        return EXIT_NO_GUI

    try:
        window = _build_window(tkinter, messagebox, args.package, args.target)
    except tkinter.TclError as error:
        # No display: the usual case on a server or over a plain SSH session.
        print(f"No display available ({error}).\n\n" + CLI_HINT, file=sys.stderr)
        return EXIT_NO_GUI

    window.mainloop()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
