"""Maxroll structured parser - NOT IMPLEMENTED YET.

Maxroll build guides are article pages, but their d4 planner links
(maxroll.gg/d4/planner/<id>) are backed by a planner profile service that
returns JSON. That JSON references game-data IDs (skills, affixes, paragon
nodes) that need a mapping table to render as human-readable text, so the
first structured milestone here is planner profile names + per-slot item
list, falling back to the generic behaviour for everything else.
"""


def parse(url: str, page: str) -> dict:
    raise NotImplementedError("Maxroll structured parsing not implemented yet")
