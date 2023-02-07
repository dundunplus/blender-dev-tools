#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

"""
This is a tool for reviewing commit ranges, writing into accept/reject files,
and optionally generate release-log-ready data.

Useful for reviewing revisions to back-port to stable builds.

Note that, if any of the data files generated already exist, they will be extended
with new revisions, not overwritten.

Note that, for the most complex 'wiki-ready' file generated by  `--accept-releaselog`,
proof-reading after this tool has ran is heavily suggested!

Example usage:

   ./git_log_review_commits_advanced.py  --source ../../.. --range HEAD~40..HEAD --filter 'BUGFIX' --accept-pretty --accept-releaselog --blender-rev 2.79

To add list of fixes between RC2 and RC3, and list both RC2 and RC3 fixes also in their own sections:

   ./git_log_review_commits_advanced.py  --source ../../.. --range <RC2 revision>..<RC3 revision> --filter 'BUGFIX' --accept-pretty --accept-releaselog --blender-rev 2.79 --blender-rstate=RC3 --blender-rstate-list="RC2,RC3"

To exclude all commits from some given files, by sha1 or by commit message (from previously generated release logs) - much handy when going over commits which were partially cherry-picked into a previous release branch e.g.:

   ./git_log_review_commits_advanced.py  --source ../../.. --range HEAD~40..HEAD --filter 'BUGFIX' --filter-exclude-sha1-fromfiles "review_accept.txt" "review_reject.txt" --filter-exclude-fromreleaselogs "review_accept_release_log.txt" --accept-pretty --accept-releaselog --blender-rev 2.75

"""

import os
import sys
import io
import re

ACCEPT_FILE = "review_accept.txt"
REJECT_FILE = "review_reject.txt"
ACCEPT_LOG_FILE = "review_accept_log.txt"
ACCEPT_PRETTY_FILE = "review_accept_pretty.txt"
ACCEPT_RELEASELOG_FILE = "review_accept_release_log.txt"

IGNORE_START_LINE = "<!-- IGNORE_START -->"
IGNORE_END_LINE = "<!-- IGNORE_END -->"

_cwd = os.getcwd()
__doc__ = __doc__ + \
    "\nRaw GIT revisions files:\n\t* Accepted: %s\n\t* Rejected: %s\n\n" \
    "Basic log accepted revisions: %s\n\nWiki-printed accepted revisions: %s\n\n" \
    "Full release notes wiki page: %s\n" \
    % (os.path.join(_cwd, ACCEPT_FILE), os.path.join(_cwd, REJECT_FILE),
       os.path.join(_cwd, ACCEPT_LOG_FILE), os.path.join(_cwd, ACCEPT_PRETTY_FILE),
       os.path.join(_cwd, ACCEPT_RELEASELOG_FILE))
del _cwd


class _Getch:
    """
    Gets a single character from standard input.
    Does not echo to the screen.
    """

    def __init__(self):
        try:
            self.impl = _GetchWindows()
        except ImportError:
            self.impl = _GetchUnix()

    def __call__(self):
        return self.impl()


class _GetchUnix:

    def __init__(self):
        import tty
        import sys

    def __call__(self):
        import sys
        import tty
        import termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch


class _GetchWindows:

    def __init__(self):
        import msvcrt

    def __call__(self):
        import msvcrt
        return msvcrt.getch()


getch = _Getch()
# ------------------------------------------------------------------------------
# Pretty Printing

USE_COLOR = True

if USE_COLOR:
    color_codes = {
        'black': '\033[0;30m',
        'bright_gray': '\033[0;37m',
        'blue': '\033[0;34m',
        'white': '\033[1;37m',
        'green': '\033[0;32m',
        'bright_blue': '\033[1;34m',
        'cyan': '\033[0;36m',
        'bright_green': '\033[1;32m',
        'red': '\033[0;31m',
        'bright_cyan': '\033[1;36m',
        'purple': '\033[0;35m',
        'bright_red': '\033[1;31m',
        'yellow': '\033[0;33m',
        'bright_purple': '\033[1;35m',
        'dark_gray': '\033[1;30m',
        'bright_yellow': '\033[1;33m',
        'normal': '\033[0m',
    }

    def colorize(msg, color=None):
        return (color_codes[color] + msg + color_codes['normal'])
