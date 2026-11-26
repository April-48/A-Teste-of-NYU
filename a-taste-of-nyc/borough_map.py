"""Offline SVG borough choropleth: the same within-borough shares as heatmap.

Real DCP boundaries, local equirectangular projection, no tiles or map tokens.
Trace order is the stable borough order used to route polygon clicks.
"""
import json
import math
from functools import lru_cache
from html import escape
from pathlib import Path

import plotly.graph_objects as go
from plotly.colors import sample_colorscale
from palette import SELECTED

# Label anchors are geographical coordinates, not statistical measurements.
ANCHORS = {'Bronx':(-73.85,40.855), 'Brooklyn':(-73.96,40.65),
           'Manhattan':(-73.975,40.79), 'Queens':(-73.81,40.735),
           'Staten Island':(-74.15,40.575)}
LONGITUDE_FACTOR = math.cos(math.radians(40.7))


class BoroughMap:
    def __init__(self, frame, boroughs, colors, missing='Unknown'):
        self.boroughs = list(boroughs)
        self.colors = colors
        self.totals = frame.groupby('borough').CAMIS.nunique().to_dict()
        self.counts = frame.groupby(['borough','cuisine']).CAMIS.nunique().to_dict()
        ranked = frame[frame.cuisine.ne(missing)].groupby('cuisine').CAMIS.nunique()
        self.cuisines = sorted(ranked.index, key=lambda c:(-ranked[c],c))
        maximum=max([n/self.totals[b] for (b,c),n in self.counts.items()
                     if c!=missing and self.totals.get(b)] or [.01])
        self.maximum=math.ceil(max(.01,maximum)*20)/20
        geo=json.loads((Path(__file__).parent/'data/borough_boundaries.geojson').read_text())
        self.geometry={f['properties']['borough']:f['geometry']['coordinates'] for f in geo['features']}
        if set(self.geometry)!=set(self.boroughs):
            raise ValueError('Map must contain exactly the five known boroughs.')
        self.coordinates={}
        for borough,polygons in self.geometry.items():
            xs,ys=[],[]
            for polygon in polygons:
                for ring in polygon:
                    xs.extend([lon*LONGITUDE_FACTOR for lon,lat in ring]+[None])
                    ys.extend([lat for lon,lat in ring]+[None])
            self.coordinates[borough]=(xs,ys)

    def focus(self, selected=None, allowed=None):
        eligible=self.cuisines if allowed is None else [c for c in self.cuisines if c in allowed]
        return selected if selected in eligible else None

    @lru_cache(maxsize=256)
    def figure(self, borough='All NYC', selected=None, allowed=None):
        cuisine=self.focus(selected,allowed)
        fig=go.Figure()
        metrics=[]
        for i,b in enumerate(self.boroughs):
            total=int(self.totals.get(b,0)); count=int(self.counts.get((b,cuisine),0))
            share=count/total if cuisine is not None and total else None
            fill=sample_colorscale(self.colors,[share/self.maximum])[0] if share is not None else '#e4e9e6'
            metrics.append({'borough':b,'restaurants':count,'total':total,'share':share})
            active=b==borough
            detail=(f'<b>{escape(b)} · {escape(cuisine)}</b><br>Restaurants: {count:,}'
                    f'<br>Share of borough: {share:.1%}<br>All borough restaurants: {total:,}'
                    if share is not None else f'<b>{escape(b)}</b><br>Choose a cuisine to compare shares')
            xs,ys=self.coordinates[b]
            fig.add_trace(go.Scatter(x=xs,y=ys,mode='lines',fill='toself',fillcolor=fill,
                name=b,hoveron='fills',text=detail,hoverinfo='text',
                line={'color':SELECTED if active else '#ffffff','width':2.5 if active else .8},
                showlegend=False))
            # A side key stays readable even in the compact overview card.
            label=f'{escape(b)} · <b>{share:.1%}</b>' if share is not None else escape(b)
            fig.add_annotation(x=.70,y=.96-i*.22,xref='paper',yref='paper',xanchor='left',yanchor='middle',
                               text=label,showarrow=False,
                               font={'size':14,'color':'#172033'})
        # A marker-free trace provides the same shared numeric color legend.
        if cuisine is not None:
            fig.add_trace(go.Scatter(x=[None],y=[None],mode='markers',hoverinfo='skip',showlegend=False,
                marker={'color':[0],'colorscale':self.colors,'cmin':0,'cmax':self.maximum,'showscale':True,
                        # Keep the shared legend legible in the compact overview.
                        'colorbar':{'title':{'text':'Share (%)','side':'right','font':{'size':11}},
                                    'tickvals':[0,self.maximum/2,self.maximum],'tickformat':'.0%',
                                    'tickfont':{'size':11},'thickness':11,'len':.95,'xpad':4}}))
        fig.update_layout(template='plotly_white',showlegend=False,dragmode=False,
            meta={'cuisine':cuisine,'boroughs':metrics,'projection':'local equirectangular'},
            paper_bgcolor='white',plot_bgcolor='white',font={'family':'Arial, sans-serif','size':14,'color':'#172033'},
            margin={'l':70,'r':16,'t':18,'b':44},hoverlabel={'bgcolor':'white','font_size':14},
            # Preserve geographic ranges when the card changes size. Without
            # domain constraints, scaleanchor expands ranges on every resize
            # and the boroughs stay tiny after a narrow-to-wide transition.
            xaxis={'visible':True,'fixedrange':True,'domain':[0,.62],'constrain':'domain',
                   'title':{'text':'Longitude (°W)','font':{'size':16},'standoff':6},
                   'tickvals':[lon*LONGITUDE_FACTOR for lon in [-74.2,-73.8]],
                   'ticktext':['74.2°W','73.8°W'],'tickfont':{'size':14},
                   'showline':True,'linecolor':'#cbd2d7','ticks':'outside',
                   'showgrid':False,'zeroline':False,'automargin':True,
                   'range':[-74.28*LONGITUDE_FACTOR,-73.67*LONGITUDE_FACTOR]},
            yaxis={'visible':True,'fixedrange':True,'scaleanchor':'x','scaleratio':1,'constrain':'domain',
                   'title':{'text':'Latitude (°N)','font':{'size':16},'standoff':6},
                   'tickvals':[40.5,40.7,40.9],
                   'ticktext':['40.5°N','40.7°N','40.9°N'],'tickfont':{'size':14},
                   'showline':True,'linecolor':'#cbd2d7','ticks':'outside',
                   'showgrid':False,'zeroline':False,'automargin':True,
                   'range':[40.47,40.94]},
            annotations=[*fig.layout.annotations,
                {'x':.02,'y':1.10,'xref':'paper','yref':'paper','text':'N ↑','showarrow':False,'font':{'size':11}},
                {'x':1,'y':1.12,'xref':'paper','yref':'paper','xanchor':'right','text':'NYC DCP · land boundaries',
                 'showarrow':False,'font':{'size':9,'color':'#59645f'}}])
        return fig,cuisine


def register_view_callbacks(app):
    """Presentation-only toggle: reused unchanged by local Dash and public export."""
    from dash import Input, Output
    app.clientside_callback(
        '''function(mode) {
            const map = mode === "map";
            return [{display: map ? "none" : "block"}, {display: map ? "block" : "none"},
                    "panel borough-panel " + (map ? "map-mode" : "heatmap-mode"), true];
        }''',
        Output('heatmap-view','style'),Output('map-view','style'),Output('borough-panel','className'),
        Output('cuisine-focus','clearable'),Input('borough-view','value'),
        prevent_initial_call=True)
    app.clientside_callback('function() { return "heatmap"; }',
        Output('borough-view','value'),Input('reset','n_clicks'),prevent_initial_call=True)
    app.clientside_callback(
        '''function(figure) {
            const columns = figure?.data?.[0]?.x?.length || 10;
            return {"--heatmap-readable-width": (240 + columns * 50) + "px"};
        }''',
        Output('heatmap','style'),Input('heatmap','figure'))
