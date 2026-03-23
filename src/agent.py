"""
agent.py — 지식 그래프와 연결된 Claude Tool Use 에이전트
"""

import json
import os
import anthropic
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        try:
            api_key.encode("ascii")
        except UnicodeEncodeError:
            raise ValueError("ANTHROPIC_API_KEY에 잘못된 문자가 포함되어 있습니다. .env 파일로 설정해주세요.")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


# ──────────────────────────────────────────────
# 도구 정의
# ──────────────────────────────────────────────

TOOLS = [
    {
        "name": "get_all_markers",
        "description": "유기산 검사에서 측정하는 모든 마커 목록을 반환합니다.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "find_marker",
        "description": "마커 이름, 약어, ID로 마커를 검색합니다. 예: '숙신산', 'SUCC', 'BM-OA-018', '피루브산'",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색어"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_marker_detail",
        "description": "마커의 상세 정보를 반환합니다. 해석 텍스트, 메커니즘, 관련 효소/영양소, 마커간 관계 포함.",
        "input_schema": {
            "type": "object",
            "properties": {
                "marker_id": {"type": "string", "description": "마커 ID (예: BM-OA-018)"}
            },
            "required": ["marker_id"],
        },
    },
    {
        "name": "get_supplement_recommendation",
        "description": "마커 ID 목록으로 건기식 추천 경로를 탐색합니다. 근거 체인, 필요 영양소, 용량 포함.",
        "input_schema": {
            "type": "object",
            "properties": {
                "marker_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "마커 ID 목록"
                }
            },
            "required": ["marker_ids"],
        },
    },
    {
        "name": "get_diet_recommendation",
        "description": "마커 ID 목록으로 식단/생활습관 추천 경로를 탐색합니다. 관심사 허브 경유.",
        "input_schema": {
            "type": "object",
            "properties": {
                "marker_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "마커 ID 목록"
                }
            },
            "required": ["marker_ids"],
        },
    },
    {
        "name": "get_cross_analysis",
        "description": "복수 마커 간 공통 교차 영양소를 찾습니다. 우선 보충해야 할 영양소 파악에 유용합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "marker_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "마커 ID 목록 (2개 이상)"
                }
            },
            "required": ["marker_ids"],
        },
    },
    {
        "name": "get_product_info",
        "description": "건기식 또는 식단라인의 상세 정보를 반환합니다. 성분, 용량, 병용 주의사항, 시너지 관계 포함.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {"type": "string", "description": "제품명 (예: 바이오밸런스, 메타드림)"}
            },
            "required": ["product_name"],
        },
    },
    {
        "name": "get_nutrient_interactions",
        "description": "영양소 간 시너지/길항 관계를 조회합니다. 함께 먹으면 좋은 것, 피해야 할 조합 등.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nutrient_name": {"type": "string", "description": "영양소 이름 (예: 철, 비타민C, 마그네슘)"}
            },
            "required": ["nutrient_name"],
        },
    },
    {
        "name": "run_full_analysis",
        "description": "마커 목록에 대해 건기식+식단+교차+제약+억제수단 전체 분석을 한 번에 실행합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "marker_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "마커 ID 목록"
                },
                "directions": {
                    "type": "object",
                    "description": "마커별 방향 {'BM-OA-018': '↑', 'BM-OA-035': '↓'}",
                    "additionalProperties": {"type": "string"}
                }
            },
            "required": ["marker_ids"],
        },
    },
]


# ──────────────────────────────────────────────
# 도구 실행기
# ──────────────────────────────────────────────

