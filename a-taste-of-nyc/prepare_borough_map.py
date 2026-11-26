"""Build display geometry from the official NYC DCP borough GeoJSON.

Usage: python prepare_borough_map.py /path/to/downloaded.geojson
No restaurant metrics use this simplified geometry or a spatial join.
"""
import gzip
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = 'https://data.cityofnewyork.us/resource/gthc-hcne.geojson?$limit=10'


def simplify_ring(points, tolerance=.00025):
    """Douglas-Peucker simplification in degrees, about 28 m latitude."""
    keep = {0, len(points)-1}
    stack = [(0, len(points)-1)]
    while stack:
        first, last = stack.pop()
        if last <= first+1:
            continue
        ax, ay = points[first]; bx, by = points[last]
        dx, dy = bx-ax, by-ay
        length = dx*dx+dy*dy
        best, index = 0, first
        for i in range(first+1, last):
            x,y = points[i]
            t = max(0,min(1,((x-ax)*dx+(y-ay)*dy)/length)) if length else 0
            distance = (x-ax-t*dx)**2+(y-ay-t*dy)**2
            if distance > best:
                best,index = distance,i
        if best > tolerance*tolerance:
            keep.add(index); stack.extend([(first,index),(index,last)])
    result = [points[i] for i in sorted(keep)]
    # Retain tiny rings rather than collapse a polygon into a line.
    if len(result) < 4:
        result = points
    return [[round(x,5),round(y,5)] for x,y in result]


def prepare(path):
    raw = Path(path).read_bytes(); source = json.loads(raw)
    assert source['type']=='FeatureCollection' and len(source['features'])==5
    features=[]; before=after=0
    for f in source['features']:
        assert f['geometry']['type']=='MultiPolygon'
        polygons=[]
        for polygon in f['geometry']['coordinates']:
            rings=[]
            for ring in polygon:
                clean=simplify_ring(ring)
                before+=len(ring);after+=len(clean);rings.append(clean)
            polygons.append(rings)
        features.append({'type':'Feature','properties':{'borough':f['properties']['boroname']},
                         'geometry':{'type':'MultiPolygon','coordinates':polygons}})
    data=ROOT/'data';out=data/'borough_boundaries.geojson'
    out.write_text(json.dumps({'type':'FeatureCollection','features':features},separators=(',',':')))
    (data/'borough_boundaries_source.geojson.gz').write_bytes(gzip.compress(raw,mtime=0))
    receipt={'source_url':SOURCE,'publisher':'NYC Department of City Planning / NYC Open Data',
             'dataset':'gthc-hcne','download_date':'2026-11-24','features':5,
             'coordinate_system':'WGS84 longitude/latitude','water_areas':'excluded',
             'source_vertices':before,'display_vertices':after,'simplification_degrees':.00025,
             'rounding_decimal_places':5,'purpose':'display only; restaurant metrics use borough names',
             'source_sha256':hashlib.sha256(raw).hexdigest(),
             'display_sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
    (data/'borough_boundaries_receipt.json').write_text(json.dumps(receipt,indent=2))
    print(f'Borough map: {before:,} -> {after:,} vertices; {out.stat().st_size:,} bytes')

if __name__=='__main__':
    prepare(sys.argv[1])
