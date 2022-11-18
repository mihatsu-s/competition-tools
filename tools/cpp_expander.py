from typing import TextIO, Optional, Pattern, List, Iterable, Set, Union
from pathlib import Path
import os
import re
import sys
from argparse import ArgumentParser
from hashlib import sha256


class CppLineReader:
    """ Convert plain C++ code to syntactic lines """

    def __init__(self, source: Iterable[str]):
        """ `source` must be iterated line by line (e.g. `io.StringIO` object) """
        self.source = source

    def __iter__(self):
        yield from self()

    class LineInfo:
        def __init__(self, raw="", code=""):
            self.raw = raw
            self.code = code

    _re_linebreak = re.compile(r'^\\\s*$')

    def __call__(self):
        in_string = False
        in_block_comment = False
        lineinfo = CppLineReader.LineInfo()
        for line in self.source:
            skipping = 0
            continue_to_next_line = False
            for p in range(len(line)):
                if skipping > 0:
                    skipping -= 1
                elif in_string:
                    if line[p:p+2] == r'\"':
                        skipping = 1
                        lineinfo.code += line[p:p+2]
                    elif line[p] == '"':
                        in_string = False
                        lineinfo.code += line[p]
                    else:
                        lineinfo.code += line[p]
                elif in_block_comment:
                    if line[p:p+2] == "*/":
                        skipping = 1
                        in_block_comment = False
                else:
                    if line[p] == '"':
                        in_string = True
                        lineinfo.code += line[p]
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
                            lineinfo.code += line[p]

            lineinfo.raw += line
            if not in_block_comment and not continue_to_next_line:
                yield lineinfo
                lineinfo = CppLineReader.LineInfo()

        if lineinfo.raw != "":
            yield lineinfo


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
            quote: bool
            if arg[0] == '"' and arg[-1] == '"':
                quote = True
            elif arg[0] == '<' and arg[-1] == '>':
                quote = False
            else:
                raise ValueError("cannot parse '#include {}'".format(arg))
            return CppDirective.Include(arg[1:-1], quote)

        def __str__(self):
            return "#include {}{}{}".format(
                '"' if self.quote else '<',
                self.target,
                '"' if self.quote else '>'
            )

    class Base:  # label
        pass

    class Define(Base):
        def __init__(self, identifier: str, args: List[str], code: str):
            self.identifier = identifier
            self.args = args
            self.code = code

        _re_parse = re.compile(r'^(\w+)(\([^\)]*\)|)\s*(.*)$')

        @staticmethod
        def parse(arg: str):
            match = CppDirective.Define._re_parse.match(arg)
            if match is None:
                raise ValueError("cannot parse '#define {}'".format(arg))
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

    class Undef(Base):
        def __init__(self, identifier: str):
            self.identifier = identifier

        def __str__(self):
            return "#undef " + self.identifier

    class Pragma(Base):
        def __init__(self, command: str):
            self.command = command

        def __str__(self):
            return "#pragma " + self.command

    class IfLike(Base):  # label
        pass

    class If(IfLike):
        def __init__(self, expression: str):
            self.expression = expression

        def __str__(self):
            return "#if " + self.expression

    class Ifdef(IfLike):
        def __init__(self, identifier: str):
            self.identifier = identifier

        def __str__(self):
            return "#ifdef " + self.identifier

    class Ifndef(IfLike):
        def __init__(self, identifier: str):
            self.identifier = identifier

        def __str__(self):
            return "#ifndef " + self.identifier

    class Elif(Base):
        def __init__(self, expression: str):
            self.expression = expression

        def __str__(self):
            return "#undef " + self.expression

    class Else(Base):
        def __str__(self):
            return "#else"

    class Endif(Base):
        def __str__(self):
            return "#endif"


