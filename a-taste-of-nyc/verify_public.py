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

    cases = [(b, c, n, "all") for b in manifest["boroughs"] for c, n in [(None, 1), ("Chinese", 50), ("Basque", 100)]]
    for bi, borough in enumerate(manifest["boroughs"]):
        for count_range, (_, low, high) in manifest["count_ranges"].items():
            if count_range == "all":
                continue
            eligible = [c for c in manifest["cuisines"] if c and low <= manifest["counts"][bi].get(c, 0)
                        and (high is None or manifest["counts"][bi].get(c, 0) <= high)]
            cases.extend([(borough, None, 100, count_range), (borough, eligible[0] if eligible else None, 1, count_range)])
    for borough, cuisine, minimum, count_range in cases:
        ri = list(manifest["count_ranges"]).index(count_range)
        name = f"{manifest['boroughs'].index(borough)}-{manifest['cuisines'].index(cuisine)}-{minimum}-{ri}.json"
        exported = [unpack(v) for v in json.loads((root / "states" / name).read_text())]
        values = [borough, None, 0, None, None, minimum, cuisine, count_range, None]
        response = client.post("/_dash-update-component", json={
            "output": key, "outputs": manifest["outputs"],
            "inputs": [dict(i, value=v) for i, v in zip(callback["inputs"], values)],
            "state": [{"id": "selected-cuisine", "property": "data", "value": cuisine},
                      {"id": "borough-view", "property": "value", "value": "heatmap"}],
            "changedPropIds": ["cuisine-focus.value"],
        })
        assert response.status_code == 200
        result = response.get_json()["response"]
        expected = [result[o["id"]][o["property"]] for o in manifest["outputs"]]
        assert exported == expected, (borough, cuisine, minimum)
    # Exercise the map click reducer in addition to state-render parity.
    map_cases = [("All NYC", "Chinese", "Brooklyn", "all"),
                 ("All NYC", "Chinese", "Brooklyn", "100-499"),
                 ("Brooklyn", "Frozen Desserts", "Queens", "all")]
    for old_boro, cuisine, target, count_range in map_cases:
        values = [old_boro, None, 0, None, None, 1, cuisine, count_range,
                  {"points":[{"curveNumber":manifest["boroughs"].index(target)-1}]}]
        response = client.post("/_dash-update-component", json={
            "output": key, "outputs": manifest["outputs"],
            "inputs": [dict(i, value=v) for i, v in zip(callback["inputs"], values)],
            "state": [{"id":"selected-cuisine","property":"data","value":cuisine},
                      {"id":"borough-view","property":"value","value":"map"}],
            "changedPropIds":["borough-map.clickData"]})
        assert response.status_code==200
        result=response.get_json()["response"]
        actual_range=result["count-filter"]["value"]
        name=f"{manifest['boroughs'].index(target)}-{manifest['cuisines'].index(cuisine)}-1-{list(manifest['count_ranges']).index(actual_range)}.json"
        exported=[unpack(v) for v in json.loads((root/"states"/name).read_text())]
        assert exported==[result[o["id"]][o["property"]] for o in manifest["outputs"]]
    assert len(list((root / "states").glob("*.json"))) == manifest["states"]
    for file in (root / "states").glob("*.json"):
        for item in json.loads(file.read_text()):
            if isinstance(item, dict) and "$object" in item:
                assert (root / "objects" / (item["$object"] + ".json")).is_file(), file
    print(f"PASS: {len(cases)} representative states and {len(map_cases)} map-click states exactly match Python; all {manifest['states']} states have their referenced objects.")


if __name__ == "__main__":
    verify(sys.argv[1])
