from typing import TextIO, Optional, Pattern, List
from pathlib import Path
import os
import re
import sys
from argparse import ArgumentParser


class CppLineReader:
    class LineInfo:
        def __init__(self, raw: str = "", code: str = ""):
            self.raw = raw
            self.code = code

    @staticmethod
    def read(source: TextIO):
        in_string = False
        in_block_comment = False
        info = CppLineReader.LineInfo()
        for line in source:
            skipping = 0
            continue_to_next_line = False
            for p in range(len(line)):
                if skipping > 0:
                    skipping -= 1
                elif in_string:
                    if line[p:p+2] == r'\"':
                        skipping = 1
                        info.code += line[p:p+2]
                    elif line[p] == '"':
                        in_string = False
                        info.code += line[p]
                    else:
                        info.code += line[p]
                elif in_block_comment:
                    if line[p:p+2] == "*/":
                        skipping = 1
                        in_block_comment = False
                else:
                    if line[p] == '"':
                        in_string = True
                        info.code += line[p]
                    elif line[p:p+2] == "/*":
                        skipping = 1
                        in_block_comment = True
                    elif line[p:p+2] == "//":
                        info.code += "\n"
                        break
                    elif line[p:] == "\\\n" or line[p:] == "\\\r\n":
                        continue_to_next_line = True
                        break
                    else:
                        info.code += line[p]

            info.raw += line
            if not in_block_comment and not continue_to_next_line:
                yield info
                info = CppLineReader.LineInfo()

        if info.raw != "":
            yield info


class CppDirectiveReader:
    re_space = re.compile(r'(?:^\s*|(?<=[\s#])\s*|[\s\r\n]*$)')

    @staticmethod
    def remove_space(codeline: str) -> str:
        return CppDirectiveReader.re_space.sub("", codeline)

    re_include = re.compile(r'^#include\s*(["<])([^">]*)')

    class IncludeDirective:
        def __init__(self, target: str, quote: bool = False):
            self.target = target
            self.quote = quote

    @staticmethod
    def read(codeline: str):
        codeline = CppDirectiveReader.remove_space(codeline)

        match_include = CppDirectiveReader.re_include.search(codeline)
        if match_include is not None:
            return CppDirectiveReader.IncludeDirective(match_include[2], match_include[1] == '"')

        return None


class CppExpander:
    def __init__(
            self,
            source_path: str,
            outfile: TextIO,
            exclude_pattern: Optional[Pattern[str]] = None):

        self.source_path = Path(source_path).resolve()
        self.outfile = outfile
        self.exclude_pattern: Optional[Pattern[str]] = None
        if exclude_pattern is not None:
            self.exclude_pattern = re.compile(exclude_pattern)

    @staticmethod
    def get_cplus_include_path_from_env() -> List[Path]:
        dirs: List[Path] = []
        for path in (os.environ.get("CPLUS_INCLUDE_PATH") or "").split(os.pathsep):
            if path:
                dirs.append(Path(path).resolve())
        return dirs

    def resolve_include_path(self, target: str, basepath: Optional[Path] = None) -> Optional[Path]:
        if basepath is not None:
            while basepath.parent != basepath:
                basepath = basepath.parent
                file = basepath.joinpath(target).resolve()
                if file.is_file():
                    return file

        if not hasattr(self, "include_dirs"):
            self.include_dirs = CppExpander.get_cplus_include_path_from_env()

        for dir in self.include_dirs:
            file = dir.joinpath(target).resolve()
            if file.is_file():
                return file

        return None

    def __call__(self):
        return self.expand(self.source_path)

    def expand(self, source_path: Path):
        with open(source_path, "r") as source:
            for line in CppLineReader.read(source):
                directive = CppDirectiveReader.read(line.code)
                if isinstance(directive, CppDirectiveReader.IncludeDirective):
                    target = self.resolve_include_path(directive.target, source_path if directive.quote else None)
                    if target is not None:
                        self.expand(target)
                        continue
                self.outfile.write(line.raw)


def main():
    parser = ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("-o", "--out", help="output file (default: stdout)")
    parser.add_argument("-e", "--exclude", help="prevent specific pattern from being expanded")
    args = parser.parse_args()

    if args.out is None:
        CppExpander(args.file, sys.stdout, args.exclude)()
    else:
        with open(args.out, "w") as outfile:
            CppExpander(args.file, outfile, args.exclude)()


if __name__ == "__main__":
    main()