else:
    def colorize(msg, color=None):
        return msg
bugfix = ""


BUGFIX_CATEGORIES = (
    ("Objects / Animation / GP", (
        "Animation",
        "Constraints",
        "Grease Pencil",
        "Objects",
        "Dependency Graph",
    ),
    ),

    ("Data / Geometry", (
        "Armatures",
        "Curve/Text Editing",
        "Mesh Editing",
        "Meta Editing",
        "Modifiers",
        "Material / Texture",
    ),
    ),

    ("Physics / Simulations / Sculpt / Paint", (
        "Particles",
        "Physics / Hair / Simulations",
        "Sculpting / Painting",
    ),
    ),

    ("Image / Video / Render", (
        "Image / UV Editing",
        "Masking",
        "Motion Tracking",
        "Movie Clip Editor",
        "Nodes / Compositor",
        "Render",
        "Render: Cycles",
        "Render: Freestyle",
        "Sequencer",
    ),
    ),

    ("UI / Spaces / Transform", (
        "3D View",
        "Input (NDOF / 3D Mouse)",
        "Outliner",
        "Text Editor",
        "Transform",
        "User Interface",
    ),
    ),

    ("Game Engine", (
    ),
    ),

    ("System / Misc", (
        "Audio",
        "Collada",
        "File I/O",
        "Other",
        "Python",
        "System",
    ),
    ),
)


sys.stdin = os.fdopen(sys.stdin.fileno(), "rb")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='surrogateescape', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='surrogateescape', line_buffering=True)


def gen_commit_summary(c):
    # In git, all commit message lines until first empty one are part of 'summary'.
    return c.body.split("\n\n")[0].strip(" :.;-\n").replace("\n", " ")


def print_commit(c):
    print("------------------------------------------------------------------------------")
    print(colorize(c.sha1.decode(), color='green'), end=" ")
    print(colorize(c.date.strftime("%Y/%m/%d"), color='purple'), end=" ")
    print(colorize(c.author, color='bright_blue'))
    print()
    print(colorize(c.body, color='normal'))
    print()
    print(colorize("Files: (%d)" % len(c.files_status), color='yellow'))
    for f in c.files_status:
        print(colorize("  %s %s" % (f[0].decode('ascii'), f[1].decode('ascii')), 'yellow'))
    print()


def gen_commit_log(c):
    return "rB%s   %s   %-30s   %s" % (c.sha1.decode()[:10], c.date.strftime("%Y/%m/%d"),
                                       c.author, gen_commit_summary(c))


re_bugify_str = r"T([0-9]{1,})"
re_bugify = re.compile(re_bugify_str)
re_commitify = re.compile(r"\W(r(?:B|BA|BAC|BTS)[0-9a-fA-F]{6,})")
re_prettify = re.compile(r"(.{,20}?)(Fix(?:ing|es)?\s*(?:for)?\s*" + re_bugify_str + r")\s*[-:,]*\s*", re.IGNORECASE)


def gen_commit_message_pretty(c, unreported=None):
    body = gen_commit_summary(c)

    tbody = re_prettify.sub(r"Fix {{BugReport|\3}}: \1", body)
    if tbody == body:
        if unreported is not None:
            unreported[0] = True
        tbody = "Fix unreported: %s" % body
    body = re_bugify.sub(r"{{BugReport|\1}}", tbody)
    body = re_commitify.sub(r"{{GitCommit|\1}}", body)

    return body


