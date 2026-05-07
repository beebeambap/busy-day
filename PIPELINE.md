# busy-day — 동작 로직 & 비용 노트

`DESIGN.md` 의 보조 문서. (1) Supabase 무료/유료 경계, (2) KMA 호출→작곡 파이프라인,
(3) AI 가 어디에 들어가고/안 들어가는지를 운영 관점에서 정리.

---

## 1. Supabase 무료 한도와 유료 전환 시점

(2026년 5월 기준 Supabase 공개 요금제 — 정확한 수치는 변동 가능, 신청 직전에
대시보드 재확인 필요)

### 1.1 Free Plan 핵심 한도

| 항목 | Free 한도 | busy-day 1 도시·1년 환산 |
|---|---|---|
| Postgres DB 용량 | **500 MB** | songs 365행 + plays 수만 행 → 수십 MB. 여유 |
| 월간 활성 사용자(MAU, Auth) | **50,000** | 매장 BGM 용도면 충분 |
| Storage 용량 | **1 GB** | mp3 5MB × 365 = **1.78 GB** → **1년 못 채움. 6개월쯤 초과** |
| Storage 월 송신(egress) | **5 GB / 월** | 동시 청취 매우 적으면 OK, 공개 배포는 빠르게 초과 |
| Edge Functions 호출 | **500K / 월** | 일 1만 회까지 안전 |
| DB egress | **5 GB / 월** | 메타 응답만이면 충분 |
| 프로젝트 비활성화 | **7일 무접속 시 일시정지** | 매일 cron 이 돌면 발생 X |
| 동시 Free 프로젝트 수 | 보통 **2개** | 현재 INACTIVE 2개 보유, 활성 1개 |

### 1.2 무료로 갈 수 있는 최대 기간 (도시 1개·서울 단일 기준)

병목은 **DB 용량이 아니라 Storage 1 GB**.
- mp3(영구) 5MB/일 + score.jpg 0.6MB/일 + ir/musicxml/midi ≈ 0.1MB/일 → **약 5.7MB/일**
- 1024MB / 5.7MB ≈ **약 180일 (≈ 6개월)** → 그 이후 **유료(Pro)** 또는 외부 스토리지 분리 필요
- mp3 비트레이트를 V5(~130k) 로 낮추면 ~3.5MB/일 → **약 290일 (≈ 9.5개월)**

**Egress(송신)** 가 실질 병목이 될 가능성이 더 큼:
- mp3 1곡 5MB · 사용자 100명·하루 1회 청취 = **15 GB/월** → 하루 100청취만 돼도 **첫 달부터 5 GB 초과**
- 즉 **베타로 친구 10명에게만 공유** 단계까지가 무료, 공개 배포 즉시 유료 영역.

### 1.3 유료 전환이 발생하는 트리거

다음 중 **하나라도 닿으면 그 달부터 비용 발생**:

1. Storage 누적 용량 **1 GB 초과** (대략 운영 6개월차)
2. Storage egress 월 **5 GB 초과** (공개 트래픽 시작 첫 달)
3. DB 용량 **500 MB 초과** (waveform.json·plays 폭증 시 1~2년차)
4. MAU **50,000 초과** (대중적 인기를 얻은 시점)
5. Auth add-on (소셜 로그인 무제한 등) 활성화 시
6. Edge Functions 호출 **500K/월 초과**

### 1.4 Pro Plan 전환 시 비용 구조

- **고정 $25 / 월** (조직 단위, 프로젝트 수 무관)
- 포함: DB 8 GB, Storage 100 GB, Egress 250 GB/월, MAU 100K
- 초과분: Storage $0.021/GB·월, Egress $0.09/GB, DB $0.125/GB·월 정도
- 즉 **Pro 진입 후 대부분의 트래픽은 정액 안에서 흡수**, 진짜 변동비는 egress 가
  250 GB/월 넘어갈 때부터

### 1.5 권장 운영 전략 (비용 최소화)

a. **MVP/베타(0~6개월)**: Free 그대로 사용. 도시 1개, 사용자 < 50명
b. **Storage 분리 시점(6개월~)**: mp3·jpg 같은 큰 정적 자산만 **Cloudflare R2**(egress 무료)로
   이전, Supabase 는 DB + 메타만. 이 구성이면 Free 를 1~2년까지 연장 가능
