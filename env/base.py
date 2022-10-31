from abc import ABCMeta, abstractmethod
from typing import List
import os
from pathlib import Path
import re
import subprocess


class BaseEnv(metaclass=ABCMeta):

    # == Override the following 6 methods ==

    @abstractmethod
    def source_filename(self) -> str:
        raise NotImplementedError

    def source_template(self) -> str:
        return ""

    @abstractmethod
    def test_dependencies(self) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    def test_command(self) -> str:
        raise NotImplementedError

    def submitted_file(self) -> str:
        return self.source_filename()

    def additional_make_rules(self) -> str:
        return ""

    # ======================================

    def __init__(self, problem_name: str, problem_url: str):
        self.problem_name = problem_name
        self.problem_url = problem_url or ""

    def on_windows(self) -> bool:
        return os.name == "nt"

    def python_command(self) -> str:
        return "py" if self.on_windows() else "python3"

    def can_submit_by_oj(self) -> bool:
        return re.search(r"(?:atcoder\.jp|codeforces\.com|yukicoder\.me|hackerrank\.com|toph\.co)/", self.problem_url) is not None

    def submission_command(self) -> str:
        if self.can_submit_by_oj():
            return 'oj submit -y "{url}" "{file}"'.format(
                url=self.problem_url,
                file=self.submitted_file()
            )
        else:
            return '{cat} "{file}" | {python} -m pyperclip --copy && echo "Copied {file} to clipboard."'.format(
                cat="type" if self.on_windows() else "cat",
                python=self.python_command(),
                file=self.submitted_file()
            )

    def opening_command(self) -> str:
        if self.problem_url:
            return "{python} -m webbrowser {url} && code {file}".format(
                python=self.python_command(),
                url=self.problem_url,
                file=self.source_filename()
            )
        else:
            return "code {}".format(self.source_filename())

    def generate_makefile(self) -> str:
        return """
_open:
\t{open}
_test: {test_dep}
\toj test -c "{test}" $(TEST_ARGS)
_exec: {test_dep}
\t{test}
_exec_input: {test_dep}
\t{cat} $(EXEC_INPUT) | {test}
_submit: {submitted_file} _test
\t{submit}
_submit_force: {submitted_file}
\t{submit}
{additional}
""".format(
            open=self.opening_command(),
            test_dep=" ".join(self.test_dependencies()),
            test=self.test_command().replace('"', r'"\""'),
            cat="type" if self.on_windows() else "cat",
            submitted_file=self.submitted_file(),
            submit=self.submission_command(),
            additional=self.additional_make_rules()
        )

    def prepare(self, directory=None, opening=False, memo=""):
        if directory:
            if not Path(directory).is_dir():
                os.mkdir(directory)
            os.chdir(directory)

        with open("Makefile", "w") as f:
            f.write(self.generate_makefile())
        with open(self.source_filename(), "w") as f:
            f.write(self.source_template())
        if self.problem_url:
            subprocess.run(["oj", "download", self.problem_url])
        with open(".problem", "w") as f:
            f.write(memo)
        
        if opening:
            subprocess.run(["make", "_open"])
        
        if directory:
            os.chdir("..")
