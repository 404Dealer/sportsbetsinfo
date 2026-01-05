"""Entry point for sportsbetsinfo CLI.

Run with: python -m sportsbetsinfo
Or after install: sportsbetsinfo
"""

from sportsbetsinfo.cli.commands import cli


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
