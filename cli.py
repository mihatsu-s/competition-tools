from env.cpp import CppEnv as Env
import sys
import subprocess
import os
import re
from pathlib import Path
from typing import List
import json


def is_task_directory(path=".") -> bool:
    return (Path(path) / ".problem").is_file()


def is_contest_directory(path=".") -> bool:
    return (Path(path) / ".contest").is_file()


def get_name_from_url(url: str) -> str:
    return list(filter(lambda s: s != "", url.split("/")))[-1]


_init_wd = os.getcwd()


def set_cd_path(x: str):
    with open(os.path.join(_init_wd, "__cd"), "w", encoding="utf-8") as f:
        f.write(x)


def set_rm_path(x: str, directory=_init_wd):
    with open(os.path.join(directory, "__rm"), "w", encoding="utf-8") as f:
        f.write(x)


def get_oj_testcases() -> List[str]:
    res: List[str] = []
    test_dir = Path("test")
    if (test_dir.is_dir()):
        for f in test_dir.iterdir():
            name = str(f)
            if (re.search(r"\.in$", name)):
                res.append(name)
    res.sort()
    return res


def clean():
    cd_path = ".."
    rm_path = os.getcwd()
    if is_task_directory():
        if is_contest_directory(".."):
            cd_path = os.path.join("..", "..")
            rm_path = str(Path("..").resolve())
    elif not is_contest_directory():
        raise RuntimeError("You are not in competition environment.")

    set_cd_path(cd_path)
    set_rm_path(rm_path, directory=cd_path)


def generate(x: str):
    if re.match(r"^\d+$", x) and int(x) > 0:
        envs: List[Env] = []
        for i in range(int(x)):
            envs.append(Env("", ""))
        i = 1
        while Path("contest" + str(i)).exists():
            i += 1
        generate_contest("contest" + str(i), envs,
                         opening=True, auto_naming=True)
    else:
        sp = subprocess.run(["oj-api", "get-problem", x],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if (sp.returncode == 0):
            name = get_name_from_url(x)
            Env(name, x).prepare(directory=name, opening=True)
            set_cd_path(name)
            return

        sp = subprocess.run(["oj-api", "get-contest", x],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if (sp.returncode == 0):
            data = json.loads(sp.stdout)["result"]["problems"]
            envs: List[Env] = []
            auto_naming = False
            for entry in data:
                url = entry["url"]
                name = ""
                if "context" in entry and "alphabet" in entry["context"]:
                    name = entry["context"]["alphabet"]
                else:
                    auto_naming = True
                envs.append(Env(name, url))
            generate_contest(get_name_from_url(x), envs,
                             opening=True, auto_naming=auto_naming)

        raise RuntimeError("Cannot generate environment for '{}'.".format(x))


def generate_contest(contest_name: str, envs: List[Env], opening=False, auto_naming=False):
    os.mkdir(contest_name)
    os.chdir(contest_name)
    with open(".contest", "w", encoding="utf-8") as f:
        f.write(contest_name)
    if auto_naming:
        for i, env in enumerate(envs):
            env.problem_name = chr(ord("A") + i)
    for i, env in enumerate(envs):
        env.prepare(directory=env.problem_name, opening=(i == 0) and opening,
                    memo=envs[i + 1].problem_name if i + 1 < len(envs) else "")
    set_cd_path(os.path.join(contest_name, envs[0].problem_name))


def submit(problem_name: str, force: bool, *args):
    if (problem_name != ""):
        problem_name = problem_name.upper()
        if (is_task_directory()):
            os.chdir("..")
        try:
            os.chdir(problem_name)
        except Exception:
            raise RuntimeError("Problem '{}' does not exist.".format(problem_name))

    if not is_task_directory():
        raise RuntimeError("You are not in problem directory.")
    
    # do not run "oj test" if test case does not exist
    if len(get_oj_testcases()) == 0:
        force = True

    cmd = ["make", "_submit_force" if force else "_submit"]
    if len(args) > 0:
        cmd.append("TEST_ARGS=" + " ".join(args))
    subprocess.run(cmd)


def test(test_case_index: int, *args):
    if not is_task_directory():
        raise RuntimeError("You are not in problem directory.")

    cmd = ["make"]
    if test_case_index == 0:
        cmd.append("_test")
        if len(args) > 0:
            cmd.append("TEST_ARGS=" + " ".join(args))
    else:
        cmd.append("_exec_input")
        test_files = get_oj_testcases()
        cmd.append("EXEC_INPUT=" + test_files[test_case_index - 1])
    subprocess.run(cmd)


def go_to(problem_name: str, opening: bool = True):
    problem_name = problem_name.upper()

    if (is_task_directory()):
        os.chdir("..")

    try:
        os.chdir(problem_name)
    except Exception:
        raise RuntimeError("Problem '{}' does not exist.".format(problem_name))

    sp_returncode = 0
    if opening:
        sp = subprocess.run(["make", "_open"])
        sp_returncode = sp.returncode

    if (sp_returncode == 0):
        set_cd_path(os.getcwd())


# Submit current problem and go to next problem
def colon(*args):
    if not is_task_directory():
        raise RuntimeError("You are not in problem directory.")
    s = ""
    with open(".problem", encoding="utf-8") as f:
        s = f.readline()  # next problem name
    if len(s):
        go_to(s)
    os.chdir(_init_wd)
    submit("", False, *args)


def show_help():
    print("""Subcommands (general):
  generate {number}\t\tGenerate an environment for an anonymous contest consisting of {number} problems. 
  generate {problem-url}\tGenerate an environment for a specified problem.
  generate {contest-url}\tGenerate an environment for a specified contest.
  gen\t\t\t\tAlias for 'generate'.
  help\t\t\t\tDisplay this information.

Subcommands (in the generated environment):
  {problem-name}\t\tSet the current problem to a specified problem.
  (none)\t\t\tRun your program for the current problem.
  0 [oj-test-arguments]\t\tRun all test cases.
  {number}\t\t\tRun {number}-th test cases.
  .\t\t\t\tTest and submit for the current problem.
  .!\t\t\t\tSubmit for the current problem without testing.
  .{problem-name}[!]\t\tSubmit for a specified problem.
  :\t\t\t\tTest and submit for the current problem and go to the next problem.
  clean\t\t\t\tRemove the current environment.
""")


def main():
    try:
        args = sys.argv[1:]
        if len(args) == 0:
            if Path(".problem").is_file():
                subprocess.run(["make", "_exec"])
                return
            else:
                args = ["help"]

        command = args[0].lower()
        if command == "clean":
            clean()
        elif command in ["gen", "generate"]:
            generate(args[1])
        elif len(command) >= 1 and command[0] == ".":
            name = command[1:]
            force = False
            if (len(name) >= 1 and name[-1] == "!"):
                name = name[:-1]
                force = True
            submit(name, force, *args[1:])
        elif command == ":":
            colon(*args[1:])
        elif re.match(r"^\d+$", command):
            test(int(command), *args[1:])
        elif command == "help":
            show_help()
        else:
            problem_name = command
            opening: bool = True
            if len(problem_name) >= 1 and problem_name[-1] == ":":
                problem_name = problem_name[:-1]
                opening = False
            go_to(problem_name, opening)
    except Exception as e:
        print(e, file=sys.stderr)
        exit(1)


if __name__ == "__main__":
    main()
