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
MONTHLY_KPI_PATH = "monthly_kpi.xlsx"
REQUIRED_COLUMNS = ["날짜", "상품", "매출", "분류"]
CONVERSION_COLUMNS = ["년월", "주차시작", "첫구매전환율", "재구매율"]
MEMBER_COLUMNS = ["년월", "주차시작", "전체가입자", "전체업체수", "업체평균가입자"]
DEFAULT_GITHUB_REPO = "jinyeong617/carrot-dashboard"
RECENT_DATE_LIMIT = 20
WEEKDAYS_KR = ["월", "화", "수", "목", "금", "토", "일"]


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
    df["년월"] = df["날짜"].dt.to_period("M").astype(str)

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


def save_to_github(
    file_bytes: bytes,
    file_path: str = DATA_PATH,
    commit_message: str | None = None,
) -> tuple[bool, str]:
    try:
        token = st.secrets["GITHUB_TOKEN"]
        repo = st.secrets.get("GITHUB_REPO", DEFAULT_GITHUB_REPO)
    except (KeyError, FileNotFoundError):
        return False, "GitHub 토큰이 설정되지 않았습니다."

    api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
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
        "message": commit_message or f"대시보드에서 {file_path} 업데이트",
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


def get_monthly_kpi_bytes() -> bytes | None:
    if st.session_state.get("uploaded_monthly_kpi"):
        return st.session_state.uploaded_monthly_kpi
    if Path(MONTHLY_KPI_PATH).exists():
        return Path(MONTHLY_KPI_PATH).read_bytes()
    return None


def format_month_label(month_value: str) -> str:
    year, month = month_value.split("-")
    return f"{year}년 {int(month)}월"


def format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def prepare_conversion_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    missing = [col for col in CONVERSION_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"전환_재구매 시트 필수 컬럼 누락: {', '.join(missing)}")

    df = df.dropna(subset=CONVERSION_COLUMNS).copy()
    df["주차시작"] = pd.to_datetime(df["주차시작"], errors="coerce")
    df = df.dropna(subset=["주차시작"])
    df["년월"] = df["년월"].astype(str)
    df["첫구매전환율"] = pd.to_numeric(df["첫구매전환율"], errors="coerce")
    df["재구매율"] = pd.to_numeric(df["재구매율"], errors="coerce")
    df = df.dropna(subset=["첫구매전환율", "재구매율"])
    return df.sort_values("주차시작").reset_index(drop=True)


def prepare_members_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    missing = [col for col in MEMBER_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"가입자 시트 필수 컬럼 누락: {', '.join(missing)}")

    df = df.dropna(subset=MEMBER_COLUMNS).copy()
    df["주차시작"] = pd.to_datetime(df["주차시작"], errors="coerce")
    df = df.dropna(subset=["주차시작"])
    df["년월"] = df["년월"].astype(str)
    for col in ["전체가입자", "전체업체수", "업체평균가입자"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["전체가입자", "전체업체수", "업체평균가입자"])
    return df.sort_values("주차시작").reset_index(drop=True)


@st.cache_data
def load_monthly_conversion(kpi_version: int, file_bytes: bytes) -> pd.DataFrame:
    sheet_df = pd.read_excel(io.BytesIO(file_bytes), sheet_name="전환_재구매")
    return prepare_conversion_dataframe(sheet_df)


@st.cache_data
def load_monthly_members(kpi_version: int, file_bytes: bytes) -> pd.DataFrame:
    sheet_df = pd.read_excel(io.BytesIO(file_bytes), sheet_name="가입자")
    return prepare_members_dataframe(sheet_df)


def apply_uploaded_file(
    file_bytes: bytes,
    file_path: str,
    session_key: str,
    version_key: str,
    *clear_cache_fns,
) -> None:
    st.session_state[session_key] = file_bytes
    st.session_state[version_key] = st.session_state.get(version_key, 0) + 1

    try:
        Path(file_path).write_bytes(file_bytes)
    except OSError:
        pass

    if github_token_configured():
        saved, message = save_to_github(file_bytes, file_path=file_path)
        if saved:
            st.success(message)
        else:
            st.warning(f"{message} 이번 접속 동안만 반영됩니다.")
    else:
        st.info(
            "이번 접속에 적용되었습니다. "
            "Streamlit Cloud에서 영구 저장하려면 GitHub 토큰 설정이 필요합니다."
        )

    for clear_cache_fn in clear_cache_fns:
        clear_cache_fn.clear()
    st.rerun()


