"""d4builds.gg structured parser - NOT IMPLEMENTED YET.

d4builds.gg is a community planner where a build URL
(d4builds.gg/builds/<uuid>) maps to a structured build document - the most
parser-friendly of the three providers. Once the fetch endpoint is pinned
down, map its skills / gear / paragon data into Grimoire's generic
sections format (see mobalytics.py docstring for the shape).
"""


def parse(url: str, page: str) -> dict:
    raise NotImplementedError("d4builds structured parsing not implemented yet")
