import pandas as pd
import plotly.express as px
import streamlit as st

# 1. 데이터 불러오기
df = pd.read_excel("datax.xlsx")
#df = pd.read_excel(r"C:\Users\jinye\OneDrive - 주식회사 소도몰\당근\data.xlsx")
# 2. 기본 정리 (결측값 제거)
df = df.dropna(subset=["상품", "매출", "분류"])
df = df.sort_values(by="매출", ascending=False)

categories = df["분류"].unique()

colors = px.colors.qualitative.Set2

color_map = {
    cat: colors[i % len(colors)]
    for i, cat in enumerate(categories)
}

st.set_page_config(
    page_title="일별 상품 매출 분석",
    layout="wide"
)

st.title("일별 상품 매출 분석")

# 필요한 컬럼만 사용
df = df.dropna(subset=["날짜", "상품", "매출"])

# 날짜 변환
# 날짜 형식이 20250401 형태라고 가정
df["날짜"] = pd.to_datetime(
    df["날짜"].astype(str),
    format="%Y%m%d",
    errors="coerce"
)

# 날짜 변환 실패 제거
df = df.dropna(subset=["날짜"])

# 매출 숫자 처리
df["매출"] = (
    df["매출"]
    .astype(str)
    .str.replace(",", "", regex=False)
)

df["매출"] = pd.to_numeric(df["매출"], errors="coerce")

# 0 이하 제거
df = df[df["매출"] > 0]

# =====================================================
# 일별 상품 매출 집계
# =====================================================

daily_sales = (
    df.groupby(["날짜", "상품"])["매출"]
    .sum()
    .reset_index()
)

# =====================================================
# 최근 날짜 목록
# =====================================================

date_list = (
    daily_sales["날짜"]
    .drop_duplicates()
    .sort_values(ascending=False)
    .head(20)
)
# 문자열 변환
date_options = [
    d.strftime("%Y-%m-%d")
    for d in date_list
]

# =====================================================
# 오른쪽 날짜 선택 탭
# =====================================================

selected_date = st.sidebar.radio(
    "날짜 선택",
    date_options
)

selected_date = pd.to_datetime(selected_date)

# =====================================================
# 선택 날짜 데이터
# =====================================================

selected_data = daily_sales[
    daily_sales["날짜"] == selected_date
]

# 매출 정렬
selected_data = selected_data.sort_values(
    "매출",
    ascending=False
)
# =====================================================
# 그래프
# =====================================================

fig = px.bar(
    selected_data,
    x="상품",
    y="매출",
    color="상품",
    title=f"{selected_date.strftime('%Y-%m-%d')} 상품별 매출",
    text="매출",
    template="plotly_white"
)

fig.update_layout(
    height=700,
    xaxis_tickangle=-30,
    yaxis_tickformat=",",
    showlegend=False,
    xaxis=dict(
        tickfont=dict(size=18)
    )
)

fig.update_traces(
    texttemplate='%{text:,.0f}',
    textposition='outside',
    textfont=dict(size=20)
)

st.plotly_chart(
    fig,
    use_container_width=True
)

# =====================================================
# 데이터 테이블
# =====================================================

st.subheader("데이터")

display_df = selected_data.copy()

display_df["매출"] = display_df["매출"].map(
    lambda x: f"{x:,.0f}"
)

st.dataframe(
    display_df,
    use_container_width=True
)

##########################
#일별 라인 그래프
#########################

daily_total_sales = (
    df.groupby("날짜")["매출"]
    .sum()
    .reset_index()
)
st.subheader("일별 총 매출 추이")

fig_daily_line = px.line(
    daily_total_sales,
    x="날짜",
    y="매출",
    markers=True,
    title="일별 총 매출 추이",
    template="plotly_white"
)

fig_daily_line.update_layout(
    height=500,
    yaxis_tickformat=",",
    hovermode="x unified"
)

fig_daily_line.update_traces(
    text=daily_total_sales["매출"],
    texttemplate='%{text:,.0f}',
    textposition="top center"
)

st.plotly_chart(
    fig_daily_line,
    use_container_width=True
)



# =====================================================
# 주별 총 매출 집계
# =====================================================

# 날짜를 주 단위로 변환
# 각 주의 시작일(Monday 기준) 생성
df["주차"] = (
    df["날짜"]
    .dt.strftime('%Y-%U주차')
)

