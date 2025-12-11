import os
import subprocess
import sys
from pathlib import Path

# --- CONFIGURATION ---
# Set this to your local project root
PROJECT_ROOT = Path(r"C:\Users\asher\OneDrive - Informs\ScholarOne-Tools")

# Set your GitHub repo URL
REMOTE_URL = "https://github.com/Sparda104/S1-API-Project.git"

BRANCH = "main"


def run(cmd, cwd=None):
    """Run a shell command and print it."""
    print(f"\n>>> {cmd}")
    result = subprocess.run(cmd, cwd=cwd, shell=True)
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def ensure_gitignore_excludes_venv():
    gitignore_path = PROJECT_ROOT / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(".venv/\n", encoding="utf-8")
        print("Created .gitignore with .venv/ entry")
        return

    content = gitignore_path.read_text(encoding="utf-8").splitlines()
    if ".venv/" not in content and ".venv" not in content:
        content.append(".venv/")
        gitignore_path.write_text("\n".join(content) + "\n", encoding="utf-8")
        print("Added .venv/ to .gitignore")
    else:
        print(".venv/ already ignored in .gitignore")


def main():
    if not PROJECT_ROOT.exists():
        print(f"Project root does not exist: {PROJECT_ROOT}")
        sys.exit(1)

    os.chdir(PROJECT_ROOT)
    print(f"Working in: {PROJECT_ROOT}")

    # 1. Ensure .venv is ignored
    ensure_gitignore_excludes_venv()

    # 2. Initialize git repo if needed
    if not (PROJECT_ROOT / ".git").exists():
        run("git init", cwd=PROJECT_ROOT)
        run(f"git branch -M {BRANCH}", cwd=PROJECT_ROOT)

    # 3. Set remote origin (idempotent)
    # Try to set origin only if it doesn't exist
    result = subprocess.run("git remote get-url origin",
                            cwd=PROJECT_ROOT,
                            shell=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)

    if result.returncode != 0:
        run(f"git remote add origin {REMOTE_URL}", cwd=PROJECT_ROOT)
        print(f"Added origin remote: {REMOTE_URL}")
    else:
        print("Remote 'origin' already set")

    # 4. Stop tracking .venv if it was already tracked
    run("git rm -r --cached .venv || echo '.venv not tracked or already removed from index.'",
        cwd=PROJECT_ROOT)

    # 5. Add project files (excluding .venv thanks to .gitignore)
    run("git add .", cwd=PROJECT_ROOT)

    # 6. Commit (if there is anything to commit)
    # git diff --cached --quiet returns exit code 1 if there are staged changes
    diff_result = subprocess.run(
        "git diff --cached --quiet", cwd=PROJECT_ROOT, shell=True
    )
    if diff_result.returncode != 0:
        run('git commit -m "Sync local ScholarOne-Tools project to GitHub"', cwd=PROJECT_ROOT)
    else:
        print("No changes to commit")

    # 7. Pull remote changes (to avoid non-fast-forward errors)
    run(f"git pull origin {BRANCH} --allow-unrelated-histories || echo 'Pull had conflicts or no changes.'",
        cwd=PROJECT_ROOT)

    # 8. Push to GitHub
    run(f"git push -u origin {BRANCH}", cwd=PROJECT_ROOT)
    print("\nRepository is now synced with local project.")


if __name__ == "__main__":
    main()
