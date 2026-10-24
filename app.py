"""
Global Economics Playground — milestone 1
=========================================

A Streamlit app that pulls World Bank data with wbgapi and draws it with Plotly.

How Streamlit works (the one idea you need):
    Streamlit runs this whole file from top to bottom every time you touch a
    widget (pick a country, move the slider...). Each widget simply returns its
    current value as a normal Python variable. That's why caching matters:
    without it, every click would re-download the data.

Run it with:   streamlit run app.py
"""

import pandas as pd
import plotly.express as px
import streamlit as st
import wbgapi as wb


# ---------------------------------------------------------------------------
# 1. Page setup
# ---------------------------------------------------------------------------
# Must be the first Streamlit command in the script. "wide" uses the full
# browser width instead of a narrow centred column.
st.set_page_config(page_title="Global Economics Playground", layout="wide")


# ---------------------------------------------------------------------------
# 2. The indicators we offer
# ---------------------------------------------------------------------------
# Left: the label the user sees. Right: the World Bank's code for that series.
# You can look up more codes at https://data.worldbank.org (open an indicator,
# the code is in the URL) or in Python with:  wb.series.info(q="inflation")
INDICATORS = {
    "GDP per capita, PPP (constant 2021 international $)": "NY.GDP.PCAP.PP.KD",
    "Inflation, consumer prices (annual %)": "FP.CPI.TOTL.ZG",
    "Unemployment (% of labor force, ILO estimate)": "SL.UEM.TOTL.ZS",
    "Central government debt, total (% of GDP)": "GC.DOD.TOTL.GD.ZS",
}

# Countries pre-selected when the app first opens (ISO3 codes).
DEFAULT_COUNTRIES = ["BRA", "ARG", "MEX", "CHL", "USA"]


# ---------------------------------------------------------------------------
# 3. Data-loading functions (cached)
# ---------------------------------------------------------------------------
# @st.cache_data means: "the first time this function is called with these
# arguments, run it and remember the result; next time, hand back the stored
# copy instead of calling the API again."
# ttl = time-to-live: after 24 hours the stored copy expires and is refreshed.
# show_spinner puts a "loading..." message on screen while it runs.

@st.cache_data(ttl=60 * 60 * 24, show_spinner="Loading country list from the World Bank...")
def load_countries() -> pd.DataFrame:
    """Return a table of real countries: columns 'code' and 'name'.

    The World Bank also has 'aggregates' (World, Latin America, High income...).
    We drop them here to keep the list clean; we can add them back later.
    """
    rows = []
    for economy in wb.economy.list():  # yields one dict per economy
        if not economy["aggregate"]:
            rows.append({"code": economy["id"], "name": economy["value"]})
    return pd.DataFrame(rows).sort_values("name").reset_index(drop=True)


@st.cache_data(ttl=60 * 60 * 24, show_spinner="Downloading indicator from the World Bank...")
def load_indicator(series_code: str) -> pd.DataFrame:
    """Download ONE indicator for ALL countries and ALL years.

    Why everything at once? Because then changing the country selection or the
    year slider is just filtering a table already in memory: zero new API
    calls. Only switching to an indicator we haven't seen yet hits the API.

    Returns a "long" table, one row per (country, year):
        code | year | value
    """
    rows = []
    # wb.data.fetch yields one dict per data point, e.g.
    # {'economy': 'BRA', 'time': 'YR2010', 'value': 14512.3, ...}
    # skipBlanks=True leaves out years where the World Bank has no number.
    for point in wb.data.fetch(series_code, economy="all", skipBlanks=True):
        rows.append(
            {
                "code": point["economy"],
                "year": int(point["time"].replace("YR", "")),  # 'YR2010' -> 2010
                "value": point["value"],
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. Load the data we always need
# ---------------------------------------------------------------------------
countries = load_countries()
# A dictionary code -> name, e.g. {'BRA': 'Brazil', ...}, used for labels.
code_to_name = dict(zip(countries["code"], countries["name"]))


# ---------------------------------------------------------------------------
# 5. Sidebar controls (the widgets)
# ---------------------------------------------------------------------------
# Anything written as st.sidebar.<widget> appears in the left-hand panel.
st.sidebar.header("Controls")

# Dropdown for the indicator. It returns the label the user picked.
indicator_label = st.sidebar.selectbox("Indicator", list(INDICATORS.keys()))
indicator_code = INDICATORS[indicator_label]

# Multiselect for countries. We store codes but display names
# (format_func converts each code into the text shown to the user).
selected_codes = st.sidebar.multiselect(
    "Countries",
    options=countries["code"].tolist(),
    default=[c for c in DEFAULT_COUNTRIES if c in code_to_name],
    format_func=lambda code: code_to_name.get(code, code),
)

# Now that we know which indicator was chosen, get its data (cached).
data = load_indicator(indicator_code)

# Slider for years. Its limits come from the data itself, so they adapt to
# each indicator. Passing a tuple as `value` makes it a two-handled range slider.
min_year, max_year = int(data["year"].min()), int(data["year"].max())
year_start, year_end = st.sidebar.slider(
    "Year range",
    min_value=min_year,
    max_value=max_year,
    value=(max(min_year, 1990), max_year),
)

st.sidebar.caption("Source: World Bank, World Development Indicators (via wbgapi).")


# ---------------------------------------------------------------------------
# 6. Filter the data according to the controls
# ---------------------------------------------------------------------------
filtered = data[
    data["code"].isin(selected_codes)
    & data["year"].between(year_start, year_end)  # between() includes both ends
].copy()
filtered["country"] = filtered["code"].map(code_to_name)
filtered = filtered.sort_values(["country", "year"])


# ---------------------------------------------------------------------------
# 7. Main area: title, chart, table
# ---------------------------------------------------------------------------
st.title("Global Economics Playground")
st.subheader(indicator_label)

if not selected_codes:
    # st.info shows a blue message box. st.stop() ends this run of the script.
    st.info("Pick at least one country in the sidebar.")
    st.stop()

if filtered.empty:
    st.warning("No data for this combination of countries, indicator and years.")
    st.stop()

# Tell the user if some selected countries have no data at all for this series
# (common for government debt, which many countries don't report).
missing = [code_to_name[c] for c in selected_codes if c not in set(filtered["code"])]
if missing:
    st.caption("No data in this range for: " + ", ".join(missing))

# The chart: x = year, y = value, one line (and colour) per country.
fig = px.line(
    filtered,
    x="year",
    y="value",
    color="country",
    markers=True,
    labels={"year": "Year", "value": indicator_label, "country": "Country"},
)
# "x unified" = hovering over a year shows every country's value at once.
fig.update_layout(hovermode="x unified", legend_title_text="")
st.plotly_chart(fig, width="stretch")  # stretch = fill the available width

# A collapsible section with the raw numbers, wide format
# (rows = years, columns = countries), plus a CSV download button.
with st.expander("Show data table"):
    wide = filtered.pivot(index="year", columns="country", values="value")
    st.dataframe(wide, width="stretch")
    st.download_button(
        "Download CSV",
        data=wide.to_csv().encode("utf-8"),
        file_name=f"{indicator_code}_{year_start}-{year_end}.csv",
        mime="text/csv",
    )
