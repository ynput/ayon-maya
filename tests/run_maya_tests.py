"""Run the Maya tests with one or more `mayapy` interpreters.

Each `test_*.py` file under `tests/` is a standalone script that is run in a
separate `mayapy` process (it initializes `maya.standalone` itself and exits
non-zero on failure).

Run with any Python 3 interpreter:

    # `mayapy` from the MAYAPY environment variable or from PATH
    python tests/run_maya_tests.py

    # Explicit `mayapy` executable(s)
    python tests/run_maya_tests.py --mayapy "C:/Program Files/Autodesk/Maya2025/bin/mayapy.exe"

    # Maya version(s) installed in the default install location
    python tests/run_maya_tests.py --maya-version 2024 --maya-version 2025

    # All Maya versions installed in the default install location
    python tests/run_maya_tests.py --all-installed

    # Only specific test files
    python tests/run_maya_tests.py tests/client/ayon_maya/api/test_lib_rendersetup.py

"""
import argparse
import glob
import os
import platform
import re
import shutil
import subprocess
import sys

TESTS_ROOT = os.path.dirname(os.path.abspath(__file__))


def get_default_mayapy_path(version):
    """Return `mayapy` path for Maya version in the default install location.
    """
    system = platform.system()
    if system == "Windows":
        return os.path.join(
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            "Autodesk", "Maya{}".format(version), "bin", "mayapy.exe")
    if system == "Darwin":
        return ("/Applications/Autodesk/maya{}/Maya.app/Contents/bin/mayapy"
                .format(version))
    return "/usr/autodesk/maya{}/bin/mayapy".format(version)


def get_installed_maya_versions():
    """Return Maya versions found in the default install location."""
    pattern = get_default_mayapy_path("*")
    versions = set()
    for path in glob.glob(pattern):
        match = re.search(r"maya(\d+(?:\.\d+)?)", path, re.IGNORECASE)
        if match:
            versions.add(match.group(1))
    return sorted(versions)


def resolve_mayapy_paths(args):
    """Return the `mayapy` executables to run the tests with."""
    paths = list(args.mayapy)

    versions = list(args.maya_version)
    if args.all_installed:
        versions.extend(get_installed_maya_versions())
    for version in versions:
        path = get_default_mayapy_path(version)
        if not os.path.isfile(path):
            raise RuntimeError(
                "mayapy for Maya {} not found at: {}".format(version, path))
        paths.append(path)

    if not paths:
        path = os.environ.get("MAYAPY") or shutil.which("mayapy")
        if not path:
            raise RuntimeError(
                "No mayapy found. Set the MAYAPY environment variable, add "
                "mayapy to PATH or use --mayapy, --maya-version or "
                "--all-installed.")
        paths.append(path)

    # Remove duplicates, preserving order
    unique = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def collect_test_files(paths):
    """Return test files from the given files or directories."""
    if not paths:
        paths = [TESTS_ROOT]

    test_files = []
    for path in paths:
        path = os.path.abspath(path)
        if os.path.isfile(path):
            test_files.append(path)
            continue
        test_files.extend(sorted(glob.glob(
            os.path.join(path, "**", "test_*.py"), recursive=True)))
    return test_files


def main():
    parser = argparse.ArgumentParser(
        description="Run AYON Maya tests with mayapy.")
    parser.add_argument(
        "tests", nargs="*",
        help="Test files or directories. Defaults to all tests.")
    parser.add_argument(
        "--mayapy", action="append", default=[],
        help="Path to a mayapy executable. Can be passed multiple times.")
    parser.add_argument(
        "--maya-version", action="append", default=[],
        help="Maya version installed in the default location, e.g. 2025. "
             "Can be passed multiple times.")
    parser.add_argument(
        "--all-installed", action="store_true",
        help="Run with all Maya versions in the default install location.")
    args = parser.parse_args()

    try:
        mayapy_paths = resolve_mayapy_paths(args)
    except RuntimeError as exc:
        parser.error(str(exc))

    test_files = collect_test_files(args.tests)
    if not test_files:
        parser.error("No test files found.")

    results = []
    for mayapy in mayapy_paths:
        for test_file in test_files:
            print("=" * 79)
            print("mayapy: {}".format(mayapy))
            print("test:   {}".format(os.path.relpath(test_file)))
            print("=" * 79, flush=True)
            returncode = subprocess.call([mayapy, test_file])
            results.append((mayapy, test_file, returncode == 0))

    print("\nSummary:")
    for mayapy, test_file, passed in results:
        print("  {}  {}  ({})".format(
            "PASS" if passed else "FAIL",
            os.path.relpath(test_file),
            mayapy))

    return 0 if all(passed for _, _, passed in results) else 1


if __name__ == "__main__":
    sys.exit(main())
