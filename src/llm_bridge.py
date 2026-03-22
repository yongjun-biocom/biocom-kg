"""
llm_bridge.py — 그래프 추론 결과 → Claude API → 자연어 해석
"""

import json
import os
import anthropic

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


SYSTEM_PROMPT = """
너는 바이오컴의 AI 건강 어드바이저다.
아래 규칙을 반드시 따른다:

1. 그래프 추론 결과만 설명한다. 결과에 없는 내용을 추가하지 않는다.
2. 근거 수준에 따라 톤을 조절한다:
   - 확정: "~입니다"
   - 강함: "~인 것으로 보입니다"
   - 중간: "~일 가능성이 있습니다"
   - 참고: "~라는 연구가 있습니다"
3. 도달 강도에 따라 추천 강도를 조절한다:
   - 핵심: 강하게 추천
   - 보조: 보조적 언급
   - 간접: 필요 시에만 언급
4. 고객이 이해할 수 있는 쉬운 표현을 사용한다.
5. 구조화된 답변을 작성한다:
   - 검사 결과 요약 (어떤 마커가 활성화되었는지)
   - 건기식 추천 (근거 체인 포함)
   - 식단/생활습관 추천
   - 교차 분석 결과 (해당 시)
"""


def generate_explanation(graph_results: dict) -> str:
    """
    graph_results: path_engine.PathEngine.run_all() 반환값
    """
    client = _get_client()

    user_content = (
        "아래 검사 결과 분석 데이터를 바탕으로 고객에게 전달할 해석과 추천을 작성해주세요.\n\n"
        + json.dumps(graph_results, ensure_ascii=False, indent=2)
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text


def generate_explanation_stream(graph_results: dict):
    """스트리밍 버전 — Streamlit st.write_stream 에 사용"""
    client = _get_client()

    user_content = (
        "아래 검사 결과 분석 데이터를 바탕으로 고객에게 전달할 해석과 추천을 작성해주세요.\n\n"
        + json.dumps(graph_results, ensure_ascii=False, indent=2)
    )

    with client.messages.stream(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        for text in stream.text_stream:
            yield text


if __name__ == "__main__":
    sample = {
        "activated_markers": [
            {"id": "BM-OA-018", "name": "숙신산", "direction": "↑", "classification": "에너지 대사"}
        ],
        "supplement_paths": [
            {"product": "바이오밸런스", "reach": "핵심", "chain": "숙신산↑ → SDH → 비타민B2 → 바이오밸런스", "nutrients": ["비타민 B2", "CoQ10"]}
        ],
        "diet_paths": [{"diet": "시그니처", "concern": "에너지·활력"}],
        "cross_nutrients": [],
    }
    print(generate_explanation(sample))
