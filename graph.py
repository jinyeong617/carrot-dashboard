from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# 1. 데이터 불러오기 (저장소 루트의 data.xlsx — dailygraph.py와 동일)
df = pd.read_excel(r"C:\Users\jinye\OneDrive - 주식회사 소도몰\당근\data.xlsx")
# 2. 기본 정리 (결측값 제거)
df = df.dropna(subset=["상품", "매출", "분류"])

# 3. 매출 숫자형 변환 (혹시 문자열일 경우 대비)
df["매출"] = pd.to_numeric(df["매출"], errors="coerce")

# 4. 매출 기준 정렬
df = df.sort_values(by="매출", ascending=False)

categories = df["분류"].unique()

colors = px.colors.qualitative.Set2

color_map = {
    cat: colors[i % len(colors)]
    for i, cat in enumerate(categories)
}

# =========================
# 1. 전체 상품 매출 그래프
# =========================
df = df[df["매출"] > 0]
fig1 = px.bar(
    df,
    y="상품",
    x="매출",
    orientation="h",
    color="분류",
    color_discrete_map=color_map,
    title="상품별 매출",
    text="매출",
    template="plotly_white",
    hover_data={
    "매출": ":,",
    "상품": True,
    "분류": True
}
)

fig1.update_layout(
    height=1000,
    yaxis={'categoryorder': 'total descending'},
    xaxis_tickformat=",",
    bargap=0.15
    
)

fig1.update_traces(
    texttemplate='%{text:,}',
    textposition="outside",
    cliponaxis=False
)

fig1.show()



# =========================
# 2. 분류별 총 매출
# =========================
category_sales = df.groupby("분류")["매출"].sum().reset_index()

fig2 = px.bar(
    category_sales,
    x="분류",
    y="매출",
    color="분류",
    color_discrete_map=color_map,
    title="분류별 총 매출",
    text="매출",
    template="plotly_white",
    hover_data={
        "매출": ":,",
        "분류": True}
)

fig2.update_traces(
    texttemplate='%{text:,}',
    textposition="outside",
    textfont=dict(size=20)
)

fig2.update_layout(
    yaxis_tickformat=",",
    xaxis=dict(
        tickfont=dict(size=16))
)


fig2.show()


# =========================
# 3. TOP 10 상품
# =========================
top10 = df.nlargest(10, "매출")

fig3 = px.bar(
    top10,
    x="상품",
    y="매출",
    color="분류",
    color_discrete_map=color_map,
    title="TOP 10 상품",
    text="매출",
    template="plotly_white",
    hover_data={
    "매출": ":,",
    "상품": True,
    "분류": True
}
)

fig3.update_layout(
    height=700,
    xaxis_tickangle=-45,
    yaxis_tickformat=",",
    xaxis=dict(
        tickfont=dict(size=16))
)

fig3.update_traces(
    texttemplate='%{text:,}',
    textposition="outside",
    textfont=dict(size=20)
)

fig3.show()





fig1.write_html("상품별_매출.html")
fig2.write_html("분류별_매출.html")
fig3.write_html("top10_매출.html")