class CppDirectiveTranslator:
    """ `#elif` -> `#else` + `#if` and so on """

    def __init__(self, codelines: Iterable[CppLineReader.LineInfo], path: Optional[Path] = None):
        self.codelines = codelines
        self.path = path

        self._ifblocks: List[CppDirectiveTranslator.IfBlock] = []
        self._include_guard_emulation = False

    def __iter__(self):
        yield from self()

    class LineInfo:
        def __init__(self, text: CppLineReader.LineInfo, directive: Optional[CppDirective.Base] = None):
            self.text = text
            self.directive = directive

    class IfBlock:
        def __init__(self):
            self.endif_duplication = 0

    @staticmethod
    def _directive_line(directive: CppDirective.Base):
        return CppDirectiveTranslator.LineInfo(
            text=CppLineReader.LineInfo(
                raw=str(directive) + "\n",
                code=str(directive)
            ),
            directive=directive
        )

    _re_ifdef = re.compile(r'^[\(\s]*(!|)[\(\s]*defined\s*\(\s*([^\s\)]+)[\s\)]*$')

    def __call__(self):
        for line in self.codelines:
            res = CppDirectiveTranslator.LineInfo(line, CppDirective.parse(line.code))
            if res.directive is None:
                yield res
                continue

            #  #elif -> #else + #if
            if isinstance(res.directive, CppDirective.IfLike):
                self._ifblocks.append(CppDirectiveTranslator.IfBlock())

            elif isinstance(res.directive, CppDirective.Elif):
                if len(self._ifblocks) == 0:
                    raise ValueError("#elif without #if")
                yield CppDirectiveTranslator._directive_line(CppDirective.Else())
                res = CppDirectiveTranslator._directive_line(CppDirective.If(res.directive.expression))
                self._ifblocks[-1].endif_duplication += 1

            elif isinstance(res.directive, CppDirective.Else):
                if len(self._ifblocks) == 0:
                    raise ValueError("#else without #if")

            elif isinstance(res.directive, CppDirective.Endif):
                if len(self._ifblocks) == 0:
                    raise ValueError("#endif without #if")
                for _ in range(self._ifblocks[-1].endif_duplication):
                    yield CppDirectiveTranslator._directive_line(CppDirective.Endif())
                self._ifblocks.pop()

            #  #if defined -> #ifdef
            if isinstance(res.directive, CppDirective.If):
                match_ifdef = CppDirectiveTranslator._re_ifdef.match(res.directive.expression)
                if match_ifdef is not None:
                    if match_ifdef[1] == "!":
                        res = CppDirectiveTranslator._directive_line(CppDirective.Ifndef(match_ifdef[2]))
                    else:
                        res = CppDirectiveTranslator._directive_line(CppDirective.Ifdef(match_ifdef[2]))

            #  #pragma once -> (include guard by macro)
            if isinstance(res.directive, CppDirective.Pragma) and res.directive.command == "once":
                if len(self._ifblocks) == 0:  # not in #if block
                    if not self._include_guard_emulation and self.path:
                        macro_name = "_CPPEXPANDER_" + sha256(str(self.path).encode()).hexdigest()[:16].upper()
                        yield CppDirectiveTranslator._directive_line(CppDirective.Ifndef(macro_name))
                        res = CppDirectiveTranslator._directive_line(CppDirective.Define(macro_name, [], ""))
                        self._include_guard_emulation = True

            yield res

        if self._include_guard_emulation:
            yield CppDirectiveTranslator._directive_line(CppDirective.Endif())


class MacroContext:
    def __init__(self,
                 _defined: Optional[Set[str]] = None,
                 _not_defined: Optional[Set[str]] = None):
        self._defined: Set[str] = _defined or set()
        self._not_defined: Set[str] = _not_defined or set()

    def copy(self):
        return MacroContext(self._defined.copy(), self._not_defined.copy())

    def define(self, macro_name: str):
        self._defined.add(macro_name)
        self._not_defined.discard(macro_name)

    def undef(self, macro_name: str):
        self._not_defined.add(macro_name)
        self._defined.discard(macro_name)

    def is_defined(self, macro_name: str) -> Optional[bool]:
        if macro_name in self._defined:
            return True
        elif macro_name in self._not_defined:
            return False
        else:
            return None

    def merge(self, o: "MacroContext"):
        return MacroContext(
            self._defined & o._defined,
            self._not_defined & o._not_defined
        )


