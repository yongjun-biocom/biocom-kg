"""
app.py — 바이오컴 지식 그래프 데모 UI
탭 1: 그래프 시각화  |  탭 2: AI 에이전트 대화
"""

import json
import os
import sys
import tempfile

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.dirname(__file__))
from path_engine import PathEngine
from graph_viz import load_data, build_network, get_path_node_ids
from agent import run_agent

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

st.set_page_config(
    page_title="바이오컴 지식 그래프",
    page_icon="🧬",
    layout="wide",
)

# ── 공유 리소스 ──────────────────────────────

@st.cache_resource
def get_engine():
    return PathEngine(DATA_DIR)

@st.cache_data
def get_graph_data():
    return load_data(DATA_DIR)

@st.cache_data
def get_markers():
    nodes, _ = get_graph_data()
    return [n for n in nodes if n.get("type") == "유기산마커"]

engine     = get_engine()
all_nodes, all_edges = get_graph_data()
nodes_dict = {n["id"]: n for n in all_nodes}
markers    = get_markers()

# ── 탭 레이아웃 ──────────────────────────────

st.title("🧬 바이오컴 지식 그래프")

tab_viz, tab_agent = st.tabs(["📊 그래프 시각화", "🤖 AI 에이전트"])


# ════════════════════════════════════════════
# 탭 1: 그래프 시각화
# ════════════════════════════════════════════

with tab_viz:
    col_ctrl, col_graph = st.columns([1, 3])

    with col_ctrl:
        st.subheader("필터")
        all_types = sorted({n.get("type", "") for n in all_nodes if n.get("type")})
        selected_types = st.multiselect(
            "표시할 노드 타입",
            options=all_types,
            default=[t for t in all_types if t not in ("분류", "유형레이블")],
        )

        st.divider()
        st.subheader("마커 경로 강조")

        # 중분류별 마커 그룹
        groups = {}
        for m in markers:
            edges_to_cls = [e for e in all_edges if e["source"] == m["id"] and e["type"] == "E11_소속"]
            cat = nodes_dict.get(edges_to_cls[0]["target"], {}).get("name", "기타") if edges_to_cls else "기타"
            groups.setdefault(cat, []).append(m)

        highlight_markers = []
        marker_directions = {}
        for cat, mlist in sorted(groups.items()):
            with st.expander(cat, expanded=False):
                for m in mlist:
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        if st.checkbox(m["name"], key=f"viz_{m['id']}"):
                            highlight_markers.append(m["id"])
                    with col2:
                        if m["id"] in highlight_markers:
                            dir_val = st.selectbox("", ["↑", "↓"], key=f"dir_{m['id']}", label_visibility="collapsed")
                            marker_directions[m["id"]] = dir_val

        render_btn = st.button("🔍 그래프 렌더링", type="primary", use_container_width=True)

    with col_graph:
        # 범례
        st.markdown("""
        <div style='display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px;font-size:12px;'>
        <span style='background:#6C8EBF;padding:2px 7px;border-radius:3px;color:white'>◆ 검사</span>
        <span style='background:#D6B656;padding:2px 7px;border-radius:3px;color:white'>● 마커</span>
        <span style='background:#82B366;padding:2px 7px;border-radius:3px;color:white'>■ 효소</span>
        <span style='background:#AE4132;padding:2px 7px;border-radius:3px;color:white'>◉ 영양소</span>
        <span style='background:#9C27B0;padding:2px 7px;border-radius:3px;color:white'>★ 자사건기식</span>
        <span style='background:#CE93D8;padding:2px 7px;border-radius:3px;color:white'>★ 다빈치랩</span>
        <span style='background:#00BCD4;padding:2px 7px;border-radius:3px;color:white'>▲ 식단</span>
        <span style='background:#FF9800;padding:2px 7px;border-radius:3px;color:white'>⬡ 관심사</span>
        <span style='background:#26C6DA;padding:2px 7px;border-radius:3px;color:white'>⬡ 대사경로</span>
        <span style='background:#FF5722;padding:2px 7px;border-radius:3px;color:white'>🔴 강조경로</span>
        </div>
        """, unsafe_allow_html=True)

        if render_btn or "graph_html" not in st.session_state:
            with st.spinner("그래프 렌더링 중..."):
                highlight_ids = set()
                if highlight_markers:
                    highlight_ids = get_path_node_ids(nodes_dict, all_edges, highlight_markers)

                net = build_network(
                    all_nodes, all_edges,
                    highlight_ids=highlight_ids,
                    filter_types=selected_types or None,
                    height="660px",
                )
                tmp_path = os.path.join(tempfile.gettempdir(), "biocom_graph.html")
                net.save_graph(tmp_path)
                with open(tmp_path, encoding="utf-8") as f:
                    st.session_state["graph_html"] = f.read()

        if "graph_html" in st.session_state:
            components.html(st.session_state["graph_html"], height=680, scrolling=False)

        # 경로 요약 (마커 선택 시)
        if highlight_markers:
            results = engine.run_all(highlight_markers, marker_directions)
            c1, c2 = st.columns(2)
            with c1:
                if results["supplement_paths"]:
                    st.markdown("**💊 건기식 추천 경로**")
                    for p in results["supplement_paths"]:
                        icon = {"핵심": "🔴", "보조": "🟡", "간접": "⚪"}.get(p["reach"], "⚪")
                        with st.container(border=True):
                            st.markdown(f"{icon} **{p['product']}** ({p['reach']})")
                            if p.get("dosage"):
                                st.caption(f"복용: {p['dosage']}")
                            st.caption(f"`{p['chain']}`")
            with c2:
                if results["diet_paths"]:
                    st.markdown("**🥗 식단 추천**")
                    seen = set()
                    for d in results["diet_paths"]:
                        diet_node = nodes_dict.get(d.get("diet_id", ""), {})
                        if d["diet"] not in seen and diet_node.get("label") != "Exam":
                            seen.add(d["diet"])
                            st.markdown(f"- **{d['diet']}** ← _{d['concern']}_")

                if results["cross_nutrients"]:
                    st.markdown("**🔗 교차 영양소**")
                    for c in results["cross_nutrients"]:
                        st.success(f"**{c['nutrient']}** — {', '.join(c['markers'])}")

                if results.get("product_constraints"):
                    st.markdown("**⚠️ 병용 주의**")
                    for c in results["product_constraints"]:
                        if c["constraint_type"] == "총량주의":
                            st.warning(f"{c['from']} + {c['to']}: {c.get('description', '')}")
                        elif c["constraint_type"] == "시너지":
                            st.info(f"{c['from']} + {c['to']}: {c.get('description', '')}")


