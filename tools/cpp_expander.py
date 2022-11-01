from typing import TextIO, Set, Optional, Union, Pattern
from pathlib import Path
import os
import re
import sys
from argparse import ArgumentParser


cplus_include_paths = []
for path in (os.environ.get("CPLUS_INCLUDE_PATH") or "").split(os.pathsep):
    if path:
        cplus_include_paths.append(Path(path).resolve())


def resolve_include_path(target: str) -> Optional[Path]:
    for base in cplus_include_paths:
        path = base.joinpath(target)
        if path.is_file():
            return path
    return None


re_include1 = re.compile(r'^#include"([^>]*)"$')
re_include2 = re.compile(r'^#include<([^"]*)>$')


def _expand_core(
        source_path: Path,
        parent_files: Set[Path],
        outfile: TextIO,
        exclude_pattern: Optional[Pattern[str]] = None
) -> None:
    # !!!!  "#pragma once" is not supported  !!!!

    if (source_path in parent_files):
        return
    parent_files.add(source_path)

    with open(source_path, "r") as source:
        in_block_comment = False
        for line in source:
            code = ""
            next_skip = False
            in_string = False
            for i in range(len(line)):
                if next_skip:
                    next_skip = False
                elif in_string:
                    code += line[i]
                    if (line[i] == "\""):
                        in_string = False
                elif in_block_comment:
                    if (line[i:i+2] == "*/"):
                        in_block_comment = False
                        next_skip = True
                else:
                    if (line[i:i+2] == "//"):
                        break
                    elif (line[i:i+2] == "/*"):
                        in_block_comment = True
                        next_skip = True
                    elif (line[i] != " " and line[i] != "\t"):
                        code += line[i]
                        if (line[i] == "\""):
                            in_string = True

            match1 = re_include1.match(code)
            include_target: Optional[str] = None
            next_include_path: Optional[Path] = None
            if match1:
                next_include_path = source_path.parent.joinpath(match1[1])
                if not next_include_path.is_file():
                    next_include_path = None
                    include_target = match1[1]
            else:
                match2 = re_include2.match(code)
                if match2:
                    include_target = match2[1]

            if next_include_path is None and include_target:
                if not (exclude_pattern and exclude_pattern.search(include_target) is not None):
                    next_include_path = resolve_include_path(include_target)

            if next_include_path:
                _expand_core(next_include_path, parent_files, outfile, exclude_pattern)
            else:
                outfile.write(line)

    parent_files.discard(source_path)


def expand(
        source_path: str,
        outfile: TextIO,
        exclude_pattern: Optional[Pattern[str]] = None
) -> None:
    _expand_core(Path(source_path).resolve(),
                 set(), outfile, exclude_pattern)


def main():
    parser = ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("-o", "--out", help="output file (default: stdout)")
    parser.add_argument("-e", "--exclude", help="prevent specific pattern from being expanded")
    args = parser.parse_args()

    exclude = None if args.exclude is None else re.compile(args.exclude)
    if args.out is None:
        expand(args.file, sys.stdout, exclude)
    else:
        with open(args.out, "w") as f:
            expand(args.file, f, exclude)


if __name__ == "__main__":
    main()
