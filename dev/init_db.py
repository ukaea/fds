"""Initialize database for demo environment.

This script auto-generates an Alembic migration inside the container if one
doesn't exist, then runs it. This keeps the demo fully ephemeral.
"""

import subprocess
import sys
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import config


def init_db():
    """Initialize database for demo environment."""
    print(f"Initializing database at: {config.db_url}")

    # Check if any migrations exist
    versions_dir = Path("alembic/versions")
    migrations_exist = versions_dir.exists() and any(versions_dir.glob("*.py"))

    if not migrations_exist:
        print("No migrations found, auto-generating from current models...")
        # Create versions directory if it doesn't exist
        versions_dir.mkdir(parents=True, exist_ok=True)

        # Auto-generate migration from models
        result = subprocess.run(
            ["alembic", "revision", "--autogenerate", "-m", "Auto-generated for demo"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            print(f"Error generating migration: {result.stderr}")
            sys.exit(1)

        print("Migration auto-generated successfully!")

    # Run migrations
    print("Running migrations...")
    result = subprocess.run(
        ["alembic", "upgrade", "head"], capture_output=True, text=True, check=False
    )

    if result.returncode != 0:
        print(f"Error running migration: {result.stderr}")
        sys.exit(1)

    print("Database initialized successfully!")


if __name__ == "__main__":
    init_db()
