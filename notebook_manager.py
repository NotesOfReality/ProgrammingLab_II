import os
import sys
import subprocess
import importlib.util
from pathlib import Path
from textwrap import dedent

cached_manager = None

def find_package_manager():
    # Use shutil.which for (platform-agnostic) binary check : it reads the PATH env var
    global cached_manager
    if cached_manager is not None:
        return cached_manager

    from shutil import which
    for manager in ['uv', 'pip']: # descending order of preference
        if which(manager):
            print(f"Found {manager}. Using for packages setup.")
            cached_manager = manager
            return cached_manager
    return None

def setup_package(package_name, feature_description):
    """
    Checks if a package is available in the current environment and
    offers to install it if missing.
    """
    # Check if the package is available for import
    if importlib.util.find_spec(package_name) is None:
        print(dedent(f"""
            The '{package_name}' package is not installed.
            It is required for: {feature_description}.
            """))

        manager = find_package_manager()
        if not manager:
            print(dedent(f"""
                No package manager found.
                Package/s installation impossible.
                Feel free to manually install {package_name}.
                """))
            return False

        while True:
            user_input = input("Would you like to install it now? [y/n]: ").strip().lower()
            if user_input == 'n':
                return False
            if user_input == 'y':
                break
            print("Invalid input. Type 'y' or 'n'.")

        install_command = None
        if manager == "uv":
            install_command = [manager, "pip", "install", package_name, "--system"]
        else: # Fallback onto pip
            # Using sys.executable ensures we target the current Python environment
            install_command = [sys.executable, "-m", "pip", "install", package_name]

        print(f"Installing '{package_name}' using {manager}...")
        try:
            subprocess.check_call(install_command)
            print(f"Successfully installed '{package_name}'.\n")
        except subprocess.CalledProcessError as e:
            print(f"Failed to install '{package_name}'. Error: {e}")
            return False

    return True

def setup_git_cleaner():
    """
    Installs nbstripout and configures it to clean notebook metadata,
    specifically targeting the 'runt' field.
    """
    if not setup_package("nbstripout", "cleaning Jupyter notebook metadata"):
        print("""Cannot configure nbstripout.
            Operation 1 : Aborted.""")
        return False

    print("Configuring nbstripout...")
    try:
        # Install the git filter (adds to .gitattributes)
        subprocess.run(["nbstripout", "--install"], check=True)

        # Configure local git to strip extra keys
        # This prevents the 'runt' metadata from causing diffs
        subprocess.run(["git", "config", "--local", "filter.nbstripout.extrakeys", "metadata.runt"], check=True)

        print("nbstripout configured successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to configure nbstripout: {e}")
        return False
    return True

def run_operations(operations):
    # operations: list tuples (function_reference, operation_name)
    for func, name in operations:
        user_input = input(f"\nProceed with {name}? (y/n): ")
        if user_input.lower().strip() == 'y':
            func()
            print(f"\n{name}: Execution complete.")
        else:
            print(f"\n{name}: Execution aborted.")

# Define the absolute path for the directory to exclude
EXCLUDED_DIR = Path('esercizi').resolve()

def setup_git_tracking():
    """
    Marks tracked .ipynb files as 'assume-unchanged' in Git, thus preventing
    annoyances due to running notebooks, excluding the exercises directory.
    """
    try:
        # Retrieve all files currently tracked by Git
        git_files = subprocess.check_output(["git", "ls-files"]).decode().splitlines()
    except subprocess.CalledProcessError as e:
        print(f"Error accessing Git repository: {e}")
        return

    for file in git_files:
        path = Path(file).resolve()

        # Apply 'assume-unchanged' only to notebooks outside the exercises directory
        if path.suffix == '.ipynb' and EXCLUDED_DIR not in path.parents:
            subprocess.run(["git", "update-index", "--assume-unchanged", file])
            print(f"Git: Ignoring future changes for {file}")

    return True

def execute_notebooks():
    """
    Executes all Jupyter notebooks recursively, skipping excluded paths
    and specific lock/checkpoint files.

    Notebooks are executed in-place, allowing execution to continue despite
    runtime errors. This assumes notebooks are structured to produce errors
    only for educational or demonstration purposes without hindering the
    batch processing flow.
    """
    if not setup_package('nbconvert','batch execution of jupyter notebooks'):
        print("""Cannot configure nbconvert.
            Operation 3 : Aborted.""")
        return False

    for path in Path('.').rglob('*.ipynb'):
        # Skip the excluded directory and the runtime lock files of the notebooks
        resolved_path = path.resolve()
        if (EXCLUDED_DIR in resolved_path.parents or
                '.ipynb_checkpoints' in path.parts or
                path.name.endswith('.ipynb.runtlock')):
            continue

        print(f"Executing: {path}")

        # Run nbconvert to execute the notebook in-place.
        # Use the current python executable to ensure environment consistency.
        command = [
            sys.executable, "-m", "nbconvert", "--to", "notebook",
            "--execute", "--allow-errors", "--inplace", str(path)
        ]

        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to execute {path}: {e}")

    return True


if __name__ == "__main__":
    # Ensure the script operates within its own directory regardless of execution context
    os.chdir(Path(__file__).resolve().parent)

    # Request user confirmation before proceeding with the automated tasks
    print("--- Notebook Automation and Git Sync Utility ---")
    print("This script will perform the following actions:")
    print("1. Configure nbstripout to clean notebook metadata (including 'runt').")
    print("2. Mark tracked .ipynb files as 'assume-unchanged' in Git (excluding the 'esercizi' folder).")
    print("3. Recursively execute all remaining Jupyter notebooks in-place.")
    print("   Note: Execution is non-blocking; cells within a notebook and subsequent")
    print("   notebooks will continue to run even if runtime errors are encountered.")

    # Call list
    tasks = [
        (setup_git_cleaner, "Operation 1: Setup nbstripout"),
        (setup_git_tracking, "Operation 2: Git assume-unchanged"),
        (execute_notebooks, "Operation 3: Execute notebooks")
    ]
    run_operations(tasks)

    # Prevent the console window from closing immediately to allow output inspection
    input("Press Enter to exit...")
