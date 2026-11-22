"""The data of the slicing scenario: 24 people, as CSV, a top-level JSON array
and XML. Deterministic. Cities repeat (DISTINCT, GROUP BY, self-join on the
city), managers refer to other rows (self-join on a key), scores order the
rows (ORDER BY ... LIMIT), rows follow each other (neighbour pattern).

    python make_data.py <directory>
"""

import json
import os
import random
import sys

CITIES = ["Paris", "Lyon", "Saint-Etienne", "Madrid", "Gent", "Bologna"]


def people(n=24, seed=11):
    rnd = random.Random(seed)
    out = []
    for i in range(1, n + 1):
        out.append({"id": i, "name": "person %02d" % i, "city": CITIES[rnd.randrange(len(CITIES))],
                    "manager": (rnd.randrange(1, i) if i > 3 else None),
                    "score": rnd.randrange(0, 100)})
    return out


def main(d):
    os.makedirs(d, exist_ok=True)
    ps = people()
    with open(os.path.join(d, "people.csv"), "w", encoding="utf-8") as f:
        f.write("id,name,city,manager,score\n")
        for p in ps:
            f.write("%d,%s,%s,%s,%d\n" % (p["id"], p["name"], p["city"],
                                          "" if p["manager"] is None else p["manager"], p["score"]))
    with open(os.path.join(d, "people.json"), "w", encoding="utf-8") as f:
        json.dump([{k: v for k, v in p.items() if v is not None} for p in ps], f, indent=1)
    with open(os.path.join(d, "people.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<people>\n')
        for p in ps:
            f.write('  <person id="%d"><name>%s</name><city>%s</city>%s<score>%d</score></person>\n' % (
                p["id"], p["name"], p["city"],
                "" if p["manager"] is None else "<manager>%d</manager>" % p["manager"], p["score"]))
        f.write("</people>\n")


if __name__ == "__main__":
    main(sys.argv[1])
