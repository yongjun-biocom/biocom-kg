# 바이오컴 지식 그래프 프로토타입

유기산 검사 결과 → 경로 기반 추론 → 건기식/식단 추천

## 빠른 시작

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. Neo4j 실행 (선택 — 없으면 인메모리 모드로 동작)
```bash
docker-compose up -d
```

### 3. 데이터 적재 (Neo4j 사용 시)
```bash
python src/graph_loader.py
```

### 4. API 키 설정
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```
또는 `biocom-kg/` 디렉토리에 `.env` 파일 생성:
```
ANTHROPIC_API_KEY=sk-ant-...
```

### 5. 데모 UI 실행
```bash
streamlit run src/app.py
```
브라우저에서 http://localhost:8501 접속

## 구조

```
biocom-kg/
├── docker-compose.yml       # Neo4j 컨테이너
├── requirements.txt
├── data/
│   ├── nodes.json           # 노드 111개
│   ├── edges.json           # 엣지 164개
│   └── neo4j_import.cypher  # Cypher 임포트 스크립트
└── src/
    ├── graph_loader.py      # 데이터 → Neo4j 적재
    ├── path_engine.py       # 경로 추론 엔진 (Neo4j + 인메모리 폴백)
    ├── llm_bridge.py        # 그래프 결과 → Claude API
    └── app.py               # Streamlit 데모 UI
```

## 추론 경로

### 건기식 추천
```
마커 → [INVOLVES_ENZYME] → 효소 → [COFACTOR_OF] → 영양소 → [CONTAINS] → 건기식
마커 → [REQUIRES_NUTRIENT] → 영양소 → [CONTAINS] → 건기식
```

### 식단 추천
```
마커 → [RELATES_TO_CONCERN] → 관심사 → [RECOMMENDS] → 식단라인
```

### 교차 감지
복수 마커에서 같은 영양소에 도달하면 자동으로 교차로 감지됩니다.

## Neo4j 브라우저
http://localhost:7474 (ID: neo4j / PW: biocom2024)
