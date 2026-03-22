"""
path_engine.py — 마커 → 건기식 / 식단 / 교차 경로 추론 엔진 (인메모리)
"""

import json
import os
from collections import defaultdict, deque

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def load_graph(data_dir=None):
    if data_dir is None:
        data_dir = DATA_DIR
    data_dir = os.path.abspath(data_dir)
    with open(os.path.join(data_dir, "nodes.json"), encoding="utf-8") as f:
        raw_nodes = json.load(f)
    with open(os.path.join(data_dir, "edges.json"), encoding="utf-8") as f:
        edges = json.load(f)
    nodes = {n["id"]: n for n in raw_nodes}
    return nodes, edges


# ──────────────────────────────────────────────
# 내부 BFS 경로 탐색
# ──────────────────────────────────────────────

SUPP_RELS  = {"E08_관련효소", "E09_필요영양소", "E10_조효소", "E13_포함"}
DIET_RELS  = {"E12_관련관심사", "E16_추천"}
SUPP_TYPES = {"건기식_자사", "건기식_다빈치랩"}
DIET_TYPE  = "식단라인"


def _build_adj(edges, allowed_rels):
    adj = defaultdict(list)
    for e in edges:
        if e["type"] in allowed_rels:
            adj[e["source"]].append((e["target"], e))
    return adj


def _bfs_to_target_type(start_id, adj, nodes, target_types, max_depth=5):
    """BFS: start → target_type 노드까지 모든 최단 경로 탐색"""
    # (node_id, path_nodes, path_edges, depth)
    queue = deque([(start_id, [start_id], [], 0)])
    results = []
    visited_at_depth = defaultdict(lambda: 999)

    while queue:
        cur, path_nodes, path_edges, depth = queue.popleft()
        if depth > max_depth:
            continue
        cur_type = nodes.get(cur, {}).get("type", "")
        if cur != start_id and cur_type in target_types:
            results.append((path_nodes, path_edges, depth))
            continue  # 더 깊이 탐색 불필요
        if depth >= max_depth:
            continue
        for nxt, edge in adj.get(cur, []):
            if visited_at_depth[nxt] >= depth + 1:
                visited_at_depth[nxt] = depth + 1
                queue.append((nxt, path_nodes + [nxt], path_edges + [edge], depth + 1))

    return results


# ──────────────────────────────────────────────
# 1. 건기식 추천
# ──────────────────────────────────────────────

def get_supplement_paths(nodes, edges, marker_id):
    adj = _build_adj(edges, SUPP_RELS)
    paths = _bfs_to_target_type(marker_id, adj, nodes, SUPP_TYPES)

    by_supp = {}
    for path_nodes, path_edges, depth in paths:
        sid = path_nodes[-1]
        reach = "핵심" if depth <= 2 else ("보조" if depth <= 3 else "간접")

        chain_names = [nodes.get(n, {}).get("name", n) for n in path_nodes]
        nutrients = [nodes.get(n, {}).get("name", n)
                     for n in path_nodes if nodes.get(n, {}).get("type") == "영양소"]
        evidence = next(
            (e.get("evidence_level") for e in path_edges if e.get("evidence_level")),
            None
        )

        if sid not in by_supp or depth < by_supp[sid]["steps"]:
            by_supp[sid] = {
                "supplement_id": sid,
                "supplement_name": nodes.get(sid, {}).get("name", sid),
                "concept": nodes.get(sid, {}).get("concept"),
                "dosage": nodes.get(sid, {}).get("dosage"),
                "steps": depth,
                "reach": reach,
                "chain": " → ".join(chain_names),
                "nutrients": list(dict.fromkeys(nutrients)),
                "evidence_level": evidence,
            }
        else:
            # 기존보다 영양소 추가
            for n in nutrients:
                if n not in by_supp[sid]["nutrients"]:
                    by_supp[sid]["nutrients"].append(n)

    return sorted(by_supp.values(), key=lambda x: x["steps"])


# ──────────────────────────────────────────────
# 2. 식단 추천
# ──────────────────────────────────────────────

