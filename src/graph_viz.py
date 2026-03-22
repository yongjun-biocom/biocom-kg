"""
graph_viz.py — pyvis 기반 지식 그래프 시각화
"""

import json
import os
from pyvis.network import Network

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# 노드 타입별 색상 & 모양
NODE_STYLE = {
    "검사":           {"color": "#6C8EBF", "shape": "diamond", "size": 30},
    "유기산마커":      {"color": "#D6B656", "shape": "dot",     "size": 18},
    "효소":           {"color": "#82B366", "shape": "box",     "size": 16},
    "영양소":         {"color": "#AE4132", "shape": "ellipse", "size": 20},
    "건기식_자사":    {"color": "#9C27B0", "shape": "star",    "size": 28},
    "건기식_다빈치랩":{"color": "#CE93D8", "shape": "star",    "size": 24},
    "식단라인":       {"color": "#00BCD4", "shape": "triangle","size": 24},
    "관심사":         {"color": "#FF9800", "shape": "hexagon", "size": 22},
    "분류":           {"color": "#9E9E9E", "shape": "dot",     "size": 12},
    "대사경로":       {"color": "#26C6DA", "shape": "database","size": 20},
    "유형레이블":     {"color": "#EF5350", "shape": "square",  "size": 18},
}

DEFAULT_STYLE = {"color": "#CCCCCC", "shape": "dot", "size": 12}

# 엣지 타입별 색상
EDGE_STYLE = {
    "E01_측정":           {"color": "#AAAAAA", "label": "측정"},
    "E08_관련효소":       {"color": "#82B366", "label": "관련효소"},
    "E09_필요영양소":     {"color": "#AE4132", "label": "필요영양소"},
    "E10_조효소":         {"color": "#D6B656", "label": "조효소"},
    "E11_소속":           {"color": "#9E9E9E", "label": "소속"},
    "E12_관련관심사":     {"color": "#FF9800", "label": "관련관심사"},
    "E13_포함":           {"color": "#9C27B0", "label": "포함"},
    "E16_추천":           {"color": "#00BCD4", "label": "추천"},
    "E17_억제수단":       {"color": "#F44336", "label": "억제"},
    "E18_제품제약":       {"color": "#FF5722", "label": "제약"},
    "E19_영양소상호작용": {"color": "#4CAF50", "label": "상호작용"},
    "E02_마커간":         {"color": "#607D8B", "label": "마커관계"},
}


def load_data(data_dir=None):
    if data_dir is None:
        data_dir = DATA_DIR
    with open(os.path.join(data_dir, "nodes.json"), encoding="utf-8") as f:
        nodes = json.load(f)
    with open(os.path.join(data_dir, "edges.json"), encoding="utf-8") as f:
        edges = json.load(f)
    return nodes, edges


def build_network(
    nodes,
    edges,
    highlight_ids: set = None,
    filter_types: list = None,
    height="700px",
) -> Network:
    """
    pyvis Network 객체 생성
    highlight_ids: 강조할 노드 ID 집합 (경로 탐색 결과)
    filter_types: 표시할 노드 타입 목록 (None이면 전체)
    """
    net = Network(
        height=height,
        width="100%",
        bgcolor="#1a1a2e",
        font_color="white",
        directed=True,
    )
    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "stabilization": {"iterations": 100},
        "barnesHut": {
          "gravitationalConstant": -8000,
          "springLength": 120,
          "springConstant": 0.04
        }
      },
      "interaction": {
        "hover": true,
        "navigationButtons": true,
        "keyboard": true
      },
      "edges": {
        "smooth": {"type": "curvedCW", "roundness": 0.2},
        "arrows": {"to": {"enabled": true, "scaleFactor": 0.5}}
      }
    }
    """)

    highlight_ids = highlight_ids or set()
    filter_types_set = set(filter_types) if filter_types else None

    # 노드 추가
    node_ids_added = set()
    for node in nodes:
        ntype = node.get("type", "")
        if filter_types_set and ntype not in filter_types_set:
            continue

        style = NODE_STYLE.get(ntype, DEFAULT_STYLE)
        is_highlight = node["id"] in highlight_ids

        label = node.get("name", node["id"])
        title = f"<b>{label}</b><br>ID: {node['id']}<br>타입: {ntype}"
        for k, v in node.items():
            if k not in ("id", "name", "type") and v:
                title += f"<br>{k}: {v}"

        net.add_node(
            node["id"],
            label=label,
            title=title,
            color={"background": "#FF5722" if is_highlight else style["color"],
                   "border": "#FFFFFF" if is_highlight else style["color"],
                   "highlight": {"background": "#FF5722", "border": "#FFFFFF"}},
            shape=style["shape"],
            size=style["size"] * (1.6 if is_highlight else 1),
            font={"size": 13 if is_highlight else 11, "bold": is_highlight},
            borderWidth=3 if is_highlight else 1,
        )
        node_ids_added.add(node["id"])

    # 엣지 추가
    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        if src not in node_ids_added or tgt not in node_ids_added:
            continue
        estyle = EDGE_STYLE.get(edge["type"], {"color": "#555555", "label": edge["type"]})
        is_highlight = src in highlight_ids and tgt in highlight_ids
        net.add_edge(
            src, tgt,
            title=estyle["label"],
            label=estyle["label"] if is_highlight else "",
            color={"color": "#FF9800" if is_highlight else estyle["color"],
                   "opacity": 1.0 if is_highlight else 0.5},
            width=3 if is_highlight else 1,
        )

    return net


def render_to_html(net: Network, output_path: str) -> str:
    """HTML 파일로 저장 후 경로 반환"""
    net.save_graph(output_path)
    return output_path


def get_path_node_ids(nodes_dict, edges, marker_ids: list) -> set:
    """마커에서 건기식/식단까지 경로 상의 모든 노드 ID 수집"""
    from collections import deque

    path_rels = {"E08_관련효소", "E09_필요영양소", "E10_조효소", "E13_포함", "E12_관련관심사", "E16_추천"}
    adj = {}
    for e in edges:
        if e["type"] in path_rels:
            adj.setdefault(e["source"], []).append(e["target"])

    visited = set(marker_ids)
    queue = deque(marker_ids)
    while queue:
        cur = queue.popleft()
        for nxt in adj.get(cur, []):
            if nxt not in visited:
                visited.add(nxt)
                queue.append(nxt)
    return visited
