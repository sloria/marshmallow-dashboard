import logging

import dash
import dash_core_components as dcc
import dash_html_components as html
import environs
import pandas as pd
import plotly.graph_objs as go
from dash.dependencies import Input
from dash.dependencies import Output
from flask_caching import Cache
from google.auth.crypt._python_rsa import RSASigner
from google.cloud import bigquery
from google.oauth2.service_account import Credentials

# -----------------------------------------------------------------------------

env = environs.Env()
env.read_env(recurse=False)

HOST = env.str("DASH_RUN_HOST", "127.0.0.1")
PRIVATE_KEY = env.str("GOOGLE_PRIVATE_KEY", required=True)
PRIVATE_KEY_ID = env.str("GOOGLE_PRIVATE_KEY_ID", required=True)
PROJECT_ID = env.str("GOOGLE_PROJECT_ID", required=True)
CLIENT_EMAIL = env.str("GOOGLE_CLIENT_EMAIL", required=True)
REDIS_URL = env.str("REDIS_URL", required=True)
TOKEN_URI = env.str("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token")
CACHE_TIMEOUT = env.int("CACHE_TIMEOUT", 3600)
USE_STATIC_DATA = env.bool("USE_STATIC_DATA", False)
CACHE_GRAPHS = env.bool("CACHE_GRAPHS", False)
LOG_LEVEL = env.str("LOG_LEVEL", "INFO")


# -----------------------------------------------------------------------------

app = dash.Dash(__name__)
app.logger.setLevel(getattr(logging, LOG_LEVEL))
server = app.server
cache = Cache(
    server,
    config={
        "CACHE_TYPE": "redis",
        "CACHE_REDIS_URL": REDIS_URL,
        "CACHE_DEFAULT_TIMEOUT": CACHE_TIMEOUT,
    },
)

# -----------------------------------------------------------------------------


def get_client():
    signer = RSASigner.from_string(key=PRIVATE_KEY, key_id=PRIVATE_KEY_ID)
    scopes = ("https://www.googleapis.com/auth/bigquery",)
    credentials = Credentials(
        signer=signer,
        service_account_email=CLIENT_EMAIL,
        token_uri=TOKEN_URI,
        scopes=scopes,
        project_id=PROJECT_ID,
    )
    return bigquery.Client(project=PROJECT_ID, credentials=credentials)


query = """
SELECT *
FROM `marshmallow-dashboard.results.downloads*`
WHERE
   _TABLE_SUFFIX
    BETWEEN FORMAT_DATE(
      '%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
    AND FORMAT_DATE('%Y%m%d', CURRENT_DATE())
"""


@cache.cached(key_prefix="dataframe")
def get_data():
    if USE_STATIC_DATA:
        app.logger.debug("using static data")
        return pd.read_csv("july.csv")
    app.logger.info("fetching data")
    client = get_client()
    result = client.query(query)
    return result.to_dataframe()


# -----------------------------------------------------------------------------


def LinuxCheckbox(id):
    return dcc.Checklist(
        id=id, options=[{"label": "Include Linux (CI)", "value": "include_linux"}]
    )


def PercentageCheckbox(id):
    return dcc.Checklist(
        id=id,
        options=[{"label": "Percentages", "value": "percentages"}],
        value=["percentages"],
    )


ma2_vs_ma3 = html.Div(
    [
        html.H2("marshmallow 2 vs. 3 (past 30 days)"),
        dcc.Graph(id="ma2-vs-ma3", style=dict(height=300)),
        PercentageCheckbox(id="ma2-vs-ma3--percentages"),
        LinuxCheckbox(id="ma2-vs-ma3--include-linux"),
    ]
)

ma2_vs_ma3_by_week = html.Div(
    [
        html.H2("marshmallow 2 vs. 3 by week (past 30 days)"),
        dcc.Graph(id="ma2-vs-ma3-by-week", style=dict(height=300)),
        PercentageCheckbox(id="ma2-vs-ma3-by-week--percentages"),
        LinuxCheckbox(id="ma2-vs-ma3-by-week--include-linux"),
    ]
)

ma_versions = html.Div(
    [
        html.H2("most downloaded versions (past 30 days)"),
        dcc.Graph(id="ma-versions", style=dict(height=350)),
        PercentageCheckbox(id="ma-versions--percentages"),
        LinuxCheckbox(id="ma-versions--include-linux"),
    ]
)

ma2_vs_ma3_python_minor = html.Div(
    [
        html.H2("marshmallow 2 vs. 3 by Python version (past 30 days)"),
        dcc.Graph(id="ma2-vs-ma3-pyminor", style=dict(height=300)),
        LinuxCheckbox(id="ma2-vs-ma3-pyminor--include-linux"),
    ]
)


