import dash
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go
from plotly import tools
from dash.dependencies import Input, Output, State
from datetime import datetime as dt
from dateutil import parser
import pandas as pd
import sundial
import numpy as np


def get_battery_output(date, usage_kWhr=8, t_start=18, t_final=22, cap_kWhr=100):
    cost_mult = 10 * cap_kWhr  # cost scales with capacity, adjust to make relavent if needed

    # Compute battery degradation cost per hour.
    battery_cph = sundial.battery_model.bat_price_per_hour(usage_kWhr,
                                                           t_start,
                                                           t_final,
                                                           date,
                                                           cap_kWhr,
                                                           cost_mult)
    return battery_cph


def get_price_output(date):
    epm = sundial.price_model.EnergyPriceModel()
    price_cph = epm.test_model(date, "SVM_rbf")
    return price_cph


def get_pv_output():
    pv_output_cph = sundial.pv_model.pv_output_cph('sundial/pv_model/finalized_model.pkl', 2016, 12, 15)  # (month,day)
    return pv_output_cph

def get_demand_output():
    # demand_cph = sundial.demand_model.get_demand_cph()
    demand_cph = pd.read_csv("sundial/data/demand_hourly.csv")
    return demand_cph['demand_kwh']


def get_model_df(input_date, t_start=18, t_final=22):
    valid_date = parser.parse(input_date)

    price_cph = get_price_output(valid_date.strftime('%Y-%m-%d'))
    battery_cph = get_battery_output(valid_date.timetuple().tm_yday, t_start=t_start, t_final=t_final)
    demand_cph = get_demand_output()
    pv_cph = get_pv_output()

    df = pd.DataFrame({'battery_cph': battery_cph,
                       'price_cph': price_cph,
                       'demand_cph': demand_cph,
                       'pv_out_cph': pv_cph})
    df['demand_cph'] = df['demand_cph'] * 10
    df['pv_out_cph'] = df['pv_out_cph'] * 20 / 250
    return df


def get_scenario_a(model_output_df, valid_date):
    dayofyear = valid_date.timetuple().tm_yday
    # Calculate Scenario A
    model_output_df['Scenario_A'] = 1 * np.max([(model_output_df['price_cph'] / 1000 * (model_output_df['demand_cph'] -
                                                 model_output_df['pv_out_cph'] - 0)), np.zeros(24)], axis=0) + \
                                    get_battery_output(dayofyear, usage_kWhr=0)

    return model_output_df['Scenario_A'].cumsum()


def get_scenario_b(model_output_df, valid_date, t_start, t_final, rate):
    dayofyear = valid_date.timetuple().tm_yday
    cap_kWhr = 100
    usage_kWhr = np.min([cap_kWhr * rate * (t_final - t_start), cap_kWhr])
    B = np.zeros(24)
    B[t_start:t_final] = usage_kWhr / (t_final - t_start)

    # Energy taken from PV to charge battery
    PV_balance = usage_kWhr * model_output_df['pv_out_cph'] / np.sum(model_output_df['pv_out_cph'])

    # calculate scenario B
    model_output_df['Scenario_B'] = 1 * np.max(
        [(model_output_df['price_cph'] / 1000 * (model_output_df['demand_cph'] - (model_output_df['pv_out_cph']
                                                - PV_balance) - B)), np.zeros(24)], axis=0) \
            + get_battery_output(dayofyear, usage_kWhr=usage_kWhr, t_start=t_start, t_final=t_final, cap_kWhr=cap_kWhr)

    return model_output_df['Scenario_B'].cumsum()


def get_scenario_c(model_output_df, valid_date, t_start, t_final, rate, cost_thresh):
    dayofyear = valid_date.timetuple().tm_yday
    cap_kWhr = 100
    is_higher = np.nonzero(model_output_df['price_cph'] > cost_thresh)

    if len(is_higher[0]) > 0:
        # assume single cycle, even if price momentarily dips below
        t_start = np.min(is_higher)
        t_final = np.max(is_higher)
        usage_kWhr = np.min([cap_kWhr * rate * (t_final - t_start), cap_kWhr])
        B = np.zeros(24)
        B[t_start:t_final] = usage_kWhr / (t_final - t_start)
        # Energy taken from PV to charge battery
        PV_balance = usage_kWhr * model_output_df['pv_out_cph'] / np.sum(model_output_df['pv_out_cph'])
    else:
        usage_kWhr = 0
        B = 0
        PV_balance = 0

    # calculate scenario c
    model_output_df['Scenario_C'] = 1 * np.max(
        [(model_output_df['price_cph'] / 1000 * (model_output_df['demand_cph'] - (model_output_df['pv_out_cph'] - PV_balance) - B)), np.zeros(24)],
        axis=0) + get_battery_output(dayofyear, usage_kWhr=usage_kWhr, t_start=t_start, t_final=t_final, cap_kWhr=cap_kWhr)

    return model_output_df['Scenario_C'].cumsum()

app = dash.Dash()

css_url = "https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0-beta.2/css/bootstrap.min.css"
app.css.append_css({
    "external_url": css_url
})