class AgentToolExecutor:
    def __init__(self, engine):
        self.engine = engine

    def execute(self, tool_name, tool_input):
        try:
            if tool_name == "get_all_markers":
                return self._get_all_markers()
            elif tool_name == "find_marker":
                return self._find_marker(tool_input["query"])
            elif tool_name == "get_marker_detail":
                return self._get_marker_detail(tool_input["marker_id"])
            elif tool_name == "get_supplement_recommendation":
                return self._get_supplement_recommendation(tool_input["marker_ids"])
            elif tool_name == "get_diet_recommendation":
                return self._get_diet_recommendation(tool_input["marker_ids"])
            elif tool_name == "get_cross_analysis":
                return self._get_cross_analysis(tool_input["marker_ids"])
            elif tool_name == "get_product_info":
                return self._get_product_info(tool_input["product_name"])
            elif tool_name == "get_nutrient_interactions":
                return self._get_nutrient_interactions(tool_input["nutrient_name"])
            elif tool_name == "run_full_analysis":
                return self._run_full_analysis(
                    tool_input["marker_ids"],
                    tool_input.get("directions", {})
                )
            else:
                return f"알 수 없는 도구: {tool_name}"
        except Exception as e:
            return f"오류: {e}"

    def _get_all_markers(self):
        markers = self.engine.get_all_markers()
        if not markers:
            return "마커 목록을 불러올 수 없습니다."
        return "\n".join(
            f"{m['id']} | {m['name']} | {m.get('mid','')} | {m.get('character','')}"
            for m in markers
        )

    def _find_marker(self, query):
        found = self.engine.find_marker(query)
        if not found:
            return f"'{query}'에 해당하는 마커를 찾지 못했습니다."
        # 상세 필드 제거 후 반환
        filtered = [
            {k: v for k, v in m.items()
             if k not in ("high_interpretation", "mechanism", "discordance_notes") and v}
            for m in found
        ]
        return json.dumps(filtered, ensure_ascii=False, indent=2)

    def _get_marker_detail(self, marker_id):
        detail = self.engine.get_marker_detail(marker_id)
        if not detail:
            return f"마커 '{marker_id}'를 찾을 수 없습니다."
        return json.dumps(detail, ensure_ascii=False, indent=2)

    def _get_supplement_recommendation(self, marker_ids):
        supps = self.engine.recommend_supplements(marker_ids)
        if not supps:
            return "연결된 건기식 경로가 없습니다."
        lines = []
        for p in supps:
            lines.append(f"\n[{p['reach']}] {p['supplement_name']}")
            if p.get("concept"):
                lines.append(f"  구성: {p['concept']}")
            if p.get("dosage"):
                lines.append(f"  복용: {p['dosage']}")
            lines.append(f"  경로: {p['chain']}")
            lines.append(f"  영양소: {', '.join(p['nutrients'])}")
            if p.get("evidence_level"):
                lines.append(f"  근거: {p['evidence_level']}")
        return "\n".join(lines)

    def _get_diet_recommendation(self, marker_ids):
        diets = self.engine.recommend_diets(marker_ids)
        if not diets:
            return "연결된 식단 경로가 없습니다."
        lines = []
        for d in diets:
            line = f"- {d['diet_name']} ← {d['concern_name']}"
            if d.get("condition"):
                line += f" (조건: {d['condition']})"
            if d.get("context"):
                line += f"\n  근거: {d['context']}"
            lines.append(line)
        return "\n".join(lines)

    def _get_cross_analysis(self, marker_ids):
        cross = self.engine.detect_cross(marker_ids)
        if not cross:
            return "교차 영양소가 없습니다."
        lines = []
        for c in cross:
            lines.append(f"교차영양소: {c['nutrient_name']}")
            lines.append(f"  관련 마커: {', '.join(c['markers'])}")
            lines.append(f"  포함 건기식: {', '.join(c['supplements'])}")
        return "\n".join(lines)

    def _get_product_info(self, product_name):
        found = self.engine.get_product_info(product_name)
        if not found:
            return f"'{product_name}' 제품을 찾지 못했습니다."
        return json.dumps(found, ensure_ascii=False, indent=2)

    def _get_nutrient_interactions(self, nutrient_name):
        rows = self.engine.get_nutrient_interactions(nutrient_name)
        if not rows:
            return f"'{nutrient_name}'의 상호작용 정보가 없습니다."
        lines = [
            f"{r['name']} ↔ {r['other_name']}: {r.get('interaction_type')} — {r.get('description')}"
            for r in rows
        ]
        return "\n".join(lines)

    def _run_full_analysis(self, marker_ids, directions):
        result = self.engine.run_all(marker_ids, directions or {})
        return json.dumps(result, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────
# 에이전트 루프
# ──────────────────────────────────────────────

SYSTEM_PROMPT = """
너는 바이오컴의 기능의학 지식 그래프 AI 에이전트다.

역할:
- 사용자 질문을 이해하고 지식 그래프 도구를 호출해서 정확한 답변을 제공한다.
- 그래프에 없는 내용은 추측하지 않는다.
- 마커 이름이 나오면 먼저 find_marker로 ID를 확인한다.
- 복잡한 질문은 여러 도구를 순서대로 호출해 단계적으로 답한다.

답변 규칙:
1. 그래프 결과만 설명한다. 결과에 없는 내용을 추가하지 않는다.
2. 근거 수준에 따라 톤을 조절한다:
   - 확정: "~입니다"
   - 강함: "~인 것으로 보입니다"
   - 중간: "~일 가능성이 있습니다"
   - 참고: "~라는 연구가 있습니다"
3. 도달 강도에 따라 추천 강도를 조절한다:
   - 핵심: 강하게 추천
   - 보조: 보조적 언급
4. 병용 주의사항(제품 제약)이 있으면 반드시 언급한다.
5. 고객이 이해할 수 있는 쉬운 표현을 사용한다.
6. 근거 체인(마커 → 효소 → 영양소 → 건기식)을 명시한다.
"""


def run_agent(user_message, engine, conversation_history=None):
    client = _get_client()
    executor = AgentToolExecutor(engine)

    if conversation_history is None:
        conversation_history = []

    messages = conversation_history + [{"role": "user", "content": user_message}]

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            final_text = "".join(
                block.text for block in response.content if hasattr(block, "text")
            )
            messages.append({"role": "assistant", "content": response.content})
            return final_text, messages

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = executor.execute(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})
