from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

DATA_PATH = "data.xlsx"
REQUIRED_COLUMNS = ["날짜", "상품", "매출", "분류"]


@st.cache_data
def load_and_prepare_data(path: str) -> pd.DataFrame:
    df = pd.read_excel(path)

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {', '.join(missing)}")

    df = df.dropna(subset=REQUIRED_COLUMNS)

    df["날짜"] = pd.to_datetime(
        df["날짜"].astype(str),
        format="%Y%m%d",
        errors="coerce",
    )
    df = df.dropna(subset=["날짜"])

    df["매출"] = (
        df["매출"]
        .astype(str)
        .str.replace(",", "", regex=False)
    )
    df["매출"] = pd.to_numeric(df["매출"], errors="coerce")
    df = df.dropna(subset=["매출"])
    df = df[df["매출"] > 0]

    df["주시작"] = df["날짜"] - pd.to_timedelta(df["날짜"].dt.weekday, unit="D")
    df["주종료"] = df["주시작"] + pd.Timedelta(days=6)
    df["주차"] = (
        df["주시작"].dt.strftime("%Y-%m-%d")
        + " ~ "
        + df["주종료"].dt.strftime("%Y-%m-%d")
    )

    return df.reset_index(drop=True)


@st.cache_data
def get_daily_sales(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(["날짜", "상품", "분류"])["매출"]
        .sum()
        .reset_index()
    )