app.layout = html.Div(children=[
    html.H1(children='SunDial - solar energy cost optimization analysis'),

    html.Div(children=[
        html.Div(children=[
            html.P("SunDial is a suite of machine learning models based on weather, utility, and solar "
                   "cell-battery data to optimize solar battery utilization in a dynamic environment. Our "
                   "platform will be built to scale for different energy needs, from single family homes "
                   "to large data centers to county-wide electricity networks. Furthermore, we hope to "
                   "produce a general economic viablity assessment of solar battery installations in different "
                   "regions across the United States.")
        ], className='col'),
    ], className='row'),


    html.Div(children=[
        html.Div(children=[
            html.P("Scenario A: ... "),
            html.P("Scenario B: ... "),
            html.P("Scenario C: ... ")
        ], className='col'),
    ], className='row'),

    html.Div(children=[
        html.Div(children=[
            html.P("Date")
        ], className='col'),
        html.Div(children=[
            html.P("Time Interval Start")
        ], className='col'),
        html.Div(children=[
            html.P("Time Interval End")
        ], className='col'),
        html.Div(children=[
            html.P("Rate (%)")
        ], className='col'),
        html.Div(children=[
            html.P("Cost Threshhold ($)")
        ], className='col')
    ], className='row'),

    html.Div(children=[
        html.Div(children=[
            dcc.DatePickerSingle(id="date-picker", date=dt(2016, 12, 8)),
        ], className='col'),
        html.Div(children=[
            dcc.Input(
                id='t_start',
                placeholder='t_start',
                type='number',
                value='18'
            ),
        ], className='col'),
        html.Div(children=[
            dcc.Input(
                id='t_end',
                placeholder='t_end',
                type='number',
                value='22'
            ),
        ], className='col'),
        html.Div(children=[
            dcc.Input(
                id='rate',
                placeholder='rate',
                type='number',
                value='0.1'
            ),
        ], className='col'),
        html.Div(children=[
            dcc.Input(
                id='cost_thresh',
                placeholder='cost theshold',
                type='number',
                value='40'
            ),
        ], className='col')
    ], className='row'),

    html.Div(children=[
        html.Div(children=[
            html.Button('Submit', id="final-submit-button", className="btn btn-primary btn-lg"),
        ], className='col', style={'text-align': 'center'})
    ], className='row'),

    html.Div(children=[
        html.Div(children=[
            dcc.Graph(id='model-graphs'),
        ], className='col', style={'text-align': 'center'}),
        html.Div(children=[
            dcc.Graph(id='optimizer-graph')
        ], className='col', style={'text-align': 'center'}),
    ], className='row'),
], className='container', style={'margin-top': 25})

@app.callback(
    Output('model-graphs', 'figure'),
    [Input('final-submit-button', 'n_clicks')],
    [State('date-picker', 'date'),
     State('t_start', 'value'),
     State('t_end', 'value')]
)
def update_model_div(_, input_date, t_start, t_end):
    model_output_df = get_model_df(input_date, t_start=int(t_start), t_final=int(t_end))
    x = [i for i in range(24)]

    fig = tools.make_subplots(rows=4, cols=1, vertical_spacing=0.1)
    for i, column_name in enumerate(model_output_df.columns.values):
        trace = go.Scatter(
            x=x,
            y=model_output_df[column_name],
            mode="lines+markers",
            name=column_name,
            marker={
                'size': 6,
                'line': {'width': 0.5, 'color': 'white'}
            },
        )
        fig.append_trace(trace, i + 1, 1)

    fig['layout'].update(yaxis1={'title': 'Cost per Hour'}, yaxis2={'title': 'KWhr'}, yaxis3={'title': 'Cost per Hour'}, yaxis4={'title': 'KWhr'})
    fig['layout'].update(height=650, width=500, title='Analysis Models')
    return fig


@app.callback(
    Output('optimizer-graph', 'figure'),
    [Input('final-submit-button', 'n_clicks')],
    [State('date-picker', 'date'),
     State('t_start', 'value'),
     State('t_end', 'value'),
     State('rate', 'value'),
     State('cost_thresh', 'value'),]
)
def update_optimizer_div(_, input_date, t_start, t_end, rate, cost_thresh):
    model_output_df = get_model_df(input_date)
    valid_date = parser.parse(input_date)
    scenario_df = pd.DataFrame({"Scenario_A": get_scenario_a(model_output_df, valid_date),
                                "Scenario_B": get_scenario_b(model_output_df, valid_date, int(t_start), int(t_end), float(rate)),
                                "Scenario_C": get_scenario_c(model_output_df, valid_date, int(t_start), int(t_end), float(rate), int(cost_thresh))})

    x = [i for i in range(24)]
    traces = []
    for column_name in scenario_df.columns.values:
        traces.append(go.Scatter(
            x=x,
            y=scenario_df[column_name],
            mode="lines+markers",
            name=column_name,
            marker={
                'size': 6,
                'line': {'width': 0.5, 'color': 'white'}
            }
        ))
    return {
        'data': traces,
        'layout': go.Layout(
            xaxis={'title': 'Hour'},
            yaxis={'title': 'Cost'},
            title="Cost Analysis",
            height=650,
            width=500
        )
    }


if __name__ == '__main__':
    app.run_server()