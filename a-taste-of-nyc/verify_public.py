"""Compare public-export states against live Python callback responses."""
import json
import sys
from pathlib import Path

from app import app


def verify(root):
    root = Path(root)
    manifest = json.loads((root / "state-index.json").read_text())
    key, callback = next(iter(app.callback_map.items()))
    client = app.server.test_client()

    def unpack(value):
        if isinstance(value, dict) and "$object" in value:
            obj = json.loads((root / "objects" / (value["$object"] + ".json")).read_text())
            if isinstance(obj, dict) and "layout" in obj and "template" in obj["layout"]:
                obj["layout"]["template"] = unpack(obj["layout"]["template"])
            return obj
        return value

    cases = [(b, c, n) for b in manifest["boroughs"] for c, n in [(None, 1), ("Chinese", 50), ("Basque", 100)]]
    for borough, cuisine, minimum in cases:
        name = f"{manifest['boroughs'].index(borough)}-{manifest['cuisines'].index(cuisine)}-{minimum}.json"
        exported = [unpack(v) for v in json.loads((root / "states" / name).read_text())]
        values = [borough, None, 0, None, None, minimum, cuisine]
        response = client.post("/_dash-update-component", json={
            "output": key, "outputs": manifest["outputs"],
            "inputs": [dict(i, value=v) for i, v in zip(callback["inputs"], values)],
            "state": [{"id": "selected-cuisine", "property": "data", "value": cuisine}],
            "changedPropIds": ["cuisine-focus.value"],
        })
        assert response.status_code == 200
        result = response.get_json()["response"]
        expected = [result[o["id"]][o["property"]] for o in manifest["outputs"]]
        assert exported == expected, (borough, cuisine, minimum)
    assert len(list((root / "states").glob("*.json"))) == manifest["states"]
    for file in (root / "states").glob("*.json"):
        for item in json.loads(file.read_text()):
            if isinstance(item, dict) and "$object" in item:
                assert (root / "objects" / (item["$object"] + ".json")).is_file(), file
    print(f"PASS: {len(cases)} representative states exactly match Python; all {manifest['states']} states have their referenced objects.")


if __name__ == "__main__":
    verify(sys.argv[1])