def format_date_label(date_value: pd.Timestamp) -> str:
    weekday = WEEKDAYS_KR[date_value.weekday()]
    return f"{date_value.strftime('%Y-%m-%d')} ({weekday})"


def ensure_selected_date(all_dates: list[pd.Timestamp]) -> None:
    latest = all_dates[0].strftime("%Y-%m-%d")
    valid_dates = {date.strftime("%Y-%m-%d") for date in all_dates}

    if "selected_date_str" not in st.session_state:
        st.session_state.selected_date_str = latest
    elif st.session_state.selected_date_str not in valid_dates:
        st.session_state.selected_date_str = latest


def render_date_panel(
    df: pd.DataFrame,
    daily_total_sales: pd.DataFrame,
) -> pd.Timestamp:
    all_dates = sorted(df["날짜"].drop_duplicates(), reverse=True)
    recent_dates = all_dates[:RECENT_DATE_LIMIT]
    all_date_values = [date.strftime("%Y-%m-%d") for date in all_dates]
    recent_date_values = [date.strftime("%Y-%m-%d") for date in recent_dates]

    ensure_selected_date(all_dates)
    selected_value = st.session_state.selected_date_str

    latest_date = all_dates[0]
    st.caption(
        f"총 {len(all_dates)}일 · 최신 {format_date_label(latest_date)}"
    )

    selected_dt = pd.to_datetime(selected_value)
    selected_sales = daily_total_sales.loc[
        daily_total_sales["날짜"] == selected_dt,
        "매출",
    ]
    if not selected_sales.empty:
        st.metric("선택한 날짜 매출", f"{selected_sales.iloc[0]:,.0f} 원")

    default_mode = (
        1 if selected_value not in recent_date_values else 0
    )
    date_mode = st.radio(
        "선택 방식",
        ["최근 20일", "전체 날짜"],
        index=default_mode,
        horizontal=True,
        label_visibility="collapsed",
    )

    if date_mode == "최근 20일":
        st.caption("가장 최근 영업일을 빠르게 선택하세요.")
        recent_index = (
            recent_date_values.index(selected_value)
            if selected_value in recent_date_values
            else 0
        )
        st.session_state.selected_date_str = st.radio(
            "최근 20일",
            recent_date_values,
            index=recent_index,
            format_func=lambda value: format_date_label(pd.to_datetime(value)),
            label_visibility="collapsed",
        )
    else:
        st.caption("과거 날짜를 검색해 선택하세요.")
        all_index = (
            all_date_values.index(selected_value)
            if selected_value in all_date_values
            else 0
        )
        st.session_state.selected_date_str = st.selectbox(
            "전체 날짜",
            all_date_values,
            index=all_index,
            format_func=lambda value: format_date_label(pd.to_datetime(value)),
            label_visibility="collapsed",
        )

    return pd.to_datetime(st.session_state.selected_date_str)


def render_sales_upload_panel() -> None:
    st.markdown("#### 매출 데이터")
    st.caption("`data.xlsx` 전체 파일을 업로드하세요.")

    with st.container(border=True):
        st.markdown(
            "1. 엑셀에 오늘 데이터 추가 후 저장\n"
            "2. 파일 선택\n"
            "3. **적용** 클릭"
        )
        st.caption("필수 컬럼: 날짜 · 상품 · 분류 · 매출")

    uploaded = st.file_uploader(
        "매출 엑셀",
        type=["xlsx"],
        key="sales_uploader",
        label_visibility="collapsed",
    )
    if uploaded is None:
        st.info("파일을 선택해 주세요.")
        return

    file_bytes = uploaded.getvalue()
    try:
        preview_df = prepare_dataframe(pd.read_excel(io.BytesIO(file_bytes)))
    except (ValueError, Exception) as exc:
        st.error(str(exc))
        return

    last_date = preview_df["날짜"].max()
    first_date = preview_df["날짜"].min()
    col1, col2 = st.columns(2)
    col1.metric("행 수", f"{len(preview_df):,}")
    col2.metric("기간", f"{first_date.strftime('%m/%d')}~{last_date.strftime('%m/%d')}")
    st.success(f"확인 완료 · {format_date_label(last_date)}")

    if st.button("매출 데이터 적용", type="primary", width="stretch", key="apply_sales"):
        apply_uploaded_file(
            file_bytes,
            DATA_PATH,
            "uploaded_data",
            "data_version",
            load_and_prepare_data,
        )