class CppExpander:
    def __init__(self,
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

    class IfBlock:
        def __init__(self, directive: CppDirective.IfLike):
            self.directive = directive
            self.current = True
            self.no_output = False

    class UndeterminedIfBlock(IfBlock):
        def __init__(self, directive: CppDirective.IfLike, context: MacroContext):
            super().__init__(directive)
            self.contexts = [context.copy(), context]  # (false block context, true block context)
            if isinstance(directive, CppDirective.Ifdef):
                self.contexts[True].define(directive.identifier)
                self.contexts[False].undef(directive.identifier)
            elif isinstance(directive, CppDirective.Ifndef):
                self.contexts[True].undef(directive.identifier)
                self.contexts[False].define(directive.identifier)

    class DeterminedIfBlock(IfBlock):
        def __init__(self, directive: CppDirective.IfLike, determined: bool):
            super().__init__(directive)
            self.determined = determined
            self.no_output = True

    def is_determined(self, directive: CppDirective.IfLike, context: Optional[MacroContext] = None) -> Optional[bool]:
        """ check if given #if block can be determined in the context """
        if context is None:
            context = self.context

        if isinstance(directive, CppDirective.Ifdef) and context.is_defined(directive.identifier) is not None:
            return context.is_defined(directive.identifier)
        elif isinstance(directive, CppDirective.Ifndef) and context.is_defined(directive.identifier) is not None:
            return not context.is_defined(directive.identifier)
        else:
            return None

    def __call__(self):
        self.context = MacroContext()
        self.ifblocks: List[CppExpander.IfBlock] = []
        self.in_unreachable_block = False
        return self.expand(self.source_path)

    def expand(self, source_path: Path):
        with open(source_path, "r", encoding="utf-8") as source:
            directive_translator = CppDirectiveTranslator(CppLineReader(source), source_path)
            for line in directive_translator():

                no_output = False

                if isinstance(line.directive, CppDirective.IfLike):
                    if self.in_unreachable_block:
                        self.ifblocks.append(CppExpander.IfBlock(line.directive))  # no operation
                    else:
                        determined = self.is_determined(line.directive)
                        if determined is not None:
                            self.ifblocks.append(CppExpander.DeterminedIfBlock(line.directive, determined))
                            self.in_unreachable_block = (determined == False)
                            no_output = True
                        else:
                            ifblock_undet = CppExpander.UndeterminedIfBlock(line.directive, self.context)
                            self.ifblocks.append(ifblock_undet)
                            self.context = ifblock_undet.contexts[True]

                elif isinstance(line.directive, CppDirective.Else):
                    ifblock = self.ifblocks[-1]
                    ifblock.current = False
                    if isinstance(ifblock, CppExpander.UndeterminedIfBlock):
                        self.context = ifblock.contexts[False]
                    elif isinstance(ifblock, CppExpander.DeterminedIfBlock):
                        self.in_unreachable_block = (determined == True)

                    if ifblock.no_output:
                        no_output = True

                elif isinstance(line.directive, CppDirective.Endif):
                    ifblock = self.ifblocks.pop()

                    if isinstance(ifblock, CppExpander.UndeterminedIfBlock):
                        #  #ifndefのtrueブロックで分岐条件のマクロが定義され，かつfalseブロックが存在しない場合，当該マクロをインクルードガードとして取り扱う．
                        if isinstance(ifblock.directive, CppDirective.Ifndef) \
                                and ifblock.contexts[True].is_defined(ifblock.directive.identifier) \
                                and ifblock.current == True:
                            # インクルードガード終了後は特例としてtrueブロックのコンテキストを引き継ぐ
                            # （したがって，このtrueブロックが有効にならないような環境では展開されたコードを使用できない）
                            self.context = ifblock.contexts[True].copy()
                        else:
                            self.context = ifblock.contexts[True].merge(ifblock.contexts[False])

                        for parent_ifblock in reversed(self.ifblocks):
                            if (isinstance(parent_ifblock, CppExpander.UndeterminedIfBlock)):
                                parent_ifblock.contexts[parent_ifblock.current] = self.context

                    elif isinstance(ifblock, CppExpander.DeterminedIfBlock):
                        self.in_unreachable_block = False  # because DeterminedIfBlock does not appear in unreachable block

                    if ifblock.no_output:
                        no_output = True

                if self.in_unreachable_block:
                    continue

                if isinstance(line.directive, CppDirective.Define):
                    self.context.define(line.directive.identifier)

                elif isinstance(line.directive, CppDirective.Undef):
                    self.context.undef(line.directive.identifier)

                elif isinstance(line.directive, CppDirective.Include):
                    if not (self.exclude_pattern and self.exclude_pattern.search(line.directive.target)):
                        target = self.resolve_include_path(line.directive.target, source_path if line.directive.quote else None)
                        if target is not None:
                            self.expand(target)
                            continue

                if not no_output:
                    self.outfile.write(line.text.raw)


def main():
    parser = ArgumentParser(description="Expand #include in C++ source file.")
    parser.add_argument("file", help="C++ source file")
    parser.add_argument("-o", "--out", help="output file (default: stdout)")
    parser.add_argument("-e", "--exclude", help="prevent specific pattern from being expanded (by regular expression)")
    args = parser.parse_args()

    if args.out is None:
        CppExpander(args.file, sys.stdout, args.exclude)()
    else:
        with open(args.out, "w", encoding="utf-8") as outfile:
            CppExpander(args.file, outfile, args.exclude)()


if __name__ == "__main__":
    main()