def layout():
    get_data()  # fetch the data and add it the cache
    return html.Div(
        children=[
            html.H1("marshmallow dashboard"),
            html.P(
                "Data were collected from PyPI's BigQuery dataset. Excludes downloads from mirrors and Linux platforms (to correct for CI downloads)."
            ),
            ma2_vs_ma3,
            ma2_vs_ma3_by_week,
            ma_versions,
            ma2_vs_ma3_python_minor,
        ]
    )


app.layout = layout
app.title = "dashboard"

# -----------------------------------------------------------------------------

MA_COLORS = {"2.x": "#4f446e", "3.x": "#d15858"}
PYTHON_COLORS = {
    "2.6": "#4376a1",
    "2.7": "#316998",
    "3.0": "#fff1af",
    "3.1": "#fff1af",
    "3.2": "#fff1af",
    "3.3": "#fff1af",
    "3.4": "#ffea87",
    "3.5": "#ffe66d",
    "3.6": "#e8d264",
    "3.7": "#d1bd5a",
    "3.8": "#baa850",
    "3.9": "#a39346",
}
FONT = {"family": "monaco, consolas, menlo, monospace", "color": "#363636"}


def maybe_cache_graph(func):
    if CACHE_GRAPHS:
        app.logger.debug(f"caching graph callback: {func}")
        return cache.memoize()(func)
    return func


@app.callback(
    Output("ma2-vs-ma3", "figure"),
    [
        Input("ma2-vs-ma3--percentages", "value"),
        Input("ma2-vs-ma3--include-linux", "value"),
    ],
)
@maybe_cache_graph
def update_ma2_vs_ma3(percentages, include_linux):
    app.logger.debug("update_ma2_vs_ma3 callback")
    df = get_data()
    majors = df[df.category_label == "marshmallow_major"]
    if include_linux:
        ma2_category, ma3_category = "2", "3"
    else:
        ma2_category, ma3_category = "2-no_linux", "3-no_linux"

    ma2 = majors[majors.category_value == ma2_category]
    ma2_downloads = ma2.downloads.sum()
    ma3 = majors[majors.category_value == ma3_category]
    ma3_downloads = ma3["downloads"].sum()

    if percentages:
        total = ma2_downloads + ma3_downloads
        ma2_percent = ma2_downloads / total
        ma3_percent = ma3_downloads / total
        x = [ma2_percent, ma3_percent]
        x_title = "percentage"
        tickformat = "%"
    else:
        x = [ma2_downloads, ma3_downloads]
        x_title = "downloads"
        tickformat = ",d"

    y = ["ma2", "ma3"]
    colors = [MA_COLORS["2.x"], MA_COLORS["3.x"]]

    return go.Figure(
        data=[go.Bar(x=x, y=y, marker=dict(color=colors), orientation="h")],
        layout=go.Layout(
            font=FONT,
            margin=go.layout.Margin(t=10),
            xaxis=dict(title=x_title, tickformat=tickformat),
        ),
    )


def downloads_by_week(df, date_key="date", downloads_key="downloads"):
    df_copy = df.loc[:, [downloads_key]]
    df_copy["week"] = pd.to_datetime(df[date_key]) - pd.to_timedelta(7, unit="d")
    grouped = df_copy.groupby([pd.Grouper(key="week", freq="W-MON")])[downloads_key]
    # exclude current week
    return grouped.sum().reset_index().sort_values("week")[:-1]


@app.callback(
    Output("ma2-vs-ma3-by-week", "figure"),
    [
        Input("ma2-vs-ma3-by-week--percentages", "value"),
        Input("ma2-vs-ma3-by-week--include-linux", "value"),
    ],
)
@maybe_cache_graph
def update_ma2_vs_ma3_by_week(percentages, include_linux):
    app.logger.debug("update_ma2_vs_ma3_by_week callback")
    df = get_data()
    majors = df[df.category_label == "marshmallow_major"]
    if include_linux:
        ma2_category, ma3_category = "2", "3"
    else:
        ma2_category, ma3_category = "2-no_linux", "3-no_linux"

    ma2 = majors[majors.category_value == ma2_category]
    ma2_by_week = downloads_by_week(ma2)

    ma3 = majors[majors.category_value == ma3_category]
    ma3_by_week = downloads_by_week(ma3)

    if percentages:
        joined = pd.merge(
            ma2_by_week, ma3_by_week, on="week", how="inner", suffixes=("_ma2", "_ma3")
        )
        totals = joined.downloads_ma2 + joined.downloads_ma3

        ma2_x = ma3_x = joined.week.to_list()
        ma2_y = joined.downloads_ma2 / totals
        ma3_y = joined.downloads_ma3 / totals

        barmode = "stack"
        y_title = "percentage"
        tickformat = ".1%"
    else:
        ma2_x = ma2_by_week.week.to_list()
        ma2_y = ma2_by_week.downloads.to_list()
        ma3_x = ma3_by_week.week.to_list()
        ma3_y = ma3_by_week.downloads.to_list()
        tickformat = ",d"
        barmode = "group"
        y_title = "downloads"

    data = [
        go.Bar(x=ma2_x, y=ma2_y, name="ma2", marker=dict(color=MA_COLORS["2.x"])),
        go.Bar(x=ma3_x, y=ma3_y, name="ma3", marker=dict(color=MA_COLORS["3.x"])),
    ]
    return go.Figure(
        data=data,
        layout=go.Layout(
            font=FONT,
            barmode=barmode,
            margin=go.layout.Margin(t=30),
            yaxis=dict(title=y_title, tickformat=tickformat),
            xaxis=dict(title="week"),
        ),
    )


