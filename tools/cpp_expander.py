from typing import TextIO, Optional, Pattern, List, Iterable
from pathlib import Path
import os
import re
import sys
from argparse import ArgumentParser
from hashlib import sha256


class CppLineReader:
    def __init__(self, source: Iterable[str]):
        self.source = source

    def __iter__(self):
        yield from self()

    _re_linebreak = re.compile(r'^\\\s*$')

    def __call__(self):
        in_string = False
        in_block_comment = False
        code = ""
        for line in self.source:
            skipping = 0
            continue_to_next_line = False
            for p in range(len(line)):
                if skipping > 0:
                    skipping -= 1
                elif in_string:
                    if line[p:p+2] == r'\"':
                        skipping = 1
                        code += line[p:p+2]
                    elif line[p] == '"':
                        in_string = False
                        code += line[p]
                    else:
                        code += line[p]
                elif in_block_comment:
                    if line[p:p+2] == "*/":
                        skipping = 1
                        in_block_comment = False
                else:
                    if line[p] == '"':
                        in_string = True
                        code += line[p]
                    elif line[p:p+2] == "/*":
                        skipping = 1
                        in_block_comment = True
                    elif line[p:p+2] == "//":
                        break
                    elif CppLineReader._re_linebreak.match(line[p:]):
                        continue_to_next_line = True
                        break
                    else:
                        if not line[p] in "\r\n":
                            code += line[p]

            if not in_block_comment and not continue_to_next_line:
                yield code
                code = ""

        if code != "":
            yield code


class CppDirective:
    @staticmethod
    def _find_str(s: str, sub: str, start: Optional[int] = None, end: Optional[int] = None):
        p = s.find(sub, start, end)
        return p if p >= 0 else len(s)

    @staticmethod
    def _remove_space(s: str):
        return re.sub(r'\s', "", s)

    _re_directive = re.compile(r'^\s*#\s*(\w+)(?:\s*(.*?)|(["<].*?))\s*$')

    @staticmethod
    def parse(codeline: str):
        match = CppDirective._re_directive.match(codeline)
        if match is None:
            return None

        command = match[1]
        arg = match[2]
        if command == "include":
            return CppDirective.Include.parse(arg)
        elif command == "define":
            return CppDirective.Define.parse(arg)
        elif command == "pragma":
            return CppDirective.Pragma(arg)
        elif command == "if":
            return CppDirective.If(arg)
        elif command == "elif":
            return CppDirective.Elif(arg)
        elif command == "else":
            return CppDirective.Else()
        elif command == "endif":
            return CppDirective.Endif()

        first_token = (re.search(r'\S*', arg) or [""])[0]
        if command == "undef":
            return CppDirective.Undef(first_token)
        elif command == "ifdef":
            return CppDirective.Ifdef(first_token)
        elif command == "ifndef":
            return CppDirective.Ifndef(first_token)

        return None

    class Include:
        def __init__(self, target: str, quote: bool = False):
            self.target = target
            self.quote = quote

        @staticmethod
        def parse(arg: str):
            return CppDirective.Include(
                target=arg[1:-1],
                quote=arg[0] == '"'
            )

        def __str__(self):
            return "#include {}{}{}".format(
                '"' if self.quote else '<',
                self.target,
                '"' if self.quote else '>'
            )

    class Define:
        def __init__(self, identifier: str, args: List[str], code: str):
            self.identifier = identifier
            self.args = args
            self.code = code

        _re_parse = re.compile(r'^(\w+)(\([^\)]*\)|)\s*(.*)$')

        @staticmethod
        def parse(arg: str):
            match = CppDirective.Define._re_parse.match(arg)
            if match is None:
                raise ValueError('cannot parse "{}"'.format(str))
            return CppDirective.Define(
                identifier=match[1],
                args=CppDirective._remove_space(match[2][1:-1]).split(",") if match[2] else [],
                code=match[3]
            )

        def __str__(self):
            return "#define {}{}{}".format(
                self.identifier,
                "(" + ",".join(self.args) + ")" if self.args else "",
                " " + self.code if self.code else ""
            )

    class Undef:
        def __init__(self, identifier: str):
            self.identifier = identifier

        def __str__(self):
            return "#undef " + self.identifier

    class Pragma:
        def __init__(self, command: str):
            self.command = command

        def __str__(self):
            return "#pragma " + self.command

    class If:
        def __init__(self, expression: str):
            self.expression = expression

        def __str__(self):
            return "#if " + self.expression

    class Ifdef:
        def __init__(self, identifier: str):
            self.identifier = identifier

        def __str__(self):
            return "#ifdef " + self.identifier

    class Ifndef:
        def __init__(self, identifier: str):
            self.identifier = identifier

        def __str__(self):
            return "#ifndef " + self.identifier

    class Elif:
        def __init__(self, expression: str):
            self.expression = expression

        def __str__(self):
            return "#undef " + self.expression

    class Else:
        def __str__(self):
            return "#else"

    class Endif:
        def __str__(self):
            return "#endif"


class CppDirectiveTranslator:
    """ #elif -> #else + #if and so on """

    def __init__(self, codelines: Iterable[str], path: Optional[Path] = None):
        self.codelines = codelines
        self.path = path

        self._endif_duplication_count: List[int] = []
        self._include_guard_emulation = False

    def __iter__(self):
        yield from self()

    _re_ifdef = re.compile(r'^[\(\s]*(!|)[\(\s]*defined\s*\(\s*([^\s\)]+)[\s\)]*$')

    def __call__(self):
        for line in self.codelines:
            directive = CppDirective.parse(line)
            if directive is None:
                yield line
                continue

            #  #elif -> #else + #if
            if isinstance(directive, CppDirective.Elif):
                yield CppDirective.Else()
                directive = CppDirective.If(directive.expression)
                self._endif_duplication_count[-1] += 1
            elif isinstance(directive, (CppDirective.If, CppDirective.Ifdef, CppDirective.Ifndef)):
                self._endif_duplication_count.append(0)
            elif isinstance(directive, CppDirective.Endif):
                for _ in range(self._endif_duplication_count[-1]):
                    yield CppDirective.Endif()
                self._endif_duplication_count.pop()

            #  #if defined -> #ifdef
            if isinstance(directive, CppDirective.If):
                match_ifdef = CppDirectiveTranslator._re_ifdef.match(directive.expression)
                if match_ifdef is not None:
                    if match_ifdef[1] == "!":
                        directive = CppDirective.Ifndef(match_ifdef[2])
                    else:
                        directive = CppDirective.Ifdef(match_ifdef[2])

            #  #pragma once -> (include guard by macro)
            if isinstance(directive, CppDirective.Pragma) and directive.command == "once":
                if len(self._endif_duplication_count) == 0:  # not in #if block
                    if not self._include_guard_emulation and self.path:
                        macro_name = "_CPPEXPANDER_" + sha256(str(self.path).encode()).hexdigest()[:16]
                        yield CppDirective.Ifndef(macro_name)
                        directive = CppDirective.Define(macro_name, [], "")
                        self._include_guard_emulation = True

            yield directive
        
        if self._include_guard_emulation:
            yield CppDirective.Endif()


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
            for line in CppDirectiveTranslator(CppLineReader(source), source_path):

                if isinstance(line, CppDirective.Include):
                    target = self.resolve_include_path(line.target, source_path if line.quote else None)
                    if target is not None:
                        self.expand(target)
                        continue

                self.outfile.write(str(line))
                self.outfile.write("\n")


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
