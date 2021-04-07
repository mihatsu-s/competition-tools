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
    with open(os.path.join(_init_wd, "__cd"), "w") as f:
        f.write(x)


def set_rm_path(x: str, directory=_init_wd):
    with open(os.path.join(directory, "__rm"), "w") as f:
        f.write(x)


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


def generate_contest(contest_name: str, envs: List[Env], opening=False, auto_naming=False):
    os.mkdir(contest_name)
    os.chdir(contest_name)
    with open(".contest", "w") as f:
        f.write(contest_name)
    if auto_naming:
        for i, env in enumerate(envs):
            env.problem_name = chr(ord("A") + i)
    for i, env in enumerate(envs):
        env.prepare(directory=env.problem_name, opening=(i == 0), memo=envs[i + 1].problem_name if i + 1 < len(envs) else "")
    set_cd_path(os.path.join(contest_name, envs[0].problem_name))


def submit(name: str, force: bool, *args):
    if (name != ""):
        if (is_task_directory()):
            os.chdir("..")
        os.chdir(name)
    cmd = ["make", "_submit_force" if force else "_submit"]
    if len(args) > 0:
        cmd.append("TEST_ARGS=" + " ".join(args))
    subprocess.run(cmd)


def test(idx: int, *args):
    cmd = ["make"]
    if idx == 0:
        cmd.append("_test")
        if len(args) > 0:
            cmd.append("TEST_ARGS=" + " ".join(args))
    else:
        cmd.append("_exec_input")
        test_files = []
        test_dir = Path("test")
        if (test_dir.is_dir()):
            for f in test_dir.iterdir():
                name = str(f)
                if (re.search(r"\.in$", name)):
                    test_files.append(name)
        test_files.sort()
        cmd.append("EXEC_INPUT=" + test_files[idx - 1])
    subprocess.run(cmd)


def move(name: str):
    no_open = False
    if name[-1] == ":":
        name = name[:-1]
        no_open = True

    if (is_task_directory()):
        os.chdir("..")
    os.chdir(name)

    if not no_open:
        sp = subprocess.run(["make", "_open"])
    if (no_open or sp.returncode == 0):
        set_cd_path(os.getcwd())


def colon(*args):
    if not is_task_directory():
        raise RuntimeError("You are not in problem directory.")
    s = ""
    with open(".problem") as f:
        s = f.readline()
    if len(s):
        move(s)
    os.chdir(_init_wd)
    submit("", False, *args)


def main():
    try:
        args = sys.argv[1:]
        if len(args) == 0:
            subprocess.run(["make", "_exec"])
            return

        command = args[0].lower()
        if command == "clean":
            clean()
        elif command in ["g", "gen", "generate"]:
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
        else:
            move(command)
    except Exception as e:
        print(e, file=sys.stderr)
        exit(1)


if __name__ == "__main__":
    main()
