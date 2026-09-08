# 🚗 Mywheel 프로젝트 진행 현황 및 히스토리 리포트

> **최종 업데이트**: 2026-08-28  
> **프로젝트 위치**:  
> - Backend: `C:\Users\shiny\Mywheel\mywheel-backend`  
> - Frontend: `C:\Users\shiny\Mywheel\mywheel-frontend`

---

## 1. 🛠️ 기술 스택 & 개발 환경

* **Backend**: FastAPI, SQLAlchemy, Uvicorn, Python 3.10
* **Frontend**: React 19, Vite, React Router DOM, CSS Modules
* **Database**: PostgreSQL 16 (Docker Compose: `mywheel-postgres`, Port: `5432`)
* **DB Client Tool**: DBeaver
* **AI Engine**: Google Gemini API (`gemini-3.1-flash-image`, `gemini-3.6-flash`)
* **Image Processing**: Pillow (PIL)

---

## 2. 🗄️ 데이터베이스 스키마 현황 (PostgreSQL)

### ① `advice_logs` (AI 상담/제원 분석 기록)
차량 휠 제원 추천 및 휠 검색 결과를 저장하는 테이블입니다.

| 컬럼명 | 데이터 타입 | Null 허용 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | BIGINT | PK (Auto) | 기본키 (BIGSERIAL) |
| `user_id` | BIGINT | **O (Nullable)** | 사용자 ID (로그인 모듈 연동 전 임시 Null 허용) |
| `query_type` | VARCHAR(20) | X | 질의 유형 (`'RECOMMEND'` \| `'SEARCH'`) |
| `user_query` | TEXT | X | 사용자 입력 질문/차종/검색어 |
| `gemini_response` | TEXT | X | Gemini AI의 분석 답변 내용 |
| `created_at` | TIMESTAMP | X | 기록 생성 일시 (Default: `now()`) |

> 📌 **DB 수정 이력**: 비로그인 상태 테스트를 위해 DBeaver에서 `ALTER TABLE advice_logs ALTER COLUMN user_id DROP NOT NULL;` 적용 완료.

---

### ② `custom_synthesis_logs` (휠 사진 합성 결과 기록)
1번 API(휠 커스텀 사진 합성)의 결과 및 이미지 URL을 저장하는 테이블입니다.

| 컬럼명 | 데이터 타입 | Null 허용 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | BIGINT | PK (Auto) | 기본키 (BIGSERIAL) |
| `user_id` | BIGINT | **O (Nullable)** | 사용자 ID |
| `selected_asset_id` | VARCHAR(100) | O | 선택한 휠 ID/이름 또는 `'UPLOADED_IMAGE'` |
| `result_image_url` | TEXT | X | 생성된 합성 결과 이미지 URL (`/static/results/...`) |
| `created_at` | TIMESTAMP | X | 생성 일시 (Default: `now()`) |

---

## 3. 🔌 백엔드 API 명세 & 구현 상태

### 1) 휠 커스텀 사진 합성 API
* **Endpoint**: `POST /api/v1/custom/synthesize`
* **Content-Type**: `multipart/form-data`
* **Parameters**:
  * `original_vehicle_image` (UploadFile, 필수): 사용자 차량 사진
  * `uploaded_wheel_image` (UploadFile, 선택): 사용자 직접 업로드 휠 사진
  * `selected_asset_id` (Form str, 선택): 기본 프리셋 휠 ID/이름
* **Features**:
  * Gemini `gemini-3.1-flash-image`로 사진 합성
  * `static/results/result_{timestamp}.jpg` 로컬 저장
  * `custom_synthesis_logs` 테이블에 자동 INSERT
* **Response**:
  ```json
  {
    "result_id": 1,
    "result_image_url": "http://localhost:8000/static/results/result_1787896811396.jpg"
  }
  ```

---

### 2) 차량 휠/타이어 제원 추천 API
* **Endpoint**: `POST /api/v1/recommend/vehicle`
* **Content-Type**: `application/json`
* **Parameters**:
  * `body`: `{ "vehicle_model": "현대 아반떼 CN7" }`
  * `id` (Query, 선택): 사용자 ID
* **Features**:
  * Gemini `gemini-3.6-flash`로 차량 순정 규격 및 추천 스펙 생성 (표 + 간결한 문장)
  * `advice_logs` 테이블에 `query_type='RECOMMEND'`로 자동 INSERT
* **Response**:
  ```json
  {
    "advice_id": 1,
    "gemini_response": "현대 아반떼 CN7의 순정 규격은..."
  }
  ```

---

### 3) 휠 이름 제원 검색 API
* **Endpoint**: `POST /api/v1/search/wheel`
* **Content-Type**: `application/json`
* **Parameters**:
  * `body`: `{ "wheel_name": "BBS LM", "vehicle_model": "선택사항" }`
* **Features**:
  * Gemini `gemini-3.6-flash`로 휠 스펙 및 장착 호환성 분석 생성
  * `advice_logs` 테이블에 `query_type='SEARCH'`로 자동 INSERT
* **Response**:
  ```json
  {
    "advice_id": 2,
    "gemini_response": "BBS LM의 제조사는..."
  }
  ```

---

## 4. 💻 프론트엔드 연동 진행 현황

| 페이지 / 컴포넌트 | 연동 API | 상태 | 주요 구현 기능 |
| :--- | :--- | :---: | :--- |
| [`WheelTuning.jsx`](file:///C:/Users/shiny/Mywheel/mywheel-frontend/src/pages/custom/WheelTuning.jsx) | `POST /custom/synthesize` | **완료** | • `FormData` 기반 이미지/휠 업로드<br>• 스크롤 없는 제자리 결과 화면 전환<br>• 상단 안내 문구 & 완성 사진 표시<br>• [저장하기] 즉시 다운로드 & [다시 만들기] 초기화 |
| [`MyCarSpecs.jsx`](file:///C:/Users/shiny/Mywheel/mywheel-frontend/src/pages/custom/MyCarSpecs.jsx) | `POST /recommend/vehicle` | **대기 중** | 다음 작업 예정 (차종 입력 ➔ AI 추천 결과 뷰) |
| [`WheelSpecsSearch.jsx`](file:///C:/Users/shiny/Mywheel/mywheel-frontend/src/pages/custom/WheelSpecsSearch.jsx) | `POST /search/wheel` | **대기 중** | 다음 작업 예정 (휠 이름 검색 ➔ AI 진단 결과 뷰) |

---

## 5. 🔮 추후 계획 및 연계 사항

1. **내 차 제원 추천 (`MyCarSpecs.jsx`) & 휠 검색 (`WheelSpecsSearch.jsx`) 프론트엔드 연동**
2. **로그인/회원가입 모듈 완성 후 연계**:
   * 팀원의 로그인 파트 완료 시 `user_id`를 파라미터나 토큰 헤더에서 추출하여 `advice_logs` 및 `custom_synthesis_logs`에 저장되도록 연계
   * 마이페이지에서 사용자의 과거 합성 내역 및 상담 내역 조회 API(`GET /api/v1/history/...`) 구현