def gen_commit_pretty(c, unreported=None, rstate=None):
    body = gen_commit_message_pretty(c, unreported)

    if rstate is not None:
        return "* [%s] %s ({{GitCommit|rB%s}})." % (rstate, body, c.sha1.decode()[:10])
    return "* %s ({{GitCommit|rB%s}})." % (rstate, body, c.sha1.decode()[:10])


def gen_commit_unprettify(body):
    if body.startswith("* ["):
        end = body.find("]")
        if end > 0:
            body = body[end + 2:]  # +2 to remove ] itself, and following space.
    start = body.rfind("({{GitCommit|rB")
    if start > 0:
        body = body[:start - 1]  # -1 to remove trailing space.
    return body


def print_categories_tree():
    for i, (main_cat, sub_cats) in enumerate(BUGFIX_CATEGORIES):
        print("\t[%d] %s" % (i, main_cat))
        for j, sub_cat in enumerate(sub_cats):
            print("\t\t[%d] %s" % (j, sub_cat))


def release_log_extract_messages(path):
    messages = set()

    if os.path.exists(path):
        with open(path, 'r') as f:
            ignore = False
            header = True
            for l in f:
                if IGNORE_END_LINE in l:
                    ignore = False
                    continue
                elif ignore or IGNORE_START_LINE in l:
                    ignore = True
                    continue
                l = l.strip(" \n")
                if header and not l.startswith("=="):
                    continue  # Header, we don't care here.
                header = False
                if not l.startswith("==") and "Fix " in l:
                    messages.add(gen_commit_unprettify(l))

    return messages


def release_log_init(path, source_dir, blender_rev, start_sha1, end_sha1, rstate, rstate_list):
    from git_log import GitRepo

    if rstate is not None:
        header = "= Blender %s: Bug Fixes =\n\n" \
                 "[%s] Changes from revision {{GitCommit|rB%s}} to {{GitCommit|rB%s}}, inclusive.\n\n" \
                 % (blender_rev, rstate, start_sha1[:10], end_sha1[:10])
    else:
        header = "= Blender %s: Bug Fixes =\n\n" \
                 "Changes from revision {{GitCommit|rB%s}} to {{GitCommit|rB%s}}, inclusive.\n\n" \
                 % (blender_rev, start_sha1[:10], end_sha1[:10])

    release_log = {"__HEADER__": header, "__COUNT__": [0, 0], "__RSTATES__": {k: [] for k in rstate_list}}

    if os.path.exists(path):
        branch = GitRepo(source_dir).branch.decode().strip()

        sub_cats_to_main_cats = {s_cat: m_cat[0] for m_cat in BUGFIX_CATEGORIES for s_cat in m_cat[1]}
        main_cats = {m_cat[0] for m_cat in BUGFIX_CATEGORIES}
        with open(path, 'r') as f:
            header = []
            main_cat = None
            sub_cat = None
            ignore = False
            for l in f:
                if IGNORE_END_LINE in l:
                    ignore = False
                    continue
                elif ignore or IGNORE_START_LINE in l:
                    ignore = True
                    continue
                l = l.strip(" \n")
                if not header:
                    header.append(l)
                    for hl in f:
                        if IGNORE_END_LINE in hl:
                            ignore = False
                            continue
                        elif ignore or IGNORE_START_LINE in hl:
                            ignore = True
                            continue
                        hl = hl.strip(" \n")
                        if hl.startswith("=="):
                            main_cat = hl.strip(" =")
                            if main_cat not in main_cats:
                                sub_cat = main_cat
                                main_cat = sub_cats_to_main_cats.get(main_cat, None)
                            else:
                                sub_cat = None
                            #~ print("hl MAINCAT:", hl, main_cat, " | ", sub_cat)
                            break
                        header.append(hl)

                    if rstate is not None:
                        release_log["__HEADER__"] = "%s[%s] Changes from revision {{GitCommit|%s}} to " \
                                                    "{{GitCommit|%s}}, inclusive (''%s'' branch).\n\n" \
                                                    "" % ("\n".join(header), rstate,
                                                          start_sha1[:10], end_sha1[:10], branch)
                    else:
                        release_log["__HEADER__"] = "%sChanges from revision {{GitCommit|%s}} to {{GitCommit|%s}}, " \
                                                    "inclusive (''%s'' branch).\n\n" \
                                                    "" % ("\n".join(header), start_sha1[:10], end_sha1[:10], branch)
                    count = release_log["__COUNT__"] = [0, 0]
                    continue

                if l.startswith("==="):
                    sub_cat = l.strip(" =")
                    if sub_cat in sub_cats_to_main_cats:
                        main_cat = sub_cats_to_main_cats.get(sub_cat, None)
                    elif sub_cat in main_cats:
                        main_cat = sub_cat
                        sub_cat = None
                    else:
                        main_cat = None
                    #~ print("l SUBCAT:", l, main_cat, " | ", sub_cat)
                elif l.startswith("=="):
                    main_cat = l.strip(" =")
                    if main_cat not in main_cats:
                        sub_cat = main_cat
                        main_cat = sub_cats_to_main_cats.get(main_cat, None)
                    else:
                        sub_cat = None
                    #~ print("l MAINCAT:", l, main_cat, " | ", sub_cat)
                elif "Fix " in l:
                    if "Fix {{BugReport|" in l:
                        main_cat_data, _ = release_log.setdefault(main_cat, ({}, {}))
                        main_cat_data.setdefault(sub_cat, []).append(l)
                        count[0] += 1
                        #~ print("l REPORTED:", l)
                    else:
                        _, main_cat_data_unreported = release_log.setdefault(main_cat, ({}, {}))
                        main_cat_data_unreported.setdefault(sub_cat, []).append(l)
                        count[1] += 1
                        #~ print("l UNREPORTED:", l)
                    l_rstate = l.strip("* ")
                    if l_rstate.startswith("["):
                        end = l_rstate.find("]")
                        if end > 0:
                            rstate = l_rstate[1:end]
                            if rstate in release_log["__RSTATES__"]:
                                release_log["__RSTATES__"][rstate].append("* %s" % l_rstate[end + 1:].strip())

    return release_log