# ════════════════════════════════════════════
# 탭 2: AI 에이전트 대화
# ════════════════════════════════════════════

with tab_agent:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if not api_key:
        st.warning("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        st.code("biocom-kg/.env 파일에 ANTHROPIC_API_KEY=sk-ant-... 를 추가하세요.")
    else:
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []
        if "agent_messages" not in st.session_state:
            st.session_state.agent_messages = []

        # 예시 질문
        examples = [
            "숙신산이 높으면 어떤 건기식을 먹어야 해?",
            "피루브산과 숙신산이 동시에 높을 때 교차 영양소는?",
            "바이오밸런스 성분이랑 복용법 알려줘",
            "HVA가 낮을 때 경로와 추천을 설명해줘",
            "메타드림이랑 바이오밸런스 같이 먹어도 돼?",
            "HPHPA가 높으면 어떻게 해야 해?",
            "철분이랑 같이 먹으면 안 되는 영양소는?",
            "에너지 대사 마커들 목록 보여줘",
        ]

        st.caption("예시 질문:")
        cols = st.columns(4)
        for i, ex in enumerate(examples):
            with cols[i % 4]:
                if st.button(ex, key=f"ex_{i}", use_container_width=True):
                    st.session_state["pending_input"] = ex

        st.divider()

        # 대화 기록 표시
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        pending = st.session_state.pop("pending_input", None)
        user_input = st.chat_input("마커, 건기식, 식단에 대해 무엇이든 물어보세요") or pending

        if user_input:
            with st.chat_message("user"):
                st.markdown(user_input)
            st.session_state.chat_history.append({"role": "user", "content": user_input})

            with st.chat_message("assistant"):
                with st.spinner("지식 그래프 탐색 중..."):
                    response_text, updated_messages = run_agent(
                        user_input, engine, st.session_state.agent_messages
                    )
                    st.session_state.agent_messages = updated_messages
                st.markdown(response_text)

            st.session_state.chat_history.append({"role": "assistant", "content": response_text})
            st.rerun()

        if st.session_state.chat_history:
            if st.button("🗑️ 대화 초기화"):
                st.session_state.chat_history = []
                st.session_state.agent_messages = []
                st.rerun()