def get_diet_paths(nodes, edges, marker_id):
    concern_edges = [e for e in edges if e["source"] == marker_id and e["type"] == "E12_관련관심사"]
    results = []
    seen = set()
    for ce in concern_edges:
        cid = ce["target"]
        diet_edges = [e for e in edges if e["source"] == cid and e["type"] == "E16_추천"]
        for de in diet_edges:
            did = de["target"]
            key = (cid, did)
            if key in seen:
                continue
            seen.add(key)
            results.append({
                "concern_id": cid,
                "concern_name": nodes.get(cid, {}).get("name", cid),
                "concern_question": nodes.get(cid, {}).get("customer_question"),
                "diet_id": did,
                "diet_name": nodes.get(did, {}).get("name", did),
                "condition": de.get("condition"),
                "evidence_level": ce.get("evidence_level"),
                "context": ce.get("context"),
            })
    return results


# ──────────────────────────────────────────────
# 3. 교차 영양소 감지
# ──────────────────────────────────────────────

def get_marker_nutrients(nodes, edges, marker_id):
    adj = _build_adj(edges, SUPP_RELS)
    paths = _bfs_to_target_type(marker_id, adj, nodes, {"영양소"}, max_depth=3)
    return {path_nodes[-1] for path_nodes, _, _ in paths}


def get_cross_nutrients(nodes, edges, marker_ids):
    if len(marker_ids) < 2:
        return []

    marker_nutrients = {mid: get_marker_nutrients(nodes, edges, mid) for mid in marker_ids}
    all_nutrients = set().union(*marker_nutrients.values())

    results = []
    for nid in all_nutrients:
        involved = [mid for mid, nset in marker_nutrients.items() if nid in nset]
        if len(involved) >= 2:
            supps = [e["target"] for e in edges if e["source"] == nid and e["type"] == "E13_포함"]
            results.append({
                "nutrient_id": nid,
                "nutrient_name": nodes.get(nid, {}).get("name", nid),
                "markers": [nodes.get(m, {}).get("name", m) for m in involved],
                "supplements": [nodes.get(s, {}).get("name", s) for s in supps],
            })
    return results


# ──────────────────────────────────────────────
# 4. 제품 제약 (병용주의/시너지)
# ──────────────────────────────────────────────

def get_product_constraints(nodes, edges, supplement_ids):
    """추천된 건기식 목록 간의 제약/시너지 관계"""
    sid_set = set(supplement_ids)
    results = []
    for e in edges:
        if e["type"] == "E18_제품제약" and e["source"] in sid_set and e["target"] in sid_set:
            results.append({
                "from": nodes.get(e["source"], {}).get("name", e["source"]),
                "to": nodes.get(e["target"], {}).get("name", e["target"]),
                "constraint_type": e.get("constraint_type"),
                "nutrient": e.get("nutrient"),
                "total_amount": e.get("total_amount"),
                "description": e.get("description"),
            })
    return results


# ──────────────────────────────────────────────
# 5. 억제수단 (장내 병원균 관련)
# ──────────────────────────────────────────────

def get_suppression_paths(nodes, edges, marker_id):
    results = []
    for e in edges:
        if e["type"] == "E17_억제수단" and e["source"] == marker_id:
            pid = e["target"]
            results.append({
                "product_id": pid,
                "product_name": nodes.get(pid, {}).get("name", e.get("product_name", pid)),
                "pathogen": e.get("pathogen_ref"),
            })
    return results


# ──────────────────────────────────────────────
# 6. 마커간 관계
# ──────────────────────────────────────────────

def get_marker_relations(nodes, edges, marker_id):
    results = []
    for e in edges:
        if e["type"] == "E02_마커간" and (e["source"] == marker_id or e["target"] == marker_id):
            other_id = e["target"] if e["source"] == marker_id else e["source"]
            results.append({
                "other_id": other_id,
                "other_name": nodes.get(other_id, {}).get("name", other_id),
                "relation_type": e.get("relation_type"),
                "note": e.get("note"),
                "direction": "→" if e["source"] == marker_id else "←",
            })
    return results