def write_release_log(path, release_log, c, cat, rstate, rstate_list):
    import io

    main_cat, sub_cats = BUGFIX_CATEGORIES[cat[0]]
    sub_cat = sub_cats[cat[1]] if cat[1] is not None else None

    main_cat_data, main_cat_data_unreported = release_log.setdefault(main_cat, ({}, {}))
    unreported = [False]
    entry = gen_commit_pretty(c, unreported, rstate)
    if unreported[0]:
        main_cat_data_unreported.setdefault(sub_cat, []).append(entry)
        release_log["__COUNT__"][1] += 1
    else:
        main_cat_data.setdefault(sub_cat, []).append(entry)
        release_log["__COUNT__"][0] += 1

    if rstate in release_log["__RSTATES__"]:
        release_log["__RSTATES__"][rstate].append(gen_commit_pretty(c))

    lines = []
    main_cat_lines = []
    sub_cat_lines = []
    for main_cat, sub_cats in BUGFIX_CATEGORIES:
        main_cat_data = release_log.get(main_cat, ({}, {}))
        main_cat_lines[:] = ["== %s ==" % main_cat]
        for data in main_cat_data:
            entries = data.get(None, [])
            if entries:
                main_cat_lines.extend(entries)
                main_cat_lines.append("")
        if len(main_cat_lines) == 1:
            main_cat_lines.append("")
        for sub_cat in sub_cats:
            sub_cat_lines[:] = ["=== %s ===" % sub_cat]
            for data in main_cat_data:
                entries = data.get(sub_cat, [])
                if entries:
                    sub_cat_lines.extend(entries)
                    sub_cat_lines.append("")
            if len(sub_cat_lines) > 2:
                main_cat_lines += sub_cat_lines
        if len(main_cat_lines) > 2:
            lines += main_cat_lines

    if None in release_log:
        main_cat_data = release_log.get(None, ({}, {}))
        main_cat_lines[:] = ["== %s ==\n\n" % "UNSORTED"]
        for data in main_cat_data:
            entries = data.get(None, [])
            if entries:
                main_cat_lines.extend(entries)
                main_cat_lines.append("")
        if len(main_cat_lines) > 2:
            lines += main_cat_lines

    with open(path, 'w') as f:
        f.write(release_log["__HEADER__"])

        count = release_log["__COUNT__"]
        f.write("%s\n" % IGNORE_START_LINE)
        f.write("Total fixed bugs: %d (%d from tracker, %d reported/found by other ways).\n\n"
                "" % (sum(count), count[0], count[1]))
        f.write("%s\n%s\n\n" % ("{{Note|Note|Before RC1 (i.e. during regular development of next version in main "
                                "branch), only fixes of issues which already existed in previous official releases are "
                                "listed here. Fixes for regressions introduced since last release, or for new "
                                "features, are '''not''' listed here.<br/>For following RCs and final release, "
                                "'''all''' backported fixes are listed.}}", IGNORE_END_LINE))

        f.write("\n".join(lines))
        f.write("\n")

        f.write("%s\n\n<hr/>\n\n" % IGNORE_START_LINE)
        for rst in rstate_list:
            entries = release_log["__RSTATES__"].get(rst, [])
            if entries:
                f.write("== %s ==\n" % rst)
                f.write("For %s, %d bugs were fixed:\n\n" % (rst, len(entries)))
                f.write("\n".join(entries))
                f.write("\n\n")
        f.write("%s\n" % IGNORE_END_LINE)