@st.cache_data
def get_daily_total_sales(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby("날짜")["매출"].sum().reset_index()


@st.cache_data
def get_weekly_sales(df: pd.DataFrame) -> pd.DataFrame:
    weekly_sales = (
        df.groupby(["주시작", "주차"])["매출"]
        .sum()
        .reset_index()
        .sort_values("주시작")
        .reset_index(drop=True)
    )

    weekly_sales["전주매출"] = weekly_sales["매출"].shift(1)
    weekly_sales["증감률"] = (
        (weekly_sales["매출"] - weekly_sales["전주매출"])
        / weekly_sales["전주매출"]
    ) * 100

    return weekly_sales


def build_color_map(categories) -> dict:
    colors = px.colors.qualitative.G10
    return {
        cat: colors[i % len(colors)]
        for i, cat in enumerate(categories)
    }


def format_sales_column(series: pd.Series) -> pd.Series:
    return series.map(lambda x: f"{x:,.0f}")


st.set_page_config(
    page_title="일별 상품 매출 분석",
    layout="wide",
)

st.markdown(
    """
    <h1 style='font-size:48px;'>
        🥕 당근 매출 대시보드 🥕
    </h1>

    <p style='font-size:22px; color:gray;'>
        일별 / 주별 상품 매출 분석 시스템
    </p>
    """,
    unsafe_allow_html=True,
)

if Path("logo.png").exists():
    st.image("logo.png", width=200)

st.divider()

if not Path(DATA_PATH).exists():
    st.error(f"{DATA_PATH} 파일을 찾을 수 없습니다.")
    st.stop()

try:
    df = load_and_prepare_data(DATA_PATH)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

daily_sales = get_daily_sales(df)
daily_total_sales = get_daily_total_sales(df)
weekly_sales = get_weekly_sales(df)
color_map = build_color_map(df["분류"].unique())

date_list = (
    daily_sales["날짜"]
    .drop_duplicates()
    .sort_values(ascending=False)
    .head(20)
)
date_options = [d.strftime("%Y-%m-%d") for d in date_list]

st.sidebar.header("필터")
selected_date = st.sidebar.radio("날짜 선택", date_options)
selected_date = pd.to_datetime(selected_date)

selected_data = daily_sales[daily_sales["날짜"] == selected_date]
selected_data = selected_data.sort_values("매출", ascending=False)

tab_daily, tab_trend, tab_weekly = st.tabs(
    ["일별 분석", "매출 추이", "주별 분석"]
)

with tab_daily:
    st.subheader("일별 매출")

    daily_chart_height = max(500, len(selected_data) * 40)

    fig = px.bar(
        selected_data,
        x="상품",
        y="매출",
        color="분류",
        color_discrete_map=color_map,
        title=f"{selected_date.strftime('%Y-%m-%d')} 상품별 매출",
        text="매출",
        template="plotly_white",
        category_orders={"상품": selected_data["상품"].tolist()},
    )

    fig.update_layout(
        height=daily_chart_height,
        xaxis_tickangle=-30,
        yaxis_tickformat=",",
        showlegend=True,
        xaxis=dict(tickfont=dict(size=18)),
    )
    fig.update_traces(
        texttemplate="%{text:,.0f}",
        textposition="outside",
        textfont=dict(size=20),
    )

    st.plotly_chart(fig, width="stretch")

    st.subheader("데이터")
    display_df = selected_data.copy()
    display_df["매출"] = format_sales_column(display_df["매출"])
    st.dataframe(display_df, width="stretch")

with tab_trend:
    st.subheader("일별 총 매출 추이")

    fig_daily_line = px.line(
        daily_total_sales,
        x="날짜",
        y="매출",
        markers=True,
        title="일별 총 매출 추이",
        template="plotly_white",
    )
    fig_daily_line.update_layout(
        height=500,
        yaxis_tickformat=",",
        hovermode="x unified",
    )
    fig_daily_line.update_traces(
        text=daily_total_sales["매출"],
        texttemplate="%{text:,.0f}",
        textposition="top center",
    )
    st.plotly_chart(fig_daily_line, width="stretch")

    st.subheader("주별 총 매출 추이")

    fig_weekly = px.line(
        weekly_sales,
        x="주차",
        y="매출",
        markers=True,
        title="주별 총 매출 추이",
        template="plotly_white",
    )
    fig_weekly.update_layout(
        height=500,
        yaxis_tickformat=",",
        hovermode="x unified",
        xaxis_title="주차",
        yaxis_title="총 매출",
    )
    fig_weekly.update_traces(
        text=weekly_sales["매출"],
        texttemplate="%{text:,.0f}",
        textposition="top center",
    )
    st.plotly_chart(fig_weekly, width="stretch")

with tab_weekly:
    st.subheader("주간 KPI")

    latest_week = weekly_sales.iloc[-1]
    change_rate = latest_week["증감률"]

    col1, col2 = st.columns(2)
    col1.metric("이번 주 매출", f"{latest_week['매출']:,.0f} 원")
    col2.metric(
        "전주 대비",
        f"{change_rate:.1f}%" if not pd.isna(change_rate) else "-",
        delta=f"{change_rate:.1f}%" if not pd.isna(change_rate) else None,
    )

    st.subheader("주별 데이터")

    weekly_display = weekly_sales.drop(columns=["주시작"]).copy()
    weekly_display["매출"] = format_sales_column(weekly_display["매출"])
    weekly_display["전주매출"] = weekly_display["전주매출"].map(
        lambda x: "-" if pd.isna(x) else f"{x:,.0f}"
    )
    weekly_display["증감률"] = weekly_display["증감률"].map(
        lambda x: "-" if pd.isna(x) else f"{x:.1f}%"
    )
    st.dataframe(weekly_display, width="stretch")

    st.subheader("주별 상품 상세 분석")

    week_options = weekly_sales["주차"].tolist()
    selected_week = st.selectbox("주 선택", week_options)

    weekly_detail = df[df["주차"] == selected_week]
    weekly_product_sales = (
        weekly_detail.groupby(["상품", "분류"])["매출"]
        .sum()
        .reset_index()
        .sort_values("매출", ascending=True)
        .reset_index(drop=True)
    )

    week_product_count = len(weekly_product_sales)
    top_n_week = st.slider(
        "상위 N개 상품",
        min_value=1,
        max_value=week_product_count,
        value=week_product_count,
        key=f"weekly_top_n_{selected_week}",
    )

    weekly_chart_data = (
        weekly_product_sales
        .sort_values("매출", ascending=False)
        .head(top_n_week)
        .sort_values("매출", ascending=True)
        .reset_index(drop=True)
    )

    chart_height = max(400, len(weekly_chart_data) * 35)

    fig_week_detail = px.bar(
        weekly_chart_data,
        y="상품",
        x="매출",
        color="분류",
        color_discrete_map=color_map,
        text="매출",
        title=(
            f"{selected_week} 상품별 매출 "
            f"(상위 {top_n_week}개 / 전체 {week_product_count}개)"
        ),
        template="plotly_white",
        orientation="h",
        category_orders={"상품": weekly_chart_data["상품"].tolist()},
    )
    fig_week_detail.update_layout(
        height=chart_height,
        xaxis_tickformat=",",
        showlegend=True,
        margin=dict(l=350, r=50, t=80, b=50),
        yaxis=dict(tickfont=dict(size=16)),
        xaxis=dict(tickfont=dict(size=14)),
    )
    fig_week_detail.update_traces(
        texttemplate="%{text:,.0f}",
        textposition="outside",
        textfont=dict(size=16),
    )
    st.plotly_chart(fig_week_detail, width="stretch")

    st.subheader("주별 상품 데이터")
    weekly_display_detail = weekly_chart_data.copy()
    weekly_display_detail["매출"] = format_sales_column(
        weekly_display_detail["매출"]
    )
    st.dataframe(weekly_display_detail, width="stretch")