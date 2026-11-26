"""Shared chart expansion and accessible, consistent hover cards."""
from dash import html, dcc, Input, Output, State, ClientsideFunction


def expand_button(kind, label):
    return html.Button(html.Img(src='assets/expand.svg', alt=''), id=f'expand-{kind}',
                       n_clicks=0, className='expand-button', title=f'Expand {label}',
                       **{'aria-label': f'Expand {label}'})


def ui_components():
    return [
        dcc.Store(id='expanded-kind'),
        html.Div([
            html.Button(id='modal-backdrop', n_clicks=0, className='modal-backdrop',
                        **{'aria-label':'Close chart overlay'}),
            html.Section([
                html.Div([html.Div([html.H2(id='expanded-title'), html.P(id='expanded-context')]),
                          html.Button('×', id='close-expanded', n_clicks=0, className='modal-close',
                                      **{'aria-label':'Close expanded chart'})], className='modal-heading'),
                html.Div(dcc.Graph(id='expanded-graph', responsive=True, clear_on_unhover=True,
                    config={'displayModeBar':True,'displaylogo':False,'responsive':True,'scrollZoom':True,
                            'modeBarButtonsToRemove':['lasso2d','select2d','autoScale2d','toggleSpikelines']},
                    className='expanded-plot'), className='modal-plot-body'),
                html.P('Click a cuisine or borough to update the dashboard. Press Esc to close.',className='modal-help'),
            ], id='modal-card', className='modal-card'),
        ],id='chart-modal', className='chart-modal',style={'display':'none'},role='dialog',
           **{'aria-modal':'true','aria-labelledby':'expanded-title'}),
        html.Div(id='ui-tooltip',className='ui-tooltip',style={'display':'none'},role='tooltip'),
    ]


def register_ui_callbacks(app):
    app.clientside_callback(ClientsideFunction(namespace='nyc_ui',function_name='modalState'),
        Output('chart-modal','style'),Output('expanded-kind','data'),
        Input('expand-scatter','n_clicks'),Input('expand-bar','n_clicks'),Input('expand-borough','n_clicks'),
        Input('close-expanded','n_clicks'),Input('modal-backdrop','n_clicks'),Input('reset','n_clicks'),
        State('borough-view','value'),State('expanded-kind','data'),prevent_initial_call=True)
    app.clientside_callback(ClientsideFunction(namespace='nyc_ui',function_name='renderExpanded'),
        Output('expanded-graph','figure'),Output('expanded-title','children'),
        Output('expanded-context','children'),Output('modal-card','className'),
        Input('expanded-kind','data'),Input('scatter','figure'),Input('bar','figure'),
        Input('heatmap','figure'),Input('borough-map','figure'),Input('selection','children'),
        prevent_initial_call=True)
    app.clientside_callback(ClientsideFunction(namespace='nyc_ui',function_name='forwardClick'),
        Output('scatter','clickData',allow_duplicate=True),Output('bar','clickData',allow_duplicate=True),
        Output('heatmap','clickData',allow_duplicate=True),Output('borough-map','clickData',allow_duplicate=True),
        Output('expanded-graph','clickData'),Input('expanded-graph','clickData'),State('expanded-kind','data'),
        prevent_initial_call=True)
    app.clientside_callback(ClientsideFunction(namespace='nyc_ui',function_name='tooltip'),
        Output('ui-tooltip','style'),Output('ui-tooltip','children'),
        Input('scatter','hoverData'),Input('bar','hoverData'),Input('heatmap','hoverData'),
        Input('borough-map','hoverData'),Input('expanded-graph','hoverData'),
        Input('expanded-kind','data'),Input('borough-view','value'),
        State('borough-map','figure'),State('expanded-graph','figure'),prevent_initial_call=True)