def render_monthly_upload_panel() -> None:
    st.markdown("#### 월간 KPI")
    st.caption("`monthly_kpi.xlsx` 전체 파일을 업로드하세요.")

    with st.container(border=True):
        st.markdown(
            "1. `전환_재구매`, `가입자` 시트에 주차 데이터 추가\n"
            "2. 파일 선택\n"
            "3. **적용** 클릭"
        )

    uploaded = st.file_uploader(
        "월간 KPI 엑셀",
        type=["xlsx"],
        key="monthly_uploader",
        label_visibility="collapsed",
    )
    if uploaded is None:
        st.info("파일을 선택해 주세요.")
        return

    file_bytes = uploaded.getvalue()
    try:
        conversion_df = prepare_conversion_dataframe(
            pd.read_excel(io.BytesIO(file_bytes), sheet_name="전환_재구매")
        )
        members_df = prepare_members_dataframe(
            pd.read_excel(io.BytesIO(file_bytes), sheet_name="가입자")
        )
    except (ValueError, Exception) as exc:
        st.error(str(exc))
        return

    col1, col2 = st.columns(2)
    col1.metric("전환·재구매", f"{len(conversion_df):,}행")
    col2.metric("가입자", f"{len(members_df):,}행")
    st.success(
        "확인 완료 · "
        f"{format_month_label(conversion_df['년월'].iloc[-1])}까지"
    )

    if st.button("월간 KPI 적용", type="primary", width="stretch", key="apply_monthly"):
        apply_uploaded_file(
            file_bytes,
            MONTHLY_KPI_PATH,
            "uploaded_monthly_kpi",
            "kpi_version",
            load_monthly_conversion,
            load_monthly_members,
        )


def render_upload_panel() -> None:
    tab_sales, tab_monthly = st.tabs(["매출", "월간 KPI"])
    with tab_sales:
        render_sales_upload_panel()
    with tab_monthly:
        render_monthly_upload_panel()


def render_conversion_tab(conversion_df: pd.DataFrame) -> None:
    months = sorted(conversion_df["년월"].unique(), reverse=True)
    selected_month = st.selectbox(
        "월 선택",
        months,
        format_func=format_month_label,
        key="conversion_month",
    )

    with st.container(border=True):
        st.markdown("**지표 설명**")
        st.markdown(
            "- **첫구매 전환율**: 가입 후 **7일 이내** 구매한 비율\n"
            "- **재구매율**: 구매 후 **14일 이내** 재구매한 비율"
        )

    month_df = conversion_df[conversion_df["년월"] == selected_month].copy()
    month_avg_conversion = month_df["첫구매전환율"].mean()
    month_avg_repurchase = month_df["재구매율"].mean()

    month_index = months.index(selected_month)
    prev_conversion_delta = None
    prev_repurchase_delta = None
    if month_index < len(months) - 1:
        prev_month = months[month_index + 1]
        prev_df = conversion_df[conversion_df["년월"] == prev_month]
        if not prev_df.empty:
            prev_conversion_delta = (
                (month_avg_conversion - prev_df["첫구매전환율"].mean()) * 100
            )
            prev_repurchase_delta = (
                (month_avg_repurchase - prev_df["재구매율"].mean()) * 100
            )

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "평균 첫구매 전환율",
        format_percent(month_avg_conversion),
        delta=f"{prev_conversion_delta:.1f}%p" if prev_conversion_delta is not None else None,
    )
    col2.metric(
        "평균 재구매율",
        format_percent(month_avg_repurchase),
        delta=f"{prev_repurchase_delta:.1f}%p" if prev_repurchase_delta is not None else None,
    )
    col3.metric("집계 주차", f"{len(month_df)}주")

    chart_df = month_df.copy()
    chart_df["첫구매전환율(%)"] = chart_df["첫구매전환율"] * 100
    chart_df["재구매율(%)"] = chart_df["재구매율"] * 100

    fig = px.line(
        chart_df,
        x="주차시작",
        y=["첫구매전환율(%)", "재구매율(%)"],
        markers=True,
        title=f"{format_month_label(selected_month)} 주차별 전환·재구매 추이",
        template="plotly_white",
        labels={"value": "비율(%)", "variable": "지표"},
    )
    fig.update_layout(height=450, yaxis_title="비율(%)", hovermode="x unified")
    st.plotly_chart(fig, width="stretch")

    display_df = month_df.copy()
    display_df["주차시작"] = display_df["주차시작"].dt.strftime("%Y-%m-%d")
    display_df["첫구매전환율"] = display_df["첫구매전환율"].map(format_percent)
    display_df["재구매율"] = display_df["재구매율"].map(format_percent)
    st.dataframe(display_df, width="stretch", hide_index=True)