@app.callback(
    Output("ma-versions", "figure"),
    [
        Input("ma-versions--percentages", "value"),
        Input("ma-versions--include-linux", "value"),
    ],
)
@maybe_cache_graph
def update_ma_versions(percentages, include_linux):
    app.logger.debug("update_ma_versions callback")
    df = get_data()
    ma_versions = df[df.category_label == "marshmallow_version"]
    if include_linux:
        data = ma_versions[~ma_versions.category_value.str.endswith("no_linux")]
    else:
        data = ma_versions[ma_versions.category_value.str.endswith("no_linux")]

    totals = (
        data.groupby(["category_value"])["downloads"].sum().sort_values(ascending=False)
    )
    top_10 = totals[:10]

    if percentages:
        total = sum(top_10.values)
        x = [each / total for each in reversed(top_10.values)]
        x_title = "percentage"
        tickformat = ".1%"
    else:
        x = list(reversed(top_10.values))
        x_title = "downloads"
        tickformat = ",d"

    y = [version.split("-")[0] for version in reversed(top_10.index)]
    colors = [
        MA_COLORS["2.x"] if label.startswith("2") else MA_COLORS["3.x"] for label in y
    ]

    return go.Figure(
        data=[go.Bar(x=x, y=y, marker=dict(color=colors), orientation="h")],
        layout=go.Layout(
            font=FONT,
            xaxis=dict(title=x_title, tickformat=tickformat),
            margin=go.layout.Margin(t=5, b=50),
        ),
    )


@app.callback(
    Output("ma2-vs-ma3-pyminor", "figure"),
    [Input("ma2-vs-ma3-pyminor--include-linux", "value")],
)
@maybe_cache_graph
def update_ma2_vs_ma3_pyminor(value):
    app.logger.info("update_ma2_vs_ma3_pyminor callback")
    df = get_data()
    combined = df[df.category_label == "combined"]
    if value and "include_linux" in value:
        data = combined[~combined.category_value.str.endswith("no_linux")]
    else:
        data = combined[combined.category_value.str.endswith("no_linux")]

    ma2 = data[data.category_value.str.contains("marshmallow2")]
    ma2_versions = sorted(ma2.category_value.unique())
    ma2_labels = [version.split("-")[0].lstrip("py") for version in ma2_versions]
    ma2_colors = [PYTHON_COLORS.get(label, "#6991b4") for label in ma2_labels]
    ma2_values = [
        ma2[ma2.category_value == version].downloads.sum() for version in ma2_versions
    ]

    ma3 = data[data.category_value.str.contains("marshmallow3")]
    ma3_versions = sorted(ma3.category_value.unique())
    ma3_labels = [version.split("-")[0].lstrip("py") for version in ma3_versions]
    ma3_colors = [PYTHON_COLORS.get(label, "#fff3bc") for label in ma3_labels]
    ma3_values = [
        ma3[ma3.category_value == version].downloads.sum() for version in ma3_versions
    ]

    return go.Figure(
        data=[
            go.Pie(
                values=ma2_values,
                labels=ma2_labels,
                textinfo="label",
                hoverinfo="label+percent+value",
                marker=dict(colors=ma2_colors),
                hole=0.6,
                name="ma2",
                domain=dict(column=0),
            ),
            go.Pie(
                values=ma3_values,
                labels=ma3_labels,
                textinfo="label",
                hoverinfo="label+percent+value",
                marker=dict(colors=ma3_colors),
                hole=0.6,
                name="ma3",
                domain=dict(column=1),
            ),
        ],
        layout=go.Layout(
            font=FONT,
            grid=go.layout.Grid(rows=1, columns=2),
            margin=go.layout.Margin(t=5, b=60),
            legend=go.layout.Legend(x=1, y=0),
            annotations=[
                go.layout.Annotation(
                    text="ma2", font=dict(size=25), x=0.2, y=0.5, showarrow=False
                ),
                go.layout.Annotation(
                    text="ma3", font=dict(size=25), x=0.81, y=0.5, showarrow=False
                ),
            ],
        ),
    )


if __name__ == "__main__":
    app.run_server(host=HOST, debug=True)
