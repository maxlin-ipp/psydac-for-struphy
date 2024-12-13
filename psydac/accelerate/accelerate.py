import argparse
import logging
import os
import sys
from shutil import which, rmtree
from subprocess import run as sub_run, PIPE, STDOUT  # nosec B404

import psydac


def configure_logging(level=logging.INFO):
    """
    Configure global logging settings.
    """
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stdout
    )


def pyccelize_files(root_path: str, language: str = 'fortran', openmp: bool = False):
    """
    Recursively pyccelize all files ending with '_kernels.py' in the given root path.

    Parameters
    ----------
    root_path : str
        Path to the Psydac source directory.
    language : str, optional
        Programming language for pyccel generated code ('fortran' or 'c'), by default 'fortran'.
    openmp : bool, optional
        Whether to enable OpenMP multithreading, by default False.
    """
    pyccel_path = which('pyccel')
    if pyccel_path is None:
        logging.error("`pyccel` not found in PATH. Please ensure it is installed and accessible.")
        return

    parameters = ['--language', language]
    if openmp:
        parameters.append('--openmp')

    for root, _, files in os.walk(root_path):
        for name in files:
            if name.endswith('_kernels.py'):
                file_path = os.path.join(root, name)
                logging.info(f"Pyccelizing: {file_path}")
                command = [pyccel_path, file_path] + parameters
                logging.info(f"Running command: {' '.join(command)}")

                try:
                    result = sub_run(command, stdout=PIPE, stderr=STDOUT, text=True, shell=False, check=True)  # nosec B603
                    if result.stdout.strip():
                        logging.info(result.stdout.strip())
                except Exception as e:
                    logging.error(f"Failed to pyccelize {file_path}: {e}")


def cleanup_files(root_path: str):
    """
    Remove unnecessary build artifacts, such as `__pyccel__` directories and `.lock_acquisition.lock` files.
    """
    # Remove __pyccel__ directories
    for root, dirs, _ in os.walk(root_path):
        for dirname in dirs:
            if dirname == '__pyccel__':
                dir_to_remove = os.path.join(root, dirname)
                logging.info(f"Removing directory: {dir_to_remove}")
                rmtree(dir_to_remove)

    # Remove .lock_acquisition.lock files
    for root, _, files in os.walk(root_path):
        for filename in files:
            if filename == '.lock_acquisition.lock':
                file_to_remove = os.path.join(root, filename)
                logging.info(f"Removing lock file: {file_to_remove}")
                os.remove(file_to_remove)


def main():
    parser = argparse.ArgumentParser(
        description="Pyccelize Psydac kernel files and optionally clean up build artifacts.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--language', type=str, default='fortran', choices=['fortran', 'c'],
                        help="Language used to pyccelize kernel files.")
    parser.add_argument('--openmp', action='store_true',
                        help="Use OpenMP multithreading in generated code.")
    parser.add_argument('--cleanup', action='store_true',
                        help="Remove unnecessary files and directories after pyccelizing.")

    args = parser.parse_args()

    # Configure logging
    configure_logging(logging.INFO)

    # Get the absolute path to the psydac directory
    psydac_path = os.path.abspath(os.path.dirname(psydac.__path__[0]))

    # Pyccelize kernel files
    pyccelize_files(psydac_path, language=args.language, openmp=args.openmp)

    # Cleanup if requested
    if args.cleanup:
        print('Cleanup')
        cleanup_files(psydac_path)


if __name__ == "__main__":
    main()