# 주별 총 매출 집계
weekly_sales = (
    df.groupby("주차")["매출"]
    .sum()
    .reset_index()
)

# =====================================================
# 전주 대비 증감률 계산
# =====================================================

weekly_sales["전주매출"] = weekly_sales["매출"].shift(1)

weekly_sales["증감률"] = (
    (
        weekly_sales["매출"]
        - weekly_sales["전주매출"]
    )
    / weekly_sales["전주매출"]
) * 100

# =====================================================
# 주별 총 매출 그래프
# =====================================================

st.subheader("주별 총 매출 추이")

fig_weekly = px.line(
    weekly_sales,
    x="주차",
    y="매출",
    markers=True,
    title="주별 총 매출 추이",
    template="plotly_white"
)

fig_weekly.update_layout(
    height=500,
    yaxis_tickformat=",",
    hovermode="x unified",
    xaxis_title="주차",
    yaxis_title="총 매출"
)

# 데이터 라벨 추가
fig_weekly.update_traces(
    text=weekly_sales["매출"],
    texttemplate='%{text:,.0f}',
    textposition="top center"
)

# 그래프 출력
st.plotly_chart(
    fig_weekly,
    use_container_width=True
)

# =====================================================
# KPI 영역
# =====================================================

st.subheader("주간 KPI")

# 최신 주 데이터
latest_week = weekly_sales.iloc[-1]

# 증감률 표시용
change_rate = latest_week["증감률"]

if pd.isna(change_rate):
    change_text = "-"
else:
    change_text = f"{change_rate:.1f}%"

# KPI 표시
col1, col2 = st.columns(2)

col1.metric(
    "이번 주 매출",
    f"{latest_week['매출']:,.0f} 원"
)

col2.metric(
    "전주 대비",
    change_text
)

# =====================================================
# 주별 데이터 테이블
# =====================================================

st.subheader("주별 데이터")

weekly_display = weekly_sales.copy()


weekly_display["매출"] = (
    weekly_display["매출"]
    .map(lambda x: f"{x:,.0f}")
)

weekly_display["전주매출"] = (
    weekly_display["전주매출"]
    .map(lambda x: f"{x:,.0f}")
)

weekly_display["증감률"] = (
    weekly_display["증감률"]
    .map(
        lambda x:
        "-" if pd.isna(x)
        else f"{x:.1f}%"
    )
)

st.dataframe(
    weekly_display,
    use_container_width=True
)

# =====================================================
# 주별 상품 상세 분석
# =====================================================

st.subheader("주별 상품 상세 분석")

# 주 선택
selected_week = st.selectbox(
    "주 선택",
    weekly_sales["주차"]
)

# 선택한 주 데이터 필터링
weekly_detail = df[
    df["주차"] == selected_week
]

# 상품별 매출 집계
weekly_product_sales = (
    weekly_detail
    .groupby("상품")["매출"]
    .sum()
    .reset_index()
)

# 매출 기준 정렬
weekly_product_sales = (
    weekly_product_sales
    .sort_values("매출", ascending=False)
    .reset_index(drop=True)
)

# =====================================================
# 주별 상품 BAR 그래프
# =====================================================

fig_week_detail = px.bar(
    weekly_product_sales,
    y="상품",
    x="매출",
    color="상품",
    text="매출",
    title=f"{selected_week} 상품별 매출",
    template="plotly_white",
    orientation="h"
)

fig_week_detail.update_layout(
    height=1100,
    #xaxis_tickangle=-30,
    xaxis_tickformat=",",
    showlegend=False,
        margin=dict(
        l=350,
        r=50,
        t=80,
        b=50
    ),

    yaxis=dict(
        tickfont=dict(size=16)
    ),

    xaxis=dict(
        tickfont=dict(size=14)
    )

)

fig_week_detail.update_traces(
    texttemplate='%{text:,.0f}',
    textposition='outside',
    textfont=dict(size=16)
)

# 그래프 출력
st.plotly_chart(
    fig_week_detail,
    use_container_width=True
)

# =====================================================
# 상세 데이터 테이블
# =====================================================

st.subheader("주별 상품 데이터")

weekly_display_detail = weekly_product_sales.copy()

weekly_display_detail["매출"] = (
    weekly_display_detail["매출"]
    .map(lambda x: f"{x:,.0f}")
)

st.dataframe(
    weekly_display_detail,
    use_container_width=True
)