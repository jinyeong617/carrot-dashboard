import base64
import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

DATA_PATH = "data.xlsx"
REQUIRED_COLUMNS = ["날짜", "상품", "매출", "분류"]
DEFAULT_GITHUB_REPO = "jinyeong617/carrot-dashboard"


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
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
def load_and_prepare_data(data_version: int, file_bytes: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(file_bytes))
    return prepare_dataframe(df)


def github_token_configured() -> bool:
    try:
        return bool(st.secrets.get("GITHUB_TOKEN"))
    except (KeyError, FileNotFoundError):
        return False


def save_to_github(file_bytes: bytes) -> tuple[bool, str]:
    try:
        token = st.secrets["GITHUB_TOKEN"]
        repo = st.secrets.get("GITHUB_REPO", DEFAULT_GITHUB_REPO)
    except (KeyError, FileNotFoundError):
        return False, "GitHub 토큰이 설정되지 않았습니다."

    api_url = f"https://api.github.com/repos/{repo}/contents/{DATA_PATH}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "carrot-dashboard",
    }

    sha = None
    request = urllib.request.Request(api_url, headers=headers)
    try:
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            sha = payload.get("sha")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            return False, f"GitHub 조회 실패: {exc.reason}"

    body = {
        "message": "대시보드에서 data.xlsx 업데이트",
        "content": base64.b64encode(file_bytes).decode("ascii"),
    }
    if sha:
        body["sha"] = sha

    upload = urllib.request.Request(
        api_url,
        data=json.dumps(body).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(upload) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        return False, f"GitHub 저장 실패: {exc.reason} ({details})"

    return True, "GitHub에 저장되었습니다. 앱이 재시작되어도 데이터가 유지됩니다."


def get_active_file_bytes() -> bytes | None:
    if st.session_state.get("uploaded_data"):
        return st.session_state.uploaded_data
    if Path(DATA_PATH).exists():
        return Path(DATA_PATH).read_bytes()
    return None


def render_upload_section() -> None:
    st.sidebar.header("데이터 업로드")
    st.sidebar.caption(
        "매일 최신 `data.xlsx` 파일을 업로드하세요. "
        "컬럼: 날짜, 상품, 분류, 매출"
    )

    uploaded = st.sidebar.file_uploader(
        "엑셀 파일 선택",
        type=["xlsx"],
        help="기존 data.xlsx 전체 파일을 업로드하면 됩니다.",
    )

    if uploaded is None:
        return

    file_bytes = uploaded.getvalue()
    try:
        preview_df = prepare_dataframe(pd.read_excel(io.BytesIO(file_bytes)))
    except ValueError as exc:
        st.sidebar.error(str(exc))
        return
    except Exception as exc:
        st.sidebar.error(f"엑셀 파일을 읽을 수 없습니다: {exc}")
        return

    last_date = preview_df["날짜"].max().strftime("%Y-%m-%d")
    st.sidebar.success(
        f"파일 확인 완료: {len(preview_df):,}행, "
        f"최신 날짜 {last_date}"
    )

    if st.sidebar.button("대시보드에 적용", type="primary", width="stretch"):
        st.session_state.uploaded_data = file_bytes
        st.session_state.data_version = (
            st.session_state.get("data_version", 0) + 1
        )

        try:
            Path(DATA_PATH).write_bytes(file_bytes)
        except OSError:
            pass

        if github_token_configured():
            saved, message = save_to_github(file_bytes)
            if saved:
                st.sidebar.success(message)
            else:
                st.sidebar.warning(
                    f"{message} 이번 접속 동안만 반영됩니다."
                )
        else:
            st.sidebar.info(
                "이번 접속에 적용되었습니다. "
                "Streamlit Cloud에서 영구 저장하려면 GitHub 토큰 설정이 필요합니다."
            )

        load_and_prepare_data.clear()
        st.rerun()


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

if "data_version" not in st.session_state:
    st.session_state.data_version = 0

render_upload_section()

file_bytes = get_active_file_bytes()
if file_bytes is None:
    st.warning("데이터 파일이 없습니다. 왼쪽 사이드바에서 엑셀 파일을 업로드해 주세요.")
    st.stop()

try:
    df = load_and_prepare_data(st.session_state.data_version, file_bytes)
except ValueError as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:
    st.error(f"데이터를 불러오지 못했습니다: {exc}")
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

latest_date = df["날짜"].max().strftime("%Y-%m-%d")
st.caption(f"현재 데이터: {len(df):,}행 · 최신 날짜 {latest_date}")

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