c. **공개 배포 시점**: Supabase Pro($25) + R2(스토리지·egress 거의 무료) 조합이
   가장 가성비
d. **수면 모드**: 단일 도시 운영 중에도 cron 이 매일 한 번 호출되어
   "7일 비활성 자동 정지" 는 발생 X — 그래도 백업용 cron 별도 권장

### 1.6 우리 환경에서의 즉시 결정사항
- 활성 Free 프로젝트가 이미 1개(`workout_schedule`) 있음 → busy-day 는 두 번째 활성
  슬롯에 들어감(통상 Free 2개 가능)
- 또는 INACTIVE 2개 중 하나(`workout` / `roi-assessment`) 를 해제하고 신규 생성
- 권장: **`busy-day` 라는 이름으로 신규 Free 프로젝트 생성** (기존과 스키마 분리)

---

## 2. KMA 날씨 API → 작곡 파이프라인

기상청(KMA) 단기예보/실황 API 를 일 단위로 호출해 그날의 IR 과 자산을 만든다.

### 2.1 호출하는 KMA 엔드포인트

| 용도 | 엔드포인트 | 호출 주기 |
|---|---|---|
| 초단기실황 | `/VilageFcstInfoService_2.0/getUltraSrtNcst` | (옵션) 실시간 위젯용 |
| 단기예보(3일) | `/VilageFcstInfoService_2.0/getVilageFcst` | **매일 03:00 1회 (메인)** |
| 중기육상예보 | `/MidFcstInfoService/getMidLandFcst` | (옵션) 월간 합본용 |

KMA 좌표계는 LCC(격자) — 도시별로 `(nx, ny)` 룩업 테이블을 미리 둠
(서울 = 60, 127). 인증키는 환경변수 `KMA_SERVICE_KEY`.

### 2.2 단일 곡 생성 시퀀스 (배치, 매일 03:00)

```
[ 0 ] cron: city ∈ active_cities 마다 enqueue
        │
        ▼
[ 1 ] fetch_kma(nx, ny, base_date=today, base_time=0200)
        │  → JSON: TMP, REH, PCP, WSD, SKY, PTY ... 시간별 24개
        ▼
[ 2 ] aggregate_daily(rows)
        │  → temp_c=mean, temp_range=max-min, humidity=mean,
        │     precip_mm=sum, wind_mps=mean, cloud_pct=mean(SKY),
        │     precip_type=mode(PTY)
        ▼
[ 3 ] extract_features(weather)
        │  → warmth, brightness, wetness, calmness ∈ [0,1]
        ▼
[ 4 ] make_seed(date, city_id, generator_ver)
        │  → deterministic int64
        ▼
[ 5 ] mapping.pick_mode/pick_bpm/pick_meter/pick_palette
        │  → key='D', mode='dorian', bpm=72, palette={L1,L2,L3,L4}
        ▼
[ 6 ] compose.harmony  (Markov on mode chord pool)
[ 7 ] compose.melody   (motif + variation, chord-tone biased)
[ 8 ] compose.bass     (root-pedal + 5th passing)
[ 9 ] compose.texture  (rain/room layer rules)
        │
        ▼
[10 ] arrangement.compose(form=[INTRO,A,B,A',OUTRO])
        │  → IR (in-memory)
        ▼
[11 ] humanize(IR, rng)
        │
        ▼
[12 ] quality_check(IR)  ── fail ──► seed 재생성, [5]로 (max 5회)
        │ pass
        ▼
[13 ] render:
        ├─ to_midi(IR)        → audio.mid
        ├─ to_musicxml(IR)    → score.musicxml
        ├─ verovio → svg → png → jpg → score.jpg
        └─ fluidsynth + pedalboard → wav → ffmpeg → audio.mp3
        │
        ▼
[14 ] upload to Supabase Storage:
        songs/{city}/{YYYY}/{MM}/{date}/{ir.json,musicxml,jpg,mp3,wav,mid,meta.json}
        │
        ▼
[15 ] insert into public.songs (paths jsonb, weather jsonb, features jsonb, ...)
```

### 2.3 실패/재시도

- KMA API 5xx → 지수 백오프 4회 → 그래도 실패 시 **전일 날씨 + noise** 로 폴백
  플래그 `weather.fallback=true` 기록
