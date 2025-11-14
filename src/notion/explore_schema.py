"""Deprecated: Notion schema explorer.

This script previously connected to the Notion API to dump database
properties. Notion integration was removed; this module now raises to
avoid accidental use.
"""

def main(*_args, **_kwargs):
    raise RuntimeError("Notion integration removed; explore_schema is deprecated")


if __name__ == "__main__":
    main()
