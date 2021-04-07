import pyperclip
from sys import stderr
from argparse import ArgumentParser


def copy_file(filename: str):
    with open(filename) as f:
        pyperclip.copy(f.read())
        print("Copied {} to the clipboard.".format(filename), file=stderr)


def main():
    parser = ArgumentParser()
    parser.add_argument("file")
    args = parser.parse_args()
    copy_file(args.file)


if __name__ == "__main__":
    main()
