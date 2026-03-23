"""
graph_loader.py — nodes.json / edges.json 를 읽어 Neo4j에 적재
"""

import json
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+ssc://5b472a40.databases.neo4j.io")
NEO4J_USER = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

LABEL_MAP = {
    "검사": "Exam",
    "유기산마커": "OrganicAcidMarker",
    "효소": "Enzyme",
    "영양소": "Nutrient",
    "건기식": "Supplement",
    "식단라인": "DietLine",
    "관심사": "Concern",
    "분류": "Classification",
}

REL_MAP = {
    "E01_측정": "MEASURES",
    "E02_마커간": "MARKER_RELATION",
    "E08_관련효소": "INVOLVES_ENZYME",
    "E09_필요영양소": "REQUIRES_NUTRIENT",
    "E10_조효소": "COFACTOR_OF",
    "E11_소속": "BELONGS_TO",
    "E12_관련관심사": "RELATES_TO_CONCERN",
    "E13_포함": "CONTAINS",
    "E16_추천": "RECOMMENDS",
    "E17_억제수단": "SUPPRESSES",
    "E18_제품제약": "PRODUCT_CONSTRAINT",
    "E19_영양소상호작용": "NUTRIENT_INTERACTION",
}


def load_data(data_dir: str):
    nodes_path = os.path.join(data_dir, "nodes.json")
    edges_path = os.path.join(data_dir, "edges.json")
    with open(nodes_path, encoding="utf-8") as f:
        nodes = json.load(f)
    with open(edges_path, encoding="utf-8") as f:
        edges = json.load(f)
    return nodes, edges


def clear_db(session):
    session.run("MATCH (n) DETACH DELETE n")
    print("기존 데이터 삭제 완료")


def create_nodes(session, nodes):
    for node in nodes:
        node_type = node.get("type", "")
        label = LABEL_MAP.get(node_type, "Node")
        props = {k: v for k, v in node.items() if v is not None}
        session.run(
            f"MERGE (n:{label} {{id: $id}}) SET n += $props",
            id=node["id"],
            props=props,
        )
    print(f"노드 {len(nodes)}개 적재 완료")


def create_edges(session, edges):
    created = 0
    skipped = 0
    for edge in edges:
        rel_type = REL_MAP.get(edge["type"])
        if not rel_type:
            skipped += 1
            continue
        props = {k: v for k, v in edge.items() if k not in ("type", "source", "target") and v is not None}
        session.run(
            f"""
            MATCH (a {{id: $src}}), (b {{id: $tgt}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r += $props
            """,
            src=edge["source"],
            tgt=edge["target"],
            props=props,
        )
        created += 1
    print(f"엣지 {created}개 적재, {skipped}개 스킵")


def create_indexes(session):
    labels = list(LABEL_MAP.values())
    for label in labels:
        try:
            session.run(f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.id)")
        except Exception:
            pass
    print("인덱스 생성 완료")


def verify(session):
    node_count = session.run("MATCH (n) RETURN count(n) as c").single()["c"]
    edge_count = session.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
    print(f"검증: 노드 {node_count}개, 엣지 {edge_count}개")
    return node_count, edge_count


def run(data_dir: str = None, clear: bool = True):
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    data_dir = os.path.abspath(data_dir)

    nodes, edges = load_data(data_dir)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session() as session:
        if clear:
            clear_db(session)
        create_indexes(session)
        create_nodes(session, nodes)
        create_edges(session, edges)
        node_count, edge_count = verify(session)

    driver.close()
    return node_count, edge_count


if __name__ == "__main__":
    run()
