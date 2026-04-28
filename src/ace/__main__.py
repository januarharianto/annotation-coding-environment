import argparse

from ace.app import run


def main():
    parser = argparse.ArgumentParser(description="ACE — Annotation Coding Environment")
    parser.add_argument("--port", type=int, default=None, help="Server port")
    args = parser.parse_args()
    run(port=args.port)


if __name__ == "__main__":
    main()
