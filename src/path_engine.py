"""
path_engine.py — Neo4j Cypher 기반 경로 추론 엔진
"""

import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+ssc://5b472a40.databases.neo4j.io")
NEO4J_USER = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

SUPP_TYPES = ["건기식_자사", "건기식_다빈치랩"]


class PathEngine:
    def __init__(self, data_dir=None):  # data_dir은 하위호환성 유지용 (무시됨)
        self._driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        print("[PathEngine] Neo4j 연결 완료")

    def _run(self, query, **params):
        with self._driver.session() as session:
            return session.run(query, **params).data()

    # ─────────────────────────────────────────
    # 마커 조회
    # ─────────────────────────────────────────

    def get_all_markers(self):
        return self._run(
            "MATCH (n:OrganicAcidMarker) "
            "RETURN n.id AS id, n.name AS name, n.mid AS mid, n.character AS character "
            "ORDER BY n.id"
        )

    def find_marker(self, query):
        q = query.lower()
        rows = self._run(
            "MATCH (n:OrganicAcidMarker) "
            "WHERE toLower(coalesce(n.name,'')) CONTAINS $q "
            "   OR toLower(coalesce(n.id,'')) CONTAINS $q "
            "   OR toLower(coalesce(n.mid,'')) CONTAINS $q "
            "   OR toLower(coalesce(n.alias,'')) CONTAINS $q "
            "RETURN n",
            q=q,
        )
        return [dict(r["n"]) for r in rows]

    def get_marker_detail(self, marker_id):
        rows = self._run(
            """
            MATCH (m {id: $id})
            OPTIONAL MATCH (m)-[:INVOLVES_ENZYME]->(e:Enzyme)
            OPTIONAL MATCH (m)-[rn:REQUIRES_NUTRIENT]->(n:Nutrient)
            OPTIONAL MATCH (m)-[rc:RELATES_TO_CONCERN]->(c:Concern)
            RETURN m,
                   collect(distinct e.name)                                          AS enzymes,
                   collect(distinct {name: n.name, evidence: rn.evidence_level, basis: rn.basis}) AS nutrients,
                   collect(distinct {name: c.name, evidence: rc.evidence_level})     AS concerns
            """,
            id=marker_id,
        )
        if not rows:
            return None
        r = rows[0]
        m = dict(r["m"])
        return {
            **m,
            "related_enzymes": [e for e in r["enzymes"] if e],
            "required_nutrients": [n for n in r["nutrients"] if n.get("name")],
            "related_concerns": [c for c in r["concerns"] if c.get("name")],
            "marker_relations": self.get_marker_relations(marker_id),
        }

    def get_marker_relations(self, marker_id):
        rows = self._run(
            """
            MATCH (m {id: $id})-[r:MARKER_RELATION]-(other)
            RETURN other.id AS other_id, other.name AS other_name,
                   r.relation_type AS relation_type, r.note AS note,
                   startNode(r).id AS src_id
            """,
            id=marker_id,
        )
        return [
            {
                "other_id": r["other_id"],
                "other_name": r["other_name"],
                "relation_type": r["relation_type"],
                "note": r["note"],
                "direction": "→" if r["src_id"] == marker_id else "←",
            }
            for r in rows
        ]

    # ─────────────────────────────────────────
    # 건기식 추천
    # ─────────────────────────────────────────

    def recommend_supplements(self, marker_ids, marker_directions=None):
        by_supp = {}
        for mid in marker_ids:
            rows = self._run(
                """
                MATCH (m {id: $id})
                MATCH path = (m)-[:INVOLVES_ENZYME|REQUIRES_NUTRIENT|COFACTOR_OF|CONTAINS*1..5]->(s)
                WHERE s.type IN $supp_types
                WITH s,
                     [n IN nodes(path) | coalesce(n.name, n.id)]                          AS chain_names,
                     [n IN nodes(path) WHERE n.type = '영양소' | n.name]                   AS nutrients,
                     length(path)                                                           AS depth,
                     [rel IN relationships(path)
                       WHERE rel.evidence_level IS NOT NULL | rel.evidence_level][0]       AS evidence
                RETURN s.id AS supplement_id, s.name AS supplement_name,
                       s.concept AS concept, s.dosage AS dosage,
                       depth, chain_names, nutrients, evidence
                ORDER BY depth
                LIMIT 50
                """,
                id=mid,
                supp_types=SUPP_TYPES,
            )
            for r in rows:
                sid = r["supplement_id"]
                depth = r["depth"]
                reach = "핵심" if depth <= 2 else ("보조" if depth <= 3 else "간접")
                if sid not in by_supp or depth < by_supp[sid]["steps"]:
                    by_supp[sid] = {
                        "supplement_id": sid,
                        "supplement_name": r["supplement_name"],
                        "concept": r["concept"],
                        "dosage": r["dosage"],
                        "steps": depth,
                        "reach": reach,
                        "chain": " → ".join(r["chain_names"]),
                        "nutrients": list(dict.fromkeys(n for n in r["nutrients"] if n)),
                        "evidence_level": r["evidence"],
                        "markers": [mid],
                    }
                else:
                    if mid not in by_supp[sid]["markers"]:
                        by_supp[sid]["markers"].append(mid)
                    for n in r["nutrients"]:
                        if n and n not in by_supp[sid]["nutrients"]:
                            by_supp[sid]["nutrients"].append(n)

        return sorted(by_supp.values(), key=lambda x: x["steps"])

    # ─────────────────────────────────────────
    # 식단 추천
    # ─────────────────────────────────────────

    def recommend_diets(self, marker_ids):
        seen, results = set(), []
        for mid in marker_ids:
            rows = self._run(
                """
                MATCH (m {id: $id})-[ce:RELATES_TO_CONCERN]->(c:Concern)-[de:RECOMMENDS]->(d)
                RETURN c.id AS concern_id, c.name AS concern_name,
                       c.customer_question AS concern_question,
                       d.id AS diet_id, d.name AS diet_name,
                       de.condition AS condition,
                       ce.evidence_level AS evidence_level,
                       ce.context AS context
                """,
                id=mid,
            )
            for r in rows:
                key = (r["concern_id"], r["diet_id"])
                if key not in seen:
                    seen.add(key)
                    results.append(dict(r))
        return results

    # ─────────────────────────────────────────
    # 교차 영양소
    # ─────────────────────────────────────────

    def detect_cross(self, marker_ids):
        if len(marker_ids) < 2:
            return []
        rows = self._run(
            """
            MATCH (m)-[:INVOLVES_ENZYME|REQUIRES_NUTRIENT|COFACTOR_OF*1..3]->(n:Nutrient)
            WHERE m.id IN $ids
            WITH n, collect(distinct m.name) AS markers
            WHERE size(markers) >= 2
            OPTIONAL MATCH (n)-[:CONTAINS]->(s)
            RETURN n.id AS nutrient_id, n.name AS nutrient_name,
                   markers, collect(distinct s.name) AS supplements
            """,
            ids=marker_ids,
        )
        return [
            {
                "nutrient_id": r["nutrient_id"],
                "nutrient_name": r["nutrient_name"],
                "markers": r["markers"],
                "supplements": [s for s in r["supplements"] if s],
            }
            for r in rows
        ]

    # ─────────────────────────────────────────
    # 제품 제약
    # ─────────────────────────────────────────

    def detect_constraints(self, supplement_ids):
        if not supplement_ids:
            return []
        rows = self._run(
            """
            MATCH (a)-[r:PRODUCT_CONSTRAINT]->(b)
            WHERE a.id IN $ids AND b.id IN $ids
            RETURN a.name AS from, b.name AS to,
                   r.constraint_type AS constraint_type,
                   r.nutrient AS nutrient,
                   r.total_amount AS total_amount,
                   r.description AS description
            """,
            ids=supplement_ids,
        )
        return [dict(r) for r in rows]

    # ─────────────────────────────────────────
    # 억제수단
    # ─────────────────────────────────────────

    def get_suppression(self, marker_id):
        rows = self._run(
            """
            MATCH (m {id: $id})-[r:SUPPRESSES]->(p)
            RETURN p.id AS product_id, p.name AS product_name, r.pathogen_ref AS pathogen
            """,
            id=marker_id,
        )
        return [dict(r) for r in rows]

    # ─────────────────────────────────────────
    # 제품 정보
    # ─────────────────────────────────────────

    def get_product_info(self, product_name):
        q = product_name.lower()
        rows = self._run(
            """
            MATCH (p)
            WHERE p.label IN ['Supplement', 'DietLine']
              AND toLower(coalesce(p.name, '')) CONTAINS $q
            OPTIONAL MATCH (n:Nutrient)-[cn:CONTAINS]->(p)
            OPTIONAL MATCH (p)-[cr:PRODUCT_CONSTRAINT]-(other)
            RETURN p,
                   collect(distinct {name: n.name, amount: cn.amount, unit: cn.unit}) AS nutrients,
                   collect(distinct {product: other.name, type: cr.constraint_type,
                                     description: cr.description})                    AS interactions
            """,
            q=q,
        )
        results = []
        for r in rows:
            p = dict(r["p"])
            results.append({
                **p,
                "nutrients": [n for n in r["nutrients"] if n.get("name")],
                "interactions": [i for i in r["interactions"] if i.get("product")],
            })
        return results

    # ─────────────────────────────────────────
    # 영양소 상호작용
    # ─────────────────────────────────────────

    def get_nutrient_interactions(self, nutrient_name):
        q = nutrient_name.lower()
        rows = self._run(
            """
            MATCH (n:Nutrient)
            WHERE toLower(coalesce(n.name, '')) CONTAINS $q
            MATCH (n)-[r:NUTRIENT_INTERACTION]-(other:Nutrient)
            RETURN n.name AS name, other.name AS other_name,
                   r.interaction_type AS interaction_type, r.description AS description
            """,
            q=q,
        )
        return [dict(r) for r in rows]

    # ─────────────────────────────────────────
    # 전체 분석
    # ─────────────────────────────────────────

    def run_all(self, marker_ids, marker_directions=None):
        if marker_directions is None:
            marker_directions = {mid: "↑" for mid in marker_ids}

        activated = []
        for mid in marker_ids:
            rows = self._run("MATCH (n {id: $id}) RETURN n", id=mid)
            if rows:
                n = dict(rows[0]["n"])
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

        suppression = []
        for mid in marker_ids:
            marker_rows = self._run("MATCH (n {id: $id}) RETURN n.name AS name", id=mid)
            marker_name = marker_rows[0]["name"] if marker_rows else mid
            for s in self.get_suppression(mid):
                suppression.append({**s, "marker": marker_name})

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
                {
                    "nutrient": c["nutrient_name"],
                    "markers": c["markers"],
                    "supplements": c.get("supplements", []),
                }
                for c in cross
            ],
            "product_constraints": constraints,
            "suppression_paths": suppression,
        }

    def close(self):
        self._driver.close()


if __name__ == "__main__":
    import json
    engine = PathEngine()
    r = engine.run_all(["BM-OA-018", "BM-OA-004"])
    with open("test_out.json", "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    print("OK → test_out.json")
    engine.close()
