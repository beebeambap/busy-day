# busy-day 곡 선정 체계 — 2026-05-18 기준

현재 운영 중인 자동/수동 곡 생성 흐름을 한 페이지로 정리.
세부 구현은 `compose/`, `js/`, `supabase/functions/`, `.github/workflows/` 참조.

---

## 1. 큰 그림

곡은 **세 가지 경로**로 만들어진다.

| 경로 | 트리거 | 결과 | 핵심 입력 |
|---|---|---|---|
| **A. 자동(cron)** | GitHub Actions 06:00 KST (= 21:00 UTC) | `auto` 변형 1곡 (1분 + 2분+) | 그날 날씨만 |
| **B. 수동(intent)** | 브라우저 "+ 오늘 곡 더 만들기" 클릭 | `user-HHMM-<intent>` 변형 추가 | 날씨 + intent + (선택) 장르·악기 |
| **C. 편곡(tape)** | 상세 패널 "편곡하기" 버튼 | `tape-<preset>-HHMM` 변형 추가 | 기존 곡 IR + tape preset |

모든 경로는 **동일한 generator (`compose.pipeline`)**를 거치지만 입력 파라미터가 다를 뿐이다. 동일 `(date, city_id, generator_ver)` 시드는 동일 결과 → 재현 가능.

---

## 2. 공통 파이프라인 (`compose/pipeline.py`)

```
weather(dict)
   │
   ▼
features.extract()  ─►  Features(warmth, brightness, calmness, wetness)  ∈ [0, 1]⁴
   │
   ▼  (intent 있으면)
intent.apply()      ─►  feature deltas + 강제 bias (mode, genre, bpm 등)
   │
   ▼
_decide_spec()      ─►  {key_root, mode, genre, bpm, meter, motif}
   │
   ▼
compose_ir() × 2    ─►  IR (short ~60s, long ~130s)
                          ├─ bars[].chord_degree
                          ├─ tracks.melody
                          ├─ tracks.harmony
                          ├─ tracks.bass
                          └─ tracks.percussion
```

### 2.1 시드

```python
seed = make_seed(date_iso, city_id, GENERATOR_VER)   # "v1.0.0"
```
같은 (날짜, 도시)는 코드를 바꿔도 `GENERATOR_VER` 안 올리면 같은 곡. 수동 변형은 `seed_salt`(= "user-HHMM-...")로 다른 추첨을 강제.

### 2.2 4-d Feature 공간

| feature | 영향 |
|---|---|
| `warmth` | 키 선택(D/A vs E/G), bossa_nova 가산 |
| `brightness` | mode (ionian/lydian↑, aeolian↓), folk/bossa 가산 |
| `calmness` | BPM (느림↑), ambient/lo_fi 가산, 멜로디 밀도 |
| `wetness` | jazz_ballad/lo_fi, aeolian 가산, F키 가산 |

### 2.3 결정 순서 (`_decide_spec`)

1. **mode** — `pick_mode(features)` (intent의 `mode_bias` 있으면 강제)
2. **key_root** — `pick_key(features)` (C/D/E/F/G/A/B 가중)
3. **genre** — `pick_genre(features, avoid=, preferred=, force=)`
4. **bpm** — intent의 `bpm_clamp` 있으면 그 범위에서 직접 추첨, 없으면 `pick_bpm(features, genre)` (60–112)
5. **meter** — intent의 `force_meter` 있으면 강제, 없으면 `pick_meter(genre)` (3/4, 4/4, 6/8)
6. **motif** — `motifs.json`에서 features 기반 가중 추첨

---

## 3. 경로 A — 자동 (cron)

### 3.1 트리거
- 파일: `.github/workflows/daily-compose.yml`
- 스케줄: `cron: "0 21 * * *"` (UTC) = **매일 06:00 KST**
- 호출: `python -m compose daily --city seoul --date today --variant auto`

### 3.2 동작
1. KMA (기상청) API에서 그날 서울 예보 조회 (`compose/kma.py`)
2. `pipeline.generate_pair(weather=…)` — intent **없음**, 순수 날씨 기반
3. MIDI · SVG · MusicXML · IR(json) Supabase Storage 업로드
4. `songs` 테이블에 `variant_id="auto"`로 insert

### 3.3 특징
- intent 없음 → 가장 "그날을 그대로 반영한" 기본 곡
- 매일 1행, 새벽에 조용히 추가됨

---

## 4. 경로 B — 수동 (intent picker)

### 4.1 트리거
- UI: 메인 화면 `+ 오늘 곡 더 만들기` 버튼 → intent 모달
- 입력: 무드/상황 (필수) + 장르 (선택) + 악기 (선택)

### 4.2 흐름
```
브라우저
  │  POST /functions/v1/trigger {city, date, intent_id, genre_id, instrument_id}
  ▼
Edge Function (trigger)
  │  workflow_dispatch
  ▼
GitHub Actions (daily-compose.yml)
  │  python -m compose daily --intent ... --genre ... --instrument ...
  ▼
Supabase Storage + songs.insert(variant_id="user-HHMM-<intent>")
  │
  ▼
브라우저 polling (findVariant) → 도착 시 상세 패널 자동 오픈
```

### 4.3 Intent 카탈로그 (12종)

**감정 무드 (수동/자동 공용)**:

| id | 한글 | 핵심 효과 |
|---|---|---|
| `calm` | 차분하게 | ambient 가산, BPM 62-76 |
| `warm` | 따뜻하게 | warmth +0.30, BPM 72-92 |
| `wistful` | 쓸쓸하게 | dorian 강제, brightness -0.30 |
| `lively` | 활기차게 | folk 가산, BPM 86-100 |
| `after_rain` | 비 온 뒤처럼 | mixolydian 강제, wetness +0.30 |
| `sleep` | 잠들기 전 | ambient, BPM 60-70 |

**상황 무드 (수동 전용 — auto cron은 06시 1회뿐이라 의미 없음)**:

| id | 한글 | 핵심 효과 |
|---|---|---|
| `dawn` | 새벽 | ambient, BPM 50-65 |
| `commute` | 출근길 | brightness↑, BPM 90-104 |
| `nap` | 낮잠 | ambient, BPM 58-72 |
| `focus` | 작업 중 | bossa_nova 회피, BPM 74-90 |
| `walk` | 산책 | folk + 4/4 강제, BPM 114-124 |

### 4.4 장르 / 악기 오버라이드
- **장르**: `force_genre`로 hard-pin (intent의 `preferred_genre`보다 우선)
- **악기**: 멜로디 트랙의 음색만 교체 (장르의 화성/리듬은 그대로). 12종 (피아노/EP/나일론/바이올린/비올라/첼로/플루트/틴휘슬/하프/마림바/뮤직박스/호른)
- 둘 다 "자동"이면 intent 기본값 적용

---

## 5. 경로 C — 편곡 (Weather Tape)

### 5.1 컨셉
이미 만들어진 곡의 **멜로디 핏치·코드 진행을 보존**하고 장르·보이싱·악기·BPM·그루브만 그 날 날씨에 맞는 "테마"로 재해석. 카세트 테이프에 같은 곡을 다른 앨범 톤으로 재녹음하는 느낌.

### 5.2 트리거
- UI: 상세 패널에 `편곡하기` 버튼 — **그날 날씨가 등록된 preset 조건에 맞을 때만** 표시
- 기존 변형이 이미 편곡(tape)이면 버튼 숨김 (재귀 방지)

### 5.3 현재 활성 Preset (2종)

| Preset | 트리거 조건 | 변형 |
|---|---|---|
| **🌞 clear_hot** (맑고 더운 날) | `temp ≥ 25°C AND cloud ≤ 30% AND precip ≤ 0.5mm` | bossa_nova / 9th 보이싱 / 나일론 / BPM ×1.08 / 그루브 직선 |
| **🌧 rain** (비 오는 날) | `precip ≥ 0.3mm AND cloud ≥ 50%` | jazz_ballad / 9th 보이싱 / 피아노 / BPM ×0.88 / 스윙 1.50 + 18ms behind-the-beat |

Preset 전체 정의: `compose/tapes/presets.py`. JS 측 매칭 기준: `js/tapes.js` (서버와 동일 규칙).

### 5.4 흐름
```
브라우저 (편곡하기 클릭)
  │  POST /functions/v1/trigger_tape {source_song_id, tape_id}
  ▼
Edge Function (trigger_tape)
  │  workflow_dispatch → tape-compose.yml
  ▼
python -m compose tape --source-id ... --tape ... --variant tape-<id>-HHMM
  │  ├─ 원본 IR 다운로드 (Storage)
  │  ├─ transform_ir(): 멜로디 보존, 화성/베이스/타악기 재합성
  │  ├─ swing / groove delay 적용
  │  └─ MIDI·SVG 재렌더
  ▼
songs.insert(variant_id="tape-<id>-HHMM", tape_id, source_song_id)
```

---

## 6. 데이터 모델 (`songs` 테이블 핵심 컬럼)

| 컬럼 | 용도 |
|---|---|
| `variant_id` | `auto` / `user-HHMM-<intent>` / `tape-<preset>-HHMM` |
| `intent_id` | intent 사용 시 ID (예: `walk`) |
| `instrument_id` | 사용자 지정 멜로디 악기 |
| `tape_id`, `source_song_id` | 편곡일 때 원곡 참조 |
| `pin_type` | `legendary` / `worst` / null — 사용자 평가 핀 |
| `paths` (jsonb) | Storage 키들 (`mid_short`, `mid_long`, `svg`, `musicxml`, `ir_short`, …) |
| `title`, `notes` | 사용자 메모 |

워스트 핀은 달력 기본 뷰에서 자동 숨김, "👎 워스트" 필터 시만 노출.

---

## 7. 모르거나 안 하는 것

- **AI 호출 없음** — 전부 결정론적 규칙 + seeded RNG. 같은 입력 → 같은 곡.
- **실시간 합성 아님** — Python으로 MIDI·SVG 만들고 저장, 브라우저는 Tone.js로 MIDI를 재생만.
- **자동 편곡 안 함** — Tape preset 조건이 맞아도 cron이 알아서 편곡을 추가로 만들지는 않음. 항상 사용자가 명시적으로 트리거.

---

## 8. 향후 검토 메모

- SNOW / COLD / FOG / STORM preset 추가 (`weather-tapes-arrangement-system-v1.md` 참조)
- 악보에 2-스테이브 (멜로디 + 왼손) — 현재는 멜로디 + 코드 심볼만
- 편곡 변이를 악보 title_suffix로 시각화 (현재 원곡/편곡 악보가 멜로디만 보여 거의 동일)