# ──────────────────────────────────────────────
# PathEngine 공개 API
# ──────────────────────────────────────────────

class PathEngine:
    def __init__(self, data_dir=None):
        self.data_dir = os.path.abspath(data_dir or DATA_DIR)
        self._nodes, self._edges = load_graph(self.data_dir)
        print(f"[PathEngine] 노드 {len(self._nodes)}개, 엣지 {len(self._edges)}개 로드")

    def recommend_supplements(self, marker_ids, marker_directions=None):
        all_paths = {}
        for mid in marker_ids:
            for p in get_supplement_paths(self._nodes, self._edges, mid):
                sid = p["supplement_id"]
                p.setdefault("markers", [])
                if sid not in all_paths or p["steps"] < all_paths[sid]["steps"]:
                    p["markers"] = [mid]
                    all_paths[sid] = p
                else:
                    if mid not in all_paths[sid]["markers"]:
                        all_paths[sid]["markers"].append(mid)
        return sorted(all_paths.values(), key=lambda x: x["steps"])

    def recommend_diets(self, marker_ids):
        seen, results = set(), []
        for mid in marker_ids:
            for p in get_diet_paths(self._nodes, self._edges, mid):
                key = (p["diet_id"], p["concern_id"])
                if key not in seen:
                    seen.add(key)
                    results.append(p)
        return results

    def detect_cross(self, marker_ids):
        return get_cross_nutrients(self._nodes, self._edges, marker_ids)

    def detect_constraints(self, supplement_ids):
        return get_product_constraints(self._nodes, self._edges, supplement_ids)

    def get_suppression(self, marker_id):
        return get_suppression_paths(self._nodes, self._edges, marker_id)

    def get_marker_relations(self, marker_id):
        return get_marker_relations(self._nodes, self._edges, marker_id)

    def run_all(self, marker_ids, marker_directions=None):
        if marker_directions is None:
            marker_directions = {mid: "↑" for mid in marker_ids}

        activated = []
        for mid in marker_ids:
            n = self._nodes.get(mid, {})
            activated.append({
                "id": mid,
                "name": n.get("name", mid),
                "direction": marker_directions.get(mid, "↑"),
                "classification": n.get("mid", ""),
                "character": n.get("character", ""),
                "high_interpretation": n.get("high_interpretation", ""),
                "mechanism": n.get("mechanism", ""),
            })

        supps = self.recommend_supplements(marker_ids, marker_directions)
        diets = self.recommend_diets(marker_ids)
        cross = self.detect_cross(marker_ids)

        supp_ids = [p["supplement_id"] for p in supps]
        constraints = self.detect_constraints(supp_ids)

        # 억제수단 (장내 마커)
        suppression = []
        for mid in marker_ids:
            for s in self.get_suppression(mid):
                suppression.append({**s, "marker": self._nodes.get(mid, {}).get("name", mid)})

        return {
            "activated_markers": activated,
            "supplement_paths": [
                {
                    "product": p["supplement_name"],
                    "concept": p.get("concept"),
                    "dosage": p.get("dosage"),
                    "reach": p["reach"],
                    "chain": p["chain"],
                    "nutrients": p["nutrients"],
                    "evidence_level": p.get("evidence_level"),
                }
                for p in supps
            ],
            "diet_paths": [
                {
                    "diet_id": d["diet_id"],
                    "diet": d["diet_name"],
                    "concern": d["concern_name"],
                    "condition": d.get("condition"),
                    "evidence_level": d.get("evidence_level"),
                    "context": d.get("context"),
                }
                for d in diets
            ],
            "cross_nutrients": [
                {"nutrient": c["nutrient_name"], "markers": c["markers"], "supplements": c.get("supplements", [])}
                for c in cross
            ],
            "product_constraints": constraints,
            "suppression_paths": suppression,
        }

    def close(self):
        pass


if __name__ == "__main__":
    engine = PathEngine()
    r = engine.run_all(["BM-OA-018", "BM-OA-004"])
    with open("test_out.json", "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    print("OK → test_out.json")