def render_members_tab(members_df: pd.DataFrame) -> None:
    months = sorted(members_df["년월"].unique(), reverse=True)
    selected_month = st.selectbox(
        "월 선택",
        months,
        format_func=format_month_label,
        key="members_month",
    )

    month_df = members_df[members_df["년월"] == selected_month].copy()
    latest_row = month_df.iloc[-1]
    first_row = month_df.iloc[0]
    new_members = latest_row["전체가입자"] - first_row["전체가입자"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "누적 가입자",
        f"{latest_row['전체가입자']:,.0f}명",
    )
    col2.metric("이번 달 신규", f"{new_members:,.0f}명")
    col3.metric("전체 업체수", f"{latest_row['전체업체수']:,.0f}개")
    col4.metric("업체당 평균", f"{latest_row['업체평균가입자']:.1f}명")

    trend_df = month_df.copy()
    trend_df["주간 신규 가입"] = trend_df["전체가입자"].diff()
    prior_rows = members_df[members_df["주차시작"] < trend_df["주차시작"].min()]
    if pd.isna(trend_df.iloc[0]["주간 신규 가입"]):
        base_members = prior_rows.iloc[-1]["전체가입자"] if not prior_rows.empty else 0
        trend_df.iloc[0, trend_df.columns.get_loc("주간 신규 가입")] = (
            trend_df.iloc[0]["전체가입자"] - base_members
        )

    fig_total = px.line(
        trend_df,
        x="주차시작",
        y="전체가입자",
        markers=True,
        title=f"{format_month_label(selected_month)} 누적 가입자 추이",
        template="plotly_white",
    )
    fig_total.update_layout(height=400, yaxis_tickformat=",")
    st.plotly_chart(fig_total, width="stretch")

    fig_new = px.bar(
        trend_df,
        x="주차시작",
        y="주간 신규 가입",
        text="주간 신규 가입",
        title=f"{format_month_label(selected_month)} 주간 신규 가입",
        template="plotly_white",
    )
    fig_new.update_layout(height=350, yaxis_tickformat=",")
    fig_new.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
    st.plotly_chart(fig_new, width="stretch")

    display_df = month_df.copy()
    display_df["주차시작"] = display_df["주차시작"].dt.strftime("%Y-%m-%d")
    display_df["전체가입자"] = display_df["전체가입자"].map(lambda x: f"{x:,.0f}")
    display_df["전체업체수"] = display_df["전체업체수"].map(lambda x: f"{x:,.0f}")
    display_df["업체평균가입자"] = display_df["업체평균가입자"].map(lambda x: f"{x:.1f}")
    st.dataframe(display_df, width="stretch", hide_index=True)


def render_sidebar(
    df: pd.DataFrame | None,
    daily_total_sales: pd.DataFrame | None,
) -> pd.Timestamp | None:
    st.sidebar.markdown("### 🥕 당근 매출")
    st.sidebar.caption("날짜를 고르거나 데이터를 업로드하세요.")

    tab_date, tab_upload = st.sidebar.tabs(["📅 날짜 선택", "📤 데이터 업로드"])

    with tab_upload:
        render_upload_panel()

    with tab_date:
        if df is None or daily_total_sales is None:
            st.info("데이터를 먼저 업로드해 주세요.")
            return None
        return render_date_panel(df, daily_total_sales)

    return None


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


@st.cache_data
def get_monthly_sales(df: pd.DataFrame) -> pd.DataFrame:
    monthly_sales = (
        df.groupby("년월")["매출"]
        .sum()
        .reset_index()
        .sort_values("년월")
        .reset_index(drop=True)
    )

    monthly_sales["전월매출"] = monthly_sales["매출"].shift(1)
    monthly_sales["증감률"] = (
        (monthly_sales["매출"] - monthly_sales["전월매출"])
        / monthly_sales["전월매출"]
    ) * 100

    return monthly_sales