def argparse_create():
    import argparse
    global __doc__

    # When --help or no args are given, print this help
    usage_text = __doc__

    epilog = "This script is typically used to help write release notes"

    parser = argparse.ArgumentParser(description=usage_text, epilog=epilog,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument(
        "--source", dest="source_dir",
        metavar='PATH', required=True,
        help="Path to git repository")
    parser.add_argument(
        "--range", dest="range_sha1",
                        metavar='SHA1_RANGE', required=False,
                        help="Range to use, eg: 169c95b8..HEAD")
    parser.add_argument(
        "--author", dest="author",
        metavar='AUTHOR', type=str, required=False,
        help=("Author(s) to filter commits ("))
    parser.add_argument(
        "--filter", dest="filter_type",
        metavar='FILTER', type=str, required=False,
        help=("Method to filter commits in ['BUGFIX', 'NOISE']"))
    parser.add_argument(
        "--filter-exclude-sha1", dest="filter_exclude_sha1_list",
        default=[], required=False, type=lambda s: s.split(","),
        help=("Coma-separated list of commits to ignore/skip"))
    parser.add_argument(
        "--filter-exclude-sha1-fromfiles", dest="filter_exclude_sha1_filepaths",
        default="", required=False, nargs='*',
        help=("One or more text files storing list of commits to ignore/skip"))
    parser.add_argument(
        "--filter-exclude-fromreleaselogs", dest="filter_exclude_releaselogs",
        default="", required=False, nargs='*',
        help=("One or more text files storing release logs, to ignore/skip their entries "
              "(based on message comparison, not commit sha1)"))
    parser.add_argument(
        "--accept-log", dest="accept_log",
        default=False, action='store_true', required=False,
        help=("Also output more complete info about accepted commits (summary, author...)"))
    parser.add_argument(
        "--accept-pretty", dest="accept_pretty",
        default=False, action='store_true', required=False,
        help=("Also output pretty-printed accepted commits (nearly ready for WIKI release notes)"))
    parser.add_argument(
        "--accept-releaselog", dest="accept_releaselog",
        default=False, action='store_true', required=False,
        help=("Also output accepted commits as a wiki release log page (adds sorting by categories)"))
    parser.add_argument(
        "--blender-rev", dest="blender_rev",
        default=None, required=False,
        help=("Blender revision (only used to generate release notes page)"))
    parser.add_argument(
        "--blender-rstate", dest="blender_rstate",
        default="alpha", required=False,
        help=("Blender release state (like alpha, beta, rc1, final, corr_a, corr_b, etc.), "
              "each revision will be tagged by given one"))
    parser.add_argument(
        "--blender-rstate-list", dest="blender_rstate_list",
        default="", required=False, type=lambda s: s.split(","),
        help=("Blender release state(s) to additionally list in their own sections "
              "(e.g. pass 'RC2' to list fixes between RC1 and RC2, ie tagged as RC2, etc.)"))

    return parser


def main():
    # ----------
    # Parse Args

    args = argparse_create().parse_args()

    for path in args.filter_exclude_sha1_filepaths:
        if os.path.exists(path):
            with open(path, 'r') as f:
                args.filter_exclude_sha1_list += [sha1 for l in f for sha1 in l.split()]
    args.filter_exclude_sha1_list = {sha1.encode() for sha1 in args.filter_exclude_sha1_list}

    messages = set()
    for path in args.filter_exclude_releaselogs:
        messages |= release_log_extract_messages(path)
    args.filter_exclude_releaselogs = messages

    from git_log import GitCommit, GitCommitIter

    # --------------
    # Filter Commits

    def match(c):
        # filter_type
        if not args.filter_type:
            pass
        elif args.filter_type == 'BUGFIX':
            first_line = c.body.split("\n\n")[0].strip(" :.;-\n").replace("\n", " ")
            assert len(first_line)
            if any(w for w in first_line.split() if w.lower().startswith(("fix", "bugfix", "bug-fix"))):
                pass
            else:
                return False
        elif args.filter_type == 'NOISE':
            first_line = c.body.strip().split("\n")[0]
            assert len(first_line)
            if any(w for w in first_line.split() if w.lower().startswith("cleanup")):
                pass
            else:
                return False
        else:
            raise Exception("Filter type %r isn't known" % args.filter_type)

        # author
        if not args.author:
            pass
        elif args.author != c.author:
            return False

        # commits to exclude
        if c.sha1 in args.filter_exclude_sha1_list:
            return False

        # exclude by commit message (because cherry-pick totally breaks relations with original commit...)
        if args.filter_exclude_releaselogs:
            if gen_commit_message_pretty(c) in args.filter_exclude_releaselogs:
                return False

        return True

    if args.accept_releaselog:
        blender_rev = args.blender_rev or "<UNKNOWN>"
        commits = tuple(GitCommitIter(args.source_dir, args.range_sha1))
        release_log = release_log_init(ACCEPT_RELEASELOG_FILE, args.source_dir, blender_rev,
                                       commits[-1].sha1.decode(), commits[0].sha1.decode(),
                                       args.blender_rstate, args.blender_rstate_list)
        commits = [c for c in commits if match(c)]
    else:
        commits = [c for c in GitCommitIter(args.source_dir, args.range_sha1) if match(c)]

    # oldest first
    commits.reverse()

    tot_accept = 0
    tot_reject = 0

    def exit_message():
        print("  Written",
              colorize(ACCEPT_FILE, color='green'), "(%d)" % tot_accept,
              colorize(ACCEPT_LOG_FILE, color='yellow'), "(%d)" % tot_accept,
              colorize(ACCEPT_PRETTY_FILE, color='blue'), "(%d)" % tot_accept,
              colorize(REJECT_FILE, color='red'), "(%d)" % tot_reject,
              )

    def get_cat(ch, max_idx):
        cat = -1
        try:
            cat = int(ch)
        except:
            pass
        if 0 <= cat < max_idx:
            return cat
        print("Invalid input %r" % ch)
        return None

    for i, c in enumerate(commits):
        if os.name == "posix":
            # Also clears scroll-back.
            os.system("tput reset")
        else:
            print('\x1b[2J')  # clear

        sha1 = c.sha1

        # diff may scroll off the screen, that's OK
        os.system("git --git-dir %s show %s --format=%%n" % (c._git_dir, sha1.decode('ascii')))
        print("")
        print_commit(c)
        sys.stdout.flush()

        accept = False
        while True:
            print("Space=" + colorize("Accept", 'green'),
                  "Enter=" + colorize("Skip", 'red'),
                  "Ctrl+C or X=" + colorize("Exit", color='white'),
                  "[%d of %d]" % (i + 1, len(commits)),
                  "(+%d | -%d)" % (tot_accept, tot_reject),
                  )
            ch = getch()

            if ch == b'\x03' or ch == b'x':
                # Ctrl+C
                exit_message()
                print("Goodbye! (%s)" % c.sha1.decode())
                return False
            elif ch == b' ':
                log_filepath = ACCEPT_FILE
                log_filepath_log = ACCEPT_LOG_FILE
                log_filepath_pretty = ACCEPT_PRETTY_FILE
                tot_accept += 1

                if args.accept_releaselog:  # Enter sub-loop for category selection.
                    done_main = True
                    c1 = c2 = None
                    while True:
                        if c1 is None:
                            print("Select main category (V=View all categories, M=Commit message): \n\t%s"
                                  "" % " | ".join("[%d] %s" % (i, cat[0]) for i, cat in enumerate(BUGFIX_CATEGORIES)))
                        else:
                            main_cat = BUGFIX_CATEGORIES[c1][0]
                            sub_cats = BUGFIX_CATEGORIES[c1][1]
                            if not sub_cats:
                                break
                            print("[%d] %s: Select sub category "
                                  "(V=View all categories, M=Commit message, Enter=No sub-categories, "
                                  "Backspace=Select other main category): \n\t%s"
                                  "" % (c1, main_cat,
                                        " | ".join("[%d] %s" % (i, cat) for i, cat in enumerate(sub_cats))))

                        ch = getch()

                        if ch == b'\x7f':  # backspace
                            done_main = False
                            break
                        elif ch == b'\x03' or ch == b'x':
                            # Ctrl+C
                            exit_message()
                            print("Goodbye! (%s)" % c.sha1.decode())
                            return
                        elif ch == b'v':
                            print_categories_tree()
                            print("")
                        elif ch == b'm':
                            print_commit(c)
                            print("")
                        elif c1 is None:
                            c1 = get_cat(ch, len(BUGFIX_CATEGORIES))
                        elif c2 is None:
                            if ch == b'\r':
                                break
                            elif ch == b'\x7f':  # backspace
                                c1 = None
                                continue
                            c2 = get_cat(ch, len(BUGFIX_CATEGORIES[c1][1]))
                            if c2 is not None:
                                break
                        else:
                            print("BUG! this should not happen!")

                    if done_main is False:
                        # Go back to main loop, this commit is no more accepted nor rejected.
                        tot_accept -= 1
                        continue

                    write_release_log(ACCEPT_RELEASELOG_FILE, release_log, c, (c1, c2),
                                      args.blender_rstate, args.blender_rstate_list)
                break
            elif ch == b'\r':
                log_filepath = REJECT_FILE
                log_filepath_log = None
                log_filepath_pretty = None
                tot_reject += 1
                break
            else:
                print("Invalid input %r" % ch)

        with open(log_filepath, 'ab') as f:
            f.write(sha1 + b'\n')

        if args.accept_pretty and log_filepath_pretty:
            with open(log_filepath_pretty, 'a') as f:
                f.write(gen_commit_pretty(c, rstate=args.blender_rstate) + "\n")

        if args.accept_log and log_filepath_log:
            with open(log_filepath_log, 'a') as f:
                f.write(gen_commit_log(c) + "\n")

    exit_message()


if __name__ == "__main__":
    main()