- 렌더 실패 → IR 만 저장하고 audio 는 null. 다음 cron 에서 재시도
- 품질검사 5회 연속 실패 → 시드를 `+ generator_ver hash` 로 흔들고 재시도

### 2.4 사용자 청취 시 흐름 (실시간)

```
브라우저 달력 진입
  → GET /api/calendar?city=seoul&month=2026-05    (Supabase REST/Postgrest)
  → 한 달치 메타 + score-thumb 받음
  → 셀 클릭
      → GET signed URL { musicxml, mp3, ir.json }   (Supabase Storage)
      → OSMD 가 musicxml 렌더 (악보 표시)
      → Tone.js 가 IR 또는 mp3 재생
  → JPG / MP3 다운로드 버튼 = 같은 signed URL 직링크
```

여기서는 KMA 호출도, AI 호출도 없음 — **순수 정적 자산 서빙**.

---

## 3. AI 가 호출되는 지점 / 호출되지 않는 지점

핵심 입장: **곡 생성 자체는 AI 가 아닌 규칙(rule) + 의사난수(seeded RNG)**.
이유 — 재현성("같은 날 같은 도시 = 같은 곡"), 검증성, 비용 0, 라이선스 깨끗.

### 3.1 AI 호출 없음 (기본 파이프라인)

위 §2.2 의 **[1]–[14] 전 구간에 LLM/생성형 모델 호출 없음**.
- 모드 선택: 결정 트리 (lookup table)
- 화성 진행: 마르코프 체인 (사전 정의 가중치 행렬)
- 멜로디: 모티브 변주 알고리즘 (역행/축소/이조)
- 렌더: FluidSynth + 정적 이펙트 체인

→ 곡 1개 생성 비용 = CPU 수 초 + 스토리지 약간. **API 호출비 0원**.

### 3.2 선택적 AI 사용 지점 (옵션, 토글 가능)

다음은 **옵션 기능**으로만 두고, 기본은 OFF. 켜면 비용·라이선스 검토 필요.

| 위치 | 무엇을 | 모델 후보 | 켜야 하는 이유 |
|---|---|---|---|
| (a) 곡 제목/설명문 생성 | 그날의 날씨와 코드 진행을 받아 한 줄 시(詩) 생성 | Claude Haiku 4.5 | 매일 다른 카피, 무드 강화 |
| (b) 멜로디 후보 리랭킹 | 룰로 N=8 후보 생성 → 모델이 "Muji스러움" 점수 매김 | Claude (텍스트로 음표 시퀀스 평가) | 품질 회귀 테스트 보강 |
| (c) 화성 변형 가지치기 | 마르코프 후보들 중 자연스러운 것 픽 | 가벼운 분류기(자체 학습) | 룰 한계 보완 |
| (d) 사용자 피드백 학습 | 좋아요 데이터로 모드/템포 가중치 재학습 | 자체(scikit-learn 수준) | v1.1+ 개인화 |
| (e) 음성 안내(설명) | "오늘은 흐린 D Dorian, 비가 가끔" | TTS(별도) | 접근성 |

권장 순서: **(a) → (e) → (b)**. (b) 부터는 "재현성" 약속이 흔들리므로
generator_ver 를 별도로 기록.

### 3.3 비용 모델 비교

| 구성 | 곡당 비용 | 일/도시 | 1년/100도시 |
|---|---|---|---|
| 규칙 only (기본) | $0 | $0 | $0 + 인프라 |
| (a) 제목 생성 ON (Haiku 4.5, ~300토큰) | ≈ $0.0005 | $0.05 | ~$18 |
| (b) 리랭킹 ON (Sonnet 4.6, ~3K 토큰) | ≈ $0.012 | $1.2 | ~$430 |

→ 텍스트 메타데이터에만 AI 를 쓰면 거의 무시 가능, 음악 본체에 AI 를 쓰면 1년에
수백 달러 단위로 빠르게 증가.

### 3.4 결정

**v1.0 까지: AI 호출 0개로 운영.**
**v1.1: (a) 곡 제목/설명문에만 Claude Haiku 4.5 사용.**
**v1.2 이후: (b)/(d) 는 사용자 피드백이 수백 건 쌓인 뒤 검토.**