def render_monthly_tab(
    df: pd.DataFrame,
    monthly_sales: pd.DataFrame,
    color_map: dict,
) -> None:
    months = monthly_sales["년월"].tolist()
    selected_month = st.selectbox(
        "월 선택",
        months,
        index=len(months) - 1,
        format_func=format_month_label,
        key="sales_month",
    )

    month_row = monthly_sales[monthly_sales["년월"] == selected_month].iloc[0]
    change_rate = month_row["증감률"]

    col1, col2, col3 = st.columns(3)
    col1.metric(
        f"{format_month_label(selected_month)} 매출",
        f"{month_row['매출']:,.0f} 원",
    )
    col2.metric(
        "전월 대비",
        f"{change_rate:.1f}%" if not pd.isna(change_rate) else "-",
        delta=f"{change_rate:.1f}%" if not pd.isna(change_rate) else None,
    )
    month_days = df[df["년월"] == selected_month]["날짜"].nunique()
    col3.metric("영업일 수", f"{month_days}일")

    st.subheader("월별 데이터")

    monthly_display = monthly_sales.copy()
    monthly_display["년월"] = monthly_display["년월"].map(format_month_label)
    monthly_display["매출"] = format_sales_column(monthly_display["매출"])
    monthly_display["전월매출"] = monthly_display["전월매출"].map(
        lambda x: "-" if pd.isna(x) else f"{x:,.0f}"
    )
    monthly_display["증감률"] = monthly_display["증감률"].map(
        lambda x: "-" if pd.isna(x) else f"{x:.1f}%"
    )
    st.dataframe(monthly_display, width="stretch", hide_index=True)

    fig_monthly = px.bar(
        monthly_sales,
        x="년월",
        y="매출",
        text="매출",
        title="월별 총 매출",
        template="plotly_white",
    )
    fig_monthly.update_layout(
        height=400,
        yaxis_tickformat=",",
        xaxis_tickformat="%Y-%m",
    )
    fig_monthly.update_traces(
        texttemplate="%{text:,.0f}",
        textposition="outside",
    )
    fig_monthly.update_xaxes(
        tickvals=monthly_sales["년월"],
        ticktext=[format_month_label(month) for month in monthly_sales["년월"]],
    )
    st.plotly_chart(fig_monthly, width="stretch")

    st.subheader("월별 상품 상세 분석")

    monthly_detail = df[df["년월"] == selected_month]
    monthly_product_sales = (
        monthly_detail.groupby(["상품", "분류"])["매출"]
        .sum()
        .reset_index()
        .sort_values("매출", ascending=True)
        .reset_index(drop=True)
    )

    month_product_count = len(monthly_product_sales)
    top_n_month = st.slider(
        "상위 N개 상품",
        min_value=1,
        max_value=month_product_count,
        value=min(20, month_product_count),
        key=f"monthly_top_n_{selected_month}",
    )

    monthly_chart_data = (
        monthly_product_sales
        .sort_values("매출", ascending=False)
        .head(top_n_month)
        .sort_values("매출", ascending=True)
        .reset_index(drop=True)
    )

    chart_height = max(400, len(monthly_chart_data) * 35)

    fig_month_detail = px.bar(
        monthly_chart_data,
        y="상품",
        x="매출",
        color="분류",
        color_discrete_map=color_map,
        text="매출",
        title=(
            f"{format_month_label(selected_month)} 상품별 매출 "
            f"(상위 {top_n_month}개 / 전체 {month_product_count}개)"
        ),
        template="plotly_white",
        orientation="h",
        category_orders={"상품": monthly_chart_data["상품"].tolist()},
    )
    fig_month_detail.update_layout(
        height=chart_height,
        xaxis_tickformat=",",
        showlegend=True,
        margin=dict(l=350, r=50, t=80, b=50),
        yaxis=dict(tickfont=dict(size=16)),
        xaxis=dict(tickfont=dict(size=14)),
    )
    fig_month_detail.update_traces(
        texttemplate="%{text:,.0f}",
        textposition="outside",
        textfont=dict(size=16),
    )
    st.plotly_chart(fig_month_detail, width="stretch")

    st.subheader("월별 상품 데이터")
    monthly_display_detail = monthly_chart_data.copy()
    monthly_display_detail["매출"] = format_sales_column(
        monthly_display_detail["매출"]
    )
    st.dataframe(monthly_display_detail, width="stretch", hide_index=True)


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
        일별 / 주별 / 월별 상품 매출 분석 시스템
    </p>
    """,
    unsafe_allow_html=True,
)

if Path("logo.png").exists():
    st.image("logo.png", width=200)

st.divider()

if "data_version" not in st.session_state:
    st.session_state.data_version = 0
if "kpi_version" not in st.session_state:
    st.session_state.kpi_version = 0

file_bytes = get_active_file_bytes()
monthly_bytes = get_monthly_kpi_bytes()
df = None
daily_sales = None
daily_total_sales = None
weekly_sales = None
monthly_sales = None
color_map = None
conversion_df = None
members_df = None

if file_bytes is not None:
    try:
        df = load_and_prepare_data(st.session_state.data_version, file_bytes)
        daily_sales = get_daily_sales(df)
        daily_total_sales = get_daily_total_sales(df)
        weekly_sales = get_weekly_sales(df)
        monthly_sales = get_monthly_sales(df)
        color_map = build_color_map(df["분류"].unique())
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    except Exception as exc:
        st.error(f"매출 데이터를 불러오지 못했습니다: {exc}")
        st.stop()

if monthly_bytes is not None:
    try:
        conversion_df = load_monthly_conversion(
            st.session_state.kpi_version,
            monthly_bytes,
        )
        members_df = load_monthly_members(
            st.session_state.kpi_version,
            monthly_bytes,
        )
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    except Exception as exc:
        st.error(f"월간 KPI 데이터를 불러오지 못했습니다: {exc}")
        st.stop()

selected_date = render_sidebar(df, daily_total_sales)

if df is None and conversion_df is None:
    st.warning(
        "데이터가 없습니다. 왼쪽 사이드바 **데이터 업로드** 탭에서 "
        "`data.xlsx` 또는 `monthly_kpi.xlsx`를 올려 주세요."
    )
    st.stop()

caption_parts = []
if df is not None and selected_date is not None:
    latest_date = df["날짜"].max().strftime("%Y-%m-%d")
    caption_parts.append(
        f"매출 {len(df):,}행 · 최신 {latest_date} · 선택 {selected_date.strftime('%Y-%m-%d')}"
    )
if conversion_df is not None:
    caption_parts.append(
        f"월간 KPI {format_month_label(conversion_df['년월'].max())}까지"
    )
st.caption(" · ".join(caption_parts))

selected_data = None
if df is not None and selected_date is not None:
    selected_data = daily_sales[daily_sales["날짜"] == selected_date]
    selected_data = selected_data.sort_values("매출", ascending=False)

tab_daily, tab_weekly, tab_monthly, tab_trend, tab_conversion, tab_members = st.tabs(
    ["일별 분석", "주별 분석", "월별 분석", "매출 추이", "전환·재구매", "가입자"]
)

with tab_daily:
    if selected_data is None:
        st.info("매출 데이터(`data.xlsx`)를 업로드하면 일별 분석을 볼 수 있습니다.")
    else:
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

with tab_weekly:
    if df is None:
        st.info("매출 데이터(`data.xlsx`)를 업로드하면 주별 분석을 볼 수 있습니다.")
    else:
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

with tab_monthly:
    if df is None:
        st.info("매출 데이터(`data.xlsx`)를 업로드하면 월별 분석을 볼 수 있습니다.")
    else:
        st.subheader("월간 KPI")
        render_monthly_tab(df, monthly_sales, color_map)

with tab_trend:
    if df is None:
        st.info("매출 데이터(`data.xlsx`)를 업로드하면 매출 추이를 볼 수 있습니다.")
    else:
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

        st.subheader("월별 총 매출 추이")

        fig_monthly_line = px.line(
            monthly_sales,
            x="년월",
            y="매출",
            markers=True,
            title="월별 총 매출 추이",
            template="plotly_white",
        )
        fig_monthly_line.update_layout(
            height=450,
            yaxis_tickformat=",",
            hovermode="x unified",
            xaxis_title="월",
            yaxis_title="총 매출",
        )
        fig_monthly_line.update_xaxes(
            tickvals=monthly_sales["년월"],
            ticktext=[format_month_label(month) for month in monthly_sales["년월"]],
        )
        fig_monthly_line.update_traces(
            text=monthly_sales["매출"],
            texttemplate="%{text:,.0f}",
            textposition="top center",
        )
        st.plotly_chart(fig_monthly_line, width="stretch")

with tab_conversion:
    if conversion_df is None:
        st.info("월간 KPI(`monthly_kpi.xlsx`)를 업로드하면 전환·재구매 분석을 볼 수 있습니다.")
    else:
        st.subheader("구매전환율 · 재구매율")
        render_conversion_tab(conversion_df)

with tab_members:
    if members_df is None:
        st.info("월간 KPI(`monthly_kpi.xlsx`)를 업로드하면 가입자 분석을 볼 수 있습니다.")
    else:
        st.subheader("가입자 추이")
        render_members_tab(members_df)