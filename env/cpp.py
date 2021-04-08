from .base import BaseEnv
from pathlib import Path


class CppEnv(BaseEnv):

    def source_filename(self):
        return self.problem_name + ".cpp"

    def source_template(self):
        return "#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n}"

    def exectable_filename(self):
        return "a.exe" if self.on_windows() else "a"

    def test_dependencies(self):
        return [self.exectable_filename()]

    def test_command(self):
        return "./" + self.exectable_filename()

    def submitted_file(self):
        return "expanded.cpp"

    def on_atcoder(self) -> bool:
        return "atcoder.jp/" in self.problem_url

    def additional_make_rules(self):
        return """
{exe}: {src}
\tg++ {src} -Wall -std=c++17 -DDEBUG -D_GLIBCXX_DEBUG -D_GLIBCXX_DEBUG_PEDANTIC -o {exe}
{expanded}: {src}
\t{python} {expander} {src} {expander_option} -o {expanded}
""".format(
            src=self.source_filename(),
            exe=self.exectable_filename(),
            expanded=self.submitted_file(),
            python=self.python_command(),
            expander=(Path(__file__) / "../../tools/cpp_expander.py").resolve(),
            expander_option="-e \"^(?:atcoder|boost)/\"" if self.on_atcoder() else ""
        )