---

## 4. 작곡 코어 — 페이즈 진행 상황

### Phase 1 (완료) — 룰 기반 결정적 작곡 → MIDI

```
python -m compose generate --date 2026-05-06 --city seoul \
    --preset seoul-mild-clear --out ./out
```

산출: `out/ir.json` + `out/audio.mid`. 의존성: `mido`만.

구성:
- `compose/seed.py` — sha256 기반 결정적 시드
- `compose/features.py` — 날씨 → {warmth, brightness, wetness, calmness}
- `compose/mapping.py` — features → 모드/조성/장르/BPM/박자/모티브
- `compose/scales.py` — 모드 인터벌, degree → MIDI 변환
- `compose/harmony.py` — 모드별 마르코프 화성 진행
- `compose/melody.py` — 모티브 변주 8종 (역행/축소/확대/이조/장식/생략/에코/원형)
- `compose/arrange.py` — 5섹션 형식(INTRO/A/B/A'/OUTRO), 길이 ~62초 자동 산정
- `compose/render.py` — IR → 표준 MIDI (3트랙: melody/harmony/bass, GM 음색)
- `compose/data/motifs.json` — 사람이 그린 시드 모티브 8개
- `compose/__main__.py` — CLI

검증: 7일치 생성 결과 모두 모드/조성/장르/BPM/박자/모티브/시그니처 유니크,
~60초 길이 안정.

### Phase 2 — 브라우저 재생 + 악보 (완료)

작곡 본체에 **자연 종결** 추가: 마지막 마디는 강제 토닉 + 한 마디 분량
잔향(ring-out) — 끊어지지 않고 자연스럽게 사라진다.

같은 spec(키/모드/장르/BPM/박자/모티브)으로 **short(~60s)** 와
**long(~130s)** 두 IR을 동시 생성. long은 short의 자연스러운 확장 (다른
곡이 아님).

```
python -m compose generate --date 2026-05-06 --city seoul \
    --preset seoul-mild-clear --out out/test
# -> out/test/{ir_short.json, ir_long.json,
#              audio_short.mid, audio_long.mid, score.svg}
```

오디오 렌더는 **서버 측이 아닌 브라우저**:
- `js/player.js`가 [@tonejs/midi](https://tonejs.github.io/) 로 MIDI 파싱
- Tone.js Sampler + Salamander 그랜드 피아노 (CDN, ~6MB 1회 캐시)
- 멜로디는 피아노, 화성은 부드러운 AM 패드 + 리버브
- 결과: 서버 렌더 0초, mp3 파일 0개, 사용자 다운로드는 MIDI/SVG 직접

악보는 `compose/score.py`가 IR → ABC → verovio → SVG.
브라우저는 fetch 후 inline 삽입(확대 자유, 인쇄 가능).

### Phase 3 — KMA 실연동 + Supabase 업로드 (완료)

`compose/kma.py`:
- 단기예보 `getVilageFcst` 호출, 페이지네이션 처리
- KMA 강수 표기("강수없음", "1mm 미만", "30.0~50.0mm" 등) 모두 흡수
- 결과를 일 단위 평균/합계로 집계 → temp_c/temp_range/humidity/precip_mm/wind_mps/cloud_pct/precip_type

`compose/upload.py`:
- service-role key 로 Storage PUT + REST upsert
- 절대 브라우저에 노출되지 않음 (cron 환경변수에만 있음)

`compose/daily.py` end-to-end:
1. cities 행에서 `kma_nx, kma_ny` 조회
2. 최근 30일 songs 행에서 signature/motif/genre 회수 → 회피 리스트 구성
3. 시그니처 충돌 시 최대 3회 재시도
4. weekly_theme upsert (FK 충족용) → 곡 생성 → 자산 5종 업로드 → songs upsert

```
SUPABASE_URL=… SUPABASE_SERVICE_ROLE_KEY=… KMA_SERVICE_KEY=… \
  python -m compose daily --date today --city seoul
```

### Phase 4 — GitHub Actions cron (완료)

`.github/workflows/daily-compose.yml`:
- `cron: "0 21 * * *"` (UTC) = **매일 06:00 KST** (다음 날 아침)
- `workflow_dispatch` 로 수동 실행도 동일 동작
- 의존성 = `mido + verovio + requests` (사운드폰트 다운로드 0)

#### 필수 GitHub Secrets

리포 Settings → Secrets and variables → Actions → New secret:

| 이름 | 값 | 출처 |
|---|---|---|
| `SUPABASE_URL` | `https://diqxldieduslrpkjrguc.supabase.co` | 이 문서 |
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJ…` (긴 JWT) | Supabase Dashboard → Project Settings → API → service_role secret |
| `KMA_SERVICE_KEY` | `xxxxxxxx==` | data.go.kr → 마이페이지 → 단기예보 조회 서비스 일반 인증키(Encoded) |

세 개를 등록한 뒤 Actions 탭 → daily compose → Run workflow 로 즉시 호출 가능.
그 이후로는 매일 06:00 KST 자동 실행.

### Phase A — 음악 품질 ↑ (완료)

**모티브 풀 8 → 30** (`compose/data/motifs.json`):
- 따뜻/밝은 5: orange_glow, dust_in_sunbeam, kettle_chime, balcony_breeze, pottery_wheel
- 차분/조용 5: inkbrush, snow_settling, glass_rim, fog_lift, polished_stone
- 비/촉촉 4: drizzle, rain_window, undercurrent, misty_garden
- 회상/단조성향 4: old_letter, fading_print, quiet_room, long_corridor
- 활기/유희 4: tea_bowl, origami_fold, lattice_climb, courtyard_chime

**휴머나이즈** (`compose/humanize.py`):
- `apply_velocity_curve` — 섹션 단위로 산형(arch) 벨로시티: 시작은 부드럽게,
  중반에 자연스러운 피크, 끝으로 갈수록 옅게. 기본 56 ± 38 + 작은 jitter.
- `apply_outro_decay` — OUTRO 구간 전반에 걸쳐 강제 데크레센도 (×1.0 → ×0.45)
- `apply_micro_timing` — 음 시작 시점 ±0.018박 jitter (사람 손맛)
- `pedal_segments` — 피아노 계열 장르(ambient/neo_classical/folk/lo_fi)에서
  마디 단위 댐퍼 페달, 같은 코드 연속이면 페달도 이어감

**서스테인 페달** (`compose/render.py`):
- MIDI CC64 메시지로 melody/harmony 채널에 ON/OFF 기록
- 베이스는 페달 없음(저음역 머디함 방지)

**장르별 악기 분화** (`js/player.js` + Tone.js):
| 장르 | 멜로디 | 화성 | 베이스 |
|---|---|---|---|
| ambient | 피아노 (release 3.0s) | AM 패드 + 리버브 | 피아노 LH |
| neo_classical | 피아노 (release 2.6s) | 스트링 패드 | 피아노 LH |
| folk | 피아노 (release 1.6s) | AM 패드 (드라이) | 피아노 LH |
| lo_fi | 피아노 (release 2.4s) + lowpass 2.4kHz | AM 패드 | 피아노 LH |
| jazz_ballad | FM Rhodes | FM Rhodes 패드 | upright bass(FM) |
| bossa_nova | PluckSynth 나일론 | PluckSynth 컴핑 | upright bass(FM) |

검증: 14일 시뮬레이션에서 모두 시그니처 유니크, 신규 모티브 8종 출현, 6장르 모두 사용.

### 공휴일/특별한 날 메모 (한 달 운영 후 작업)

크리스마스, 어린이날, 설날 같은 날에는 별도 감정 코드를 주입:
- 따뜻한 날(크리스마스): 따뜻 +0.3, 단조성향 -0.2, 종소리 텍스처
- 어린이날: 밝음 +0.4, 장조 강제, 더 활기찬 BPM
- 추석/설날: 페달 강화, 더 긴 잔향, 명상적 모드

`compose/holidays.py` 로 (date_iso, country) → 보너스 features delta 매핑.
v1.1 에서 추가 — 1년 운영 데이터 + 한 사이클 분량 들어본 다음 어울리는
처리 결정.

### Phase B — 다중 변주 + 의견 트리거 (완료)

하루에 여러 곡, 사용자가 무드를 지정. 모두 결정적·룰 기반(LLM 0).

**스키마**
- `songs`: `variant_id text not null default 'auto'` + `intent_id text` 추가
- unique 제약 변경: `(city_id, date, generator_ver, variant_id)`
- 기존 cron 곡은 `variant_id='auto'` 유지 — **절대 덮어쓰지 않음**
- Storage 경로: `{city}/{Y}/{M}/{date}/{variant_id}/...`

**Intent 6종** (`compose/intent.py`)
| id | 한국어 | 핵심 효과 |
|---|---|---|
| calm | 차분하게 | calmness +0.30, ambient 선호, BPM 58–72 |
| warm | 따뜻하게 | warmth +0.30, calmness +0.10 |
| wistful | 쓸쓸하게 | brightness -0.30, dorian 강제, bossa/folk 회피 |
| lively | 활기차게 | brightness +0.30, calmness -0.30, bossa 선호 |
| after_rain | 비 온 뒤처럼 | wetness +0.30, brightness -0.10 |
| sleep | 잠들기 전 | calmness +0.40, ambient 선호, BPM 58–68 |

intent → feature delta + (mode_bias / preferred_genre / avoid_genres /
bpm_clamp). 사용자 트리거는 `seed_salt` 도 같이 적용해서 같은 날짜에서도
mode/key/motif 다른 draw 보장.

**파이프라인** (`compose/pipeline.py`, `daily.py`)
- `generate_pair(..., intent=, seed_salt=)` 추가
- `daily.py --variant <id> --intent <preset>` 추가
- 사용자 변주 ID: `user-HHMM-<intent>` (예: `user-1430-calm`)

**GitHub Actions** (`.github/workflows/daily-compose.yml`)
- inputs: `date / city / variant / intent`
- cron 은 모두 기본값 → variant=auto, intent=""

**Edge Function** `/trigger` (`supabase/functions/trigger`)
- POST `{ date, city, intent_id }` → workflow_dispatch 호출
- 응답 `{ variant_id, intent_id, eta_sec }`
- `GITHUB_PAT` 환경변수만 필요

**웹 UI**
- 캘린더 하단 **"+ 오늘 곡 더 만들기"** 버튼
- 6개 intent 카드 모달 → 클릭 시 `/trigger` POST → 6초 간격 polling →
  새 row 발견 시 디테일 모달로 전환
- 디테일 헤더에 **변주 칩**: `[오늘] [차분] [따뜻]…` — 클릭 시 즉시 스왑
- 캘린더 셀 우하단에 변주 개수 배지(`+2`)
- 다운로드 파일명에 `{date}_{tempC-sky}_{genre}_{kind}.{ext}` 자동 적용

**필요한 사용자 액션 (1회)**
1. GitHub Fine-grained PAT 생성 (Actions: Read and write)
2. Supabase Dashboard → Project Settings → Edge Functions →
   Secret 추가: `GITHUB_PAT = github_pat_xxx`

---

## 5. 정적 페이지(`index.html`) 배포 — GitHub Pages

빌드 단계 없는 순수 정적 파일이라 main 브랜치 root 를 GH Pages 소스로 지정하면
바로 동작합니다.

### 5.1 배포 절차

1. 리포지토리 Settings → Pages
2. Source: `Deploy from a branch`
3. Branch: `main` / folder `/ (root)`
4. Save → 1~2분 후 `https://<owner>.github.io/busy-day/` 로 접속

> 필요시 `CNAME` 파일을 root 에 추가하면 커스텀 도메인 사용 가능.

### 5.2 비밀번호 설정 (단일 사용자 게이트)

`js/config.js` 의 `PASSWORD_HASH` 에 sha-256 hex 다이제스트를 넣습니다.
빈 문자열로 두면 게이트 없이 누구나 접속 가능.

로컬에서 해시 만드는 법:
```bash
echo -n "내가-원하는-비밀번호" | shasum -a 256 | cut -d' ' -f1
```

생성된 64자리 hex 를 `PASSWORD_HASH` 값으로 붙여넣고 커밋. 이 해시가
공개되더라도 비밀번호가 길면(>= 12자, 무작위) 역산 비용이 큼.

### 5.3 파일 구조

```
busy-day/
├── index.html           — 게이트 + 달력 + 디테일 모달 셸
├── styles.css           — 무지미 스타일 1장
└── js/
    ├── config.js        — Supabase URL/key, PASSWORD_HASH
    ├── auth.js          — sha-256 게이트
    ├── api.js           — Supabase 클라이언트 + 월간 곡 조회
    ├── calendar.js      — 6주 그리드 렌더
    ├── player.js        — 디테일 모달 (악보·오디오·다운로드)
    └── main.js          — 부트
```

모든 의존성은 ESM CDN(`esm.sh`) 으로 동적 로드 — 노드/번들러 없음.

### 5.4 동작 흐름

```
페이지 로드
  → auth.bindGate() 가 sessionStorage 확인
  → 통과 시 main.boot() 호출
  → CalendarView.render() : 현재 월의 songs 행 fetch
  → 각 셀: 곡 있으면 .has-song + 장르 라벨, 클릭 시 DetailPanel.open()
  → 모달:
      - score.jpg public URL 표시
      - 1분/2분+ 토글로 mp3_short/mp3_long URL 스왑
      - 다운로드 리스트 (mp3/wav/jpg/musicxml/midi 중 존재하는 것)
      - 재생 시작 시 plays 테이블에 비동기 insert
```

곡 데이터가 아직 없으면 모든 셀이 빈 칸 — DB·작곡 파이프라인 연결 후 자동
표출.

---

## 6. Phase C-1 — 환경음 레이어 + 습도→리버브 (완료)

### 6.1 공개 매핑 (4가지 핵심 규칙)

채널 About / 사이트 카피에 그대로 옮길 수 있는 문장:

> **기온은 키를, 습도는 리버브의 깊이를, 풍속은 바람 소리를,
> 강수량은 빗소리의 무게를 결정합니다.**

내부에는 더 많은 미세 매핑(모드/장르/모티브/페달/컴핑/퍼커션 등)이
돌아가지만, 청취자에게는 위 네 줄로만 약속한다. 룰의 명료성이 시스템
작품의 매력이라는 원칙(로드맵 §시스템 확장의 함정).

### 6.2 환경음 5종 (`js/player.js: decideAmbience`)

순수 함수 — 같은 weather/features 입력 = 같은 레이어 출력.
실음원 X. 모두 Tone.js 합성. 라이선스·외부 의존성 0.

| 조건 | 레이어 | 합성 레시피 | 볼륨 |
|---|---|---|---|
| 강수 > 0.1mm | rain | PinkNoise + lowpass(1.2–3.4kHz) | -34 → -14 dB (강수 비례) |
| 풍속 > 4 m/s | wind | BrownNoise + bandpass + slow LFO | -36 → -16 dB |
| 맑음+따뜻+무비 | birds | FM chirp 8th-노트 시퀀스 | -28 dB, 밀도=brightness |
| 기온 < 3°C | indoor | 저주파 sine + 종이 텍스처 노이즈 | -30 dB |
| 습도 > 80% + 풍속 < 3 | hum | E1 + C2 sine 더블 | -34 dB |

라이프사이클: ▶ 누를 때 시작(브라우저 제스처 요구), ■/Esc/모달 닫기 시 정지.
정지 시 0.6–1.1초 페이드아웃 후 dispose.

### 6.3 리버브 wet ← 습도 (`reverbWetFromHumidity`)

```
wet = 0.20 + clip((humidity - 30) / 60, 0, 1) × 0.40
```

- 습도 30% 이하: 0.20 (드라이 거실)
- 습도 90% 이상: 0.60 (성당)
- 곡 변주 스왑 시 0.5초 ramp 으로 부드럽게 변경

### 6.4 로드맵 진행 상황

| 항목 | 상태 |
|---|---|
| 1순위 환경음 | ✅ 완료 (Phase C-1) |
| 2순위 리버브 wet → 습도 | ✅ 완료 |
| 2순위 노트 밀도 → 풍속 | 미착수 |
| 2순위 보이싱 spread → 기온 | 미착수 |
| 2순위 드론 → 흐림 | 미착수 |
| 2순위 휴머나이즈 → 기압 | 미착수 |
| 3순위 무드별 화성 풀 | 미착수 |
| 4순위 시간/상황 무드 (작업/낮잠/산책) | 미착수 |
| 5순위 마림바·하프·클라리넷 | 미착수 |

다음 사이클: **Phase C-2** = 노트 밀도(풍속) + 보이싱 spread(기온) + 드론(흐림). 한 묶음.
