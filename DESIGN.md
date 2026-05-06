# busy-day — 날씨 기반 생성 음악 시스템 설계도

매일의 날씨 변수를 받아 음계를 생성하고, 어울리는 화음으로 작곡하여
무인양품(MUJI BGM 시리즈) / "Various Artists - Busy Day" 류의 잔잔한 앰비언트
감성으로 출력하는 시스템.

---

## 0. 디자인 철학 (감성 기준선)

레퍼런스의 공통점을 음악적 파라미터로 환산:

| 감성 키워드 | 음악적 변환 |
|---|---|
| 정적 / 여백 | 느린 템포(60–90 BPM), 긴 노트 지속, 적은 보이싱(2–4 voice) |
| 따뜻함 | 메이저 7th / sus2 / add9 화음, 도미넌트 7 회피 |
| 일상감 | 4/4, 8/8 단순 박자, 페달톤 / 오스티나토 |
| 비완결성 | 주로 모달(Lydian, Dorian, Mixolydian), 종지(cadence) 약화 |
| 자연 음색 | 어쿠스틱 피아노, 로즈, 비브라폰, 글로켄슈필, 클라리넷, 어쿠스틱 기타 |
| 공간감 | 긴 리버브(2–4s), 약한 LPF, 테이프 새튜레이션, 가벼운 빗소리/필드 레코딩 |

**금지 규칙**: 강한 어택 드럼, 7#9 같은 텐션, 빠른 16분 멜리스마, 강한 컴프레션,
EDM 사이드체인, 드라이한 톤.

---

## 1. 시스템 아키텍처

```
┌────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌────────┐
│ Weather    │ → │ Feature      │ → │ Music Mapper │ → │ Composition  │ → │ Render │
│ Source     │   │ Extractor    │   │ (rule + RNG) │   │ Engine       │   │ Engine │
└────────────┘   └──────────────┘   └──────────────┘   └──────────────┘   └────────┘
       │                │                  │                  │                │
       ▼                ▼                  ▼                  ▼                ▼
   OpenWeather    정규화/특징량     키/스케일/템포/        멜로디·화성·       MIDI →
   /기상청 API    (z-score, bin)   레지스터/음색 결정     리듬·아르페지오    오디오(WAV)
                                   (시드 = 날짜+위치)     생성
```

각 단계는 순수 함수에 가깝게 분리해서 동일 입력 → 동일 출력(재현 가능)이 되도록.

---

## 2. 입력 변수 (Weather Features)

### 2.1 원천 데이터
- 기온 `temp_c` (°C)
- 일교차 `temp_range` (max - min)
- 습도 `humidity` (%)
- 강수량 `precip_mm`
- 강수 형태 `precip_type` ∈ {none, rain, snow, sleet}
- 풍속 `wind_mps` (m/s)
- 운량 `cloud_pct` (%)
- 기압 `pressure_hpa`
- 일출/일몰 → `daylight_ratio` (0–1)
- 시각 `local_hour` (0–23)
- 계절 `season` ∈ {spring, summer, autumn, winter}
- 위도 `lat` (감성 보조)

### 2.2 파생 특징량
- `warmth` = norm(temp_c, -10..30) → 0..1
- `brightness` = 1 - cloud_pct/100
- `wetness` = clamp(precip_mm / 10, 0, 1)
- `calmness` = 1 - norm(wind_mps, 0..15)
- `mood_axis_x` = warmth - wetness  (밝음 ↔ 차분/우울)
- `mood_axis_y` = calmness * brightness  (선명함 ↔ 흐림)

### 2.3 시드(Seed)
```
seed = hash(YYYY-MM-DD || location_id || version)
```
같은 날·같은 도시는 동일 곡, 버전 올리면 새 곡.

---

## 3. 매핑 규칙 (Weather → Music Parameters)

### 3.1 키 / 모드(Mode)
운량 + 강수로 모드 선택. 메이저/마이너 직접 매핑 대신 **모드(mode)** 사용 — Muji
감성에 핵심.

| 조건 | 모드 | 비고 |
|---|---|---|
| 맑음 + 따뜻 | Lydian | 떠 있는, 동화적 |
| 맑음 + 서늘 | Ionian (Major) | 청량 |
| 흐림 + 따뜻 | Mixolydian | 빈티지, 따뜻한 흐림 |
| 흐림 + 서늘 | Dorian | 우수, 약간의 그늘 |
| 비/눈 | Aeolian | 차분한 단조 느낌, 단 i–IV 진행으로 어둡지 않게 |
| 안개 / 고습 | Phrygian (드물게) | 신비, 이국적 |

루트(tonic)는 `(seed % 12)`로 12개 음 중 하나, 단 어쿠스틱 악기 음역 고려해
`C, D, E♭, E, F, G, A♭, A, B♭` 중에서만 뽑도록 가중치(피아노 친화).

### 3.2 템포(BPM)
```
bpm = 60 + calmness * 30 + (1 - wetness) * 10
       (보정: hour ∈ [22..5] 이면 -8)
       범위 캡: 56..96
```

### 3.3 박자 / 그루브
- 기본 4/4
- `wind_mps > 8` → 6/8 (흔들림)
- `local_hour ∈ [5..8]` → 잔잔한 8분 아르페지오
- `local_hour ∈ [21..2]` → 자유 루바토(quantize off, swing 55)

### 3.4 음색(Instrument Layer)
레이어 4개를 항상 유지(없으면 무음 처리):

| 레이어 | 역할 | 후보 |
|---|---|---|
| L1 PAD | 화성 베드 | 펠트 피아노, 와인드패드, 보우드 비브 |
| L2 LEAD | 멜로디 | 글로켄슈필, 셀레스타, 클라리넷, 뮤트 트럼펫 |
| L3 BASS | 베이스 | 업라이트 베이스(느슨), 신스 서브(아주 작게) |
| L4 TEX | 텍스처 | 타닥거리는 비, 새소리, 카세트 노이즈, 룸톤 |

선택 규칙:
- `warmth > 0.6` → L1=Felt Piano, L2=Vibraphone
- `wetness > 0.4` → L4=Rain field recording (−24 dB)
- `brightness > 0.7` → L2=Glockenspiel
- `calmness < 0.3` → L1을 Bowed Pad로 대체(바람 묘사)

### 3.5 다이내믹 / 공간
- Reverb decay = 1.5 + wetness * 2.5 초
- LPF cutoff = 4000 + brightness * 8000 Hz
- 전체 음량 = -18 LUFS 목표 (Muji 매장 BGM 라우드니스)

---

## 4. 작곡 엔진 (Composition Engine)

### 4.1 구조 (Form)
한 곡 = 약 2분 30초 ~ 4분, 다음 섹션:

```
INTRO (8 bars)  →  A (16 bars)  →  B (16 bars)  →  A' (16 bars)  →  OUTRO (8 bars)
   pad+tex         pad+bass+lead    +counter melody    sparse        pad fade
```

### 4.2 화성 진행 (Harmony)
모드별 코드 풀 정의 후 마르코프 체인으로 다음 코드 선택. 모든 코드는 7th/9th로
보이싱.

예) Ionian (C major) — Muji 풍 진행 풀:
```
I_maj7  IV_maj7  vi_7  iii_7  ii_9  V_sus  IVadd9  I/3
```
전이 행렬은 V→I 같은 강한 종지를 0.1로 낮추고, IV→I, vi→IV 같은 plagal/모달
이동을 0.3 이상으로 가중.

코드 길이는 2 bars 또는 4 bars (느린 호흡).

### 4.3 멜로디 생성
1. 현재 코드의 **chord tone + 9th/13th**을 안전 풀로
2. 비-코드톤은 항상 **passing / neighbor**로만 사용
3. 윤곽: 1~2 bar 모티브를 만들고 변주(역행 / 음역 이동 / 리듬 축소)
4. 음역: 전체 G3..C6, 한 곡 안에서는 1.5 옥타브 이내
5. 노트 길이: 전음표·2분음표 위주, 가끔 4분 / 점8분
6. 음표 밀도: `0.3 + brightness * 0.4` notes/beat

### 4.4 베이스
- 코드 루트 위주, 코드 변화 사이에 5도 또는 3도 패싱
- 페달톤 모드(`wetness > 0.5`)에서는 8 bars 고정 루트 유지

### 4.5 리듬 / 아르페지오
- 16분이 아닌 **8분 분산화음**, 각 노트 길이는 점4분(서스테인이 겹치며 화음감 형성)
- 셀레스타/글로켄슈필은 비주기적(예: Euclidean(5, 8))으로 한 두 음만 점묘처럼

### 4.6 휴머나이즈
- 타이밍 ±15ms 가우시안
- 벨로시티 60–88 사이 1/f 노이즈
- 피아노는 페달 다운 비율 80%

---

## 5. 렌더링 파이프라인

```
Composition (내부 IR)
   │
   ├── to_midi()  ──►  .mid  (저장/공유용)
   │
   └── to_audio()
         │
         ├── 샘플러: pretty_midi + soundfont (FluidSynth)
         │     또는 Tone.js + 샘플 라이브러리(웹)
         ├── 이펙트 체인: EQ(저역 컷 80Hz) → Tape sat → Plate Reverb → LUFS norm
         └── 출력: .wav (48kHz/24bit) + .mp3(192k) + 파형 PNG
```

### 5.1 내부 IR (중간 표현)
```jsonc
{
  "meta": { "date": "2026-05-06", "city": "Seoul", "seed": 178234 },
  "weather": { "temp_c": 18, "cloud_pct": 70, "precip_mm": 1.2, ... },
  "music": {
    "key": "D",
    "mode": "dorian",
    "bpm": 72,
    "meter": "4/4",
    "form": ["INTRO","A","B","A'","OUTRO"],
    "tracks": [
      { "name": "L1_PAD",  "instrument": "felt_piano", "events": [...] },
      { "name": "L2_LEAD", "instrument": "vibraphone",  "events": [...] },
      { "name": "L3_BASS", "instrument": "upright_bass","events": [...] },
      { "name": "L4_TEX",  "instrument": "rain_field",  "events": [...] }
    ]
  }
}
```
이벤트는 `{ t_beat, dur_beat, pitch, vel, articulation }` 단위.

---

## 6. 코드 모듈 구성 (제안: Python + JS 듀얼)

### 6.1 백엔드 (작곡 엔진) — Python
```
busy_day/
  weather/
    fetch.py          # OpenWeather / KMA 어댑터
    features.py       # 정규화, 파생 변수
  mapping/
    rules.py          # 모드/템포/음색 결정
    seed.py
  compose/
    harmony.py        # 모드별 코드 풀 + 마르코프
    melody.py         # 모티브 생성·변주
    bass.py
    texture.py
    arrangement.py    # 폼/섹션 결합, humanize
    ir.py             # 중간 표현 dataclass
  render/
    midi_writer.py    # mido / pretty_midi
    audio_render.py   # FluidSynth + pedalboard 이펙트
  cli.py              # `busyday today --city Seoul`
  api.py              # FastAPI: GET /today.mp3
```

라이브러리: `music21`(이론 검증), `mido`/`pretty_midi`(MIDI),
`pyfluidsynth`(샘플러), `pedalboard`(이펙트), `pyloudnorm`(LUFS).

### 6.2 프론트(웹 플레이어) — Tone.js
- `Tone.Sampler` + 무료 SFZ/SF2 샘플(예: VSCO Community, Sonatina)
- 매일 0시에 백엔드가 IR(json)을 생성, 프론트는 실시간 재생
- 시각화: 파형 + 날씨 카드(아주 미니멀, sans-serif, 여백 多)

### 6.3 데이터 흐름 (배치 vs 실시간)
- **배치**: 매일 새벽 1시 cron → 도시별로 곡 사전 생성 → S3에 mp3·wav·json 업로드
- **실시간**: 사용자가 위치 허락 → 가까운 캐시 곡 우선, 없으면 즉석 생성

---

## 7. 의사코드 (핵심 루프)

```python
def compose_today(city: str, date: date) -> Composition:
    w = fetch_weather(city, date)
    f = extract_features(w)
    seed = make_seed(date, city)
    rng = Random(seed)

    key, mode = pick_mode(f, rng)
    bpm       = pick_bpm(f)
    meter     = pick_meter(f, rng)
    palette   = pick_instruments(f, rng)

    chords = generate_progression(mode, key, bars=64, rng=rng)   # 마르코프
    melody = generate_melody(chords, f, rng)
    bass   = generate_bass(chords, f, rng)
    tex    = generate_texture(f, rng)

    arr = arrange(form=["INTRO","A","B","A'","OUTRO"],
                  layers={"L1": chords, "L2": melody,
                          "L3": bass,   "L4": tex},
                  bpm=bpm, palette=palette)
    return humanize(arr, rng)
```

---

## 8. 품질 보증 (감성 회귀 테스트)

순수 함수 단위 테스트 외에, **감성 일탈 방지** 어설션:

- 동일 모드 안 반음(half-step)이 같은 보이스에 연속 등장 < 5%
- 한 곡 안 코드 변화 횟수 ∈ [16, 48]  (너무 빠르거나 느리면 fail)
- 멜로디 도약(>옥타브) ≤ 곡당 3회
- 평균 노트 밀도 ≤ 1.2 notes/beat
- 출력 LUFS ∈ [-20, -16]
- 스펙트럴 센트로이드 ≤ 3.5 kHz (날카로움 방지)

각 곡은 `quality_score` 계산해 임계 미만이면 다른 시드로 재생성(최대 5회).

---

## 9. 곡 길이 & 형식 권장값

레퍼런스 분석(Muji BGM 컴필 평균 ~3'10", Various Artists "Busy Day" 류 평균 ~2'40")과
배경음악 사용 상황(아침 루틴, 카페 1잔, 산책 1바퀴)을 함께 고려한 권장값:

| 사용 시나리오 | 길이 | 비고 |
|---|---|---|
| 데일리 단곡(기본) | **2:30 – 3:30** | 권장 기본 = **3:00**. 커피 한 잔 정도 |
| 짧은 프리뷰(달력 셀 호버) | 0:20 – 0:30 | A 섹션 첫 8마디 루프 |
| 위젯/알림 | 0:45 – 1:00 | INTRO + A 8마디 |
| 한 달 합본(monthly mix) | 30 – 45분 | 날짜순 크로스페이드 4초 |
| 한 해 합본(yearly tape) | 4 × 30분 (계절별 EP) | 365곡 전부가 아니라 큐레이션 |

길이 산정 공식 (BPM에 따른 자동 보정):
```
total_bars = round(target_seconds * bpm / 240)     # 4/4 기준
target_seconds = clamp(180 ± 30 * (1 - calmness), 150, 210)
```
즉 차분한 날일수록 3'30"에 가깝고, 활동적인 날(맑고 바람 약간)은 2'30"에 가깝게.

섹션 비율 (총 64마디 = 약 3분 @ 72bpm 기준):
```
INTRO  8 bars (12.5%)   여백, 텍스처만
A     16 bars (25%)     주제 제시
B     16 bars (25%)     변주 / 카운터멜로디
A'    16 bars (25%)     축약 회귀
OUTRO  8 bars (12.5%)   페이드, 여운
```

---

## 10. 달력 UI & 악보 뷰어

### 10.1 화면 구성

```
┌─────────────────────────────────────────────────────────┐
│  busy-day            Seoul ▾            2026 / 05       │
├─────────────────────────────────────────────────────────┤
│   M    T    W    T    F    S    S                       │
│   ─    ─    ─    1    2    3    4                       │
│   5    6●   7    8    9   10   11    ●= 오늘            │
│  12   13   14   15   16   17   18    ○= 듣기 완료       │
│  19   20   21   22   23   24   25    · = 미생성         │
│  26   27   28   29   30   31   ─                        │
│                                                         │
│  각 셀 호버 → 30초 프리뷰 자동 재생                      │
│  각 셀 클릭 → 우측에 악보 뷰어 + 플레이어 오픈           │
├─────────────────────────────────────────────────────────┤
│   [ 악보 뷰어 패널 — 5월 6일 (수) ]                     │
│   ♩ = 72   D dorian   3:04                              │
│   ┌───────────────────────────────────────┐             │
│   │ ♭♭ 4/4  ♩♩ ♩  ♩ ♩  ♩ ─                │             │
│   │ ──────●─●─●──●─●──────                │             │
│   └───────────────────────────────────────┘             │
│   [▶ 재생]  [⏸]  [━━━●─────] 0:42 / 3:04                │
│   [ JPG 다운로드 ]  [ MP3 다운로드 ]  [ MIDI ] [ XML ]   │
└─────────────────────────────────────────────────────────┘
```

### 10.2 클릭 → 악보 표시 흐름

```
calendar cell click
  → GET /api/songs/{date}/{city}
       returns { ir_json_url, musicxml_url, jpg_url, mp3_url, weather }
  → 프론트 OSMD(OpenSheetMusicDisplay)에 musicxml 로드 → SVG 렌더
  → 동시에 Tone.js Sampler 가 IR(json)을 큐잉
  → 사용자가 ▶ 누르면 OSMD 커서가 진행, Tone.js 가 같은 timeline 으로 재생
```

핵심: 악보의 시각 진행과 오디오는 같은 IR(중간 표현)에서 파생되므로 **동기화가
보장**됨. OSMD `cursor.next()` 가 매 비트마다 호출되어 현재 음표를 하이라이트.

### 10.3 시스템이 악보를 읽어 재생하는 방식

두 가지 경로 중 **MusicXML 경로**를 권장:

- **A. IR(JSON) 직접 재생** — 백엔드 IR을 Tone.js 가 그대로 읽음. 빠르고 정확.
- **B. MusicXML 재해석** — 악보(MusicXML)를 진짜로 "읽어서" 재생. 사용자가 악보를
  편집(미래 기능)했을 때 그 변경이 음에 반영됨.

기본은 A로 빠르게 재생하되, "악보 모드(편집)"에서는 B로 전환해 MusicXML →
파서(Verovio / `musicxml-parser`) → Tone Part 로 변환.

### 10.4 JPG 익스포트
```
MusicXML → Verovio (server-side, headless) → SVG
        → resvg / sharp 로 PNG 래스터화 (300dpi, A4)
        → libvips 로 JPG(quality 92) 변환 → S3 업로드
```
파일명: `{city}/{YYYY}/{MM}/{YYYY-MM-DD}.jpg` 약 400–800KB.

상단 헤더에 자동 삽입: 곡 제목(`busy-day · 2026.05.06 · Seoul`),
템포·조성, 그리고 그날의 날씨 아이콘(작게).

### 10.5 MP3 익스포트
- 매일 배치에서 wav(48k/24bit) 생성 → ffmpeg 으로 mp3 V2(VBR ~190kbps) 인코딩
- ID3 태그:
  - title  : `busy-day · 2026-05-06`
  - artist : `busy-day generator`
  - album  : `Seoul · 2026-05`
  - comment: `D dorian, 72bpm, cloudy 70%, 18°C`
  - artwork: 그날의 악보 JPG 썸네일(512px)
- "MP3 다운로드" 버튼은 사전 생성된 정적 URL 로 즉시 다운로드(신호 URL, 7일 유효)

### 10.6 악보 표기 규칙 (가독성 우선)
- 5선 1단(treble) 또는 그랜드 스태프(treble + bass) — 베이스 레이어가 있으면 grand
- 텍스처(L4 비/룸톤)는 악보에 표기 X — 좌측 하단에 텍스트로 "rain field, room tone"
- 패드(L1)는 코드 심볼만 표기(`Dm9  Gmaj7  ...`), 모든 보이스를 그리지 않음
- 멜로디(L2) 1성부 + 베이스(L3) 1성부 = 사람이 연주 가능한 형태로 단순화
- 다이내믹: `mp` 일관, 페달 표시(Ped. ────)

이 단순화 덕분에 악보는 "이 곡을 사람이 따라 칠 수 있는 lead sheet" 가 되고,
시스템 재생은 IR 기반의 풀 믹스라는 이중 구조.

---

## 11. 아카이빙 구조

### 11.1 스토리지 레이아웃 (객체 스토리지: S3 / R2)

```
busy-day-archive/
├── songs/
│   └── {city}/                          # ex) seoul, tokyo, busan
│       └── {YYYY}/
│           └── {MM}/
│               └── {YYYY-MM-DD}/
│                   ├── ir.json          # 중간 표현 (재현 가능 핵심)
│                   ├── score.musicxml   # 악보 원본
│                   ├── score.jpg        # 시트 이미지 (300dpi)
│                   ├── score-thumb.png  # 달력 썸네일 (256px)
│                   ├── audio.mp3        # 배포용 (~190kbps VBR)
│                   ├── audio.wav        # 마스터 (30일 후 만료)
│                   ├── midi.mid         # MIDI 원본
│                   ├── waveform.json    # 시각화용 PCM 다운샘플
│                   └── meta.json        # 날씨·시드·품질지표
├── compilations/
│   └── {city}/
│       └── {YYYY}-{MM}.mp3              # 월간 합본(크로스페이드)
│       └── {YYYY}-{season}.mp3          # 계절 EP
└── sitemap/
    └── {city}-{YYYY}.json               # 달력 UI 가 한 번에 받는 인덱스
```

### 11.2 메타 인덱스 (DB: Postgres)

```sql
-- 곡 한 곡 = row 하나
create table songs (
  id            uuid primary key,
  city          text not null,
  date          date not null,
  seed          bigint not null,
  key_root      text,           -- 'D'
  mode          text,           -- 'dorian'
  bpm           int,
  duration_sec  int,
  weather       jsonb,          -- 원본 날씨 스냅샷
  features      jsonb,          -- 정규화 특징량
  quality       jsonb,          -- 회귀 테스트 점수
  paths         jsonb,          -- {ir, musicxml, jpg, mp3, wav, midi}
  generator_ver text,           -- 'v1.2.0' 재생성 추적
  created_at    timestamptz default now(),
  unique(city, date, generator_ver)
);

create index on songs (city, date desc);
create index on songs using gin (weather);

-- 사용자 인터랙션
create table plays (
  user_id  uuid,
  song_id  uuid references songs(id),
  played_at timestamptz default now(),
  duration_sec int,
  liked    bool default false
);
```

`generator_ver` 키 덕분에 엔진을 개선해도 과거 곡은 그대로 보존되고,
새 버전은 별도 row 로 누적된다(같은 날·같은 도시에 여러 버전 공존 가능).

### 11.3 보존 정책 (Retention)

| 자산 | 보존 기간 | 사유 |
|---|---|---|
| `ir.json`, `meta.json`, `score.musicxml` | **영구** | 가벼움(KB), 곡 재생성 가능 |
| `midi.mid` | 영구 | 수십 KB |
| `score.jpg` (300dpi) | 영구 | ~600KB |
| `audio.mp3` | 영구 | ~5MB |
| `audio.wav` | **30일** | 30MB · IR로부터 재렌더 가능 |
| `waveform.json` | 1년 | UI 캐시 용도 |
| 월간/계절 합본 | 영구 | 큐레이션 자산 |

도시 1개·1년 기준 영구 자산 ≈ `(0.6 + 5 + 0.05) × 365 ≈ 2.1 GB`. 100개 도시면
연간 ~210 GB(객체 스토리지에서 충분히 합리적).

### 11.4 명명 / 버전 규칙
- 곡 ID 표기: `busy-day/{city}/{YYYY-MM-DD}@v{generator_ver}` 예) `busy-day/seoul/2026-05-06@v1.2.0`
- 사용자에게 보이는 제목: `busy-day · 2026.05.06 · Seoul`
- 공유 URL: `/songs/seoul/2026-05-06` (최신 generator_ver 자동 매핑)

### 11.5 백업
- 객체 스토리지는 cross-region 복제 1개
- DB는 매일 dump → 별도 버킷에 14일 보관
- `ir.json` 만 있으면 audio·jpg 등 모든 파생물 100% 재현되므로, **재해 복구 시
  최소 복원 단위 = ir.json + 코드 + 샘플팩**

### 11.6 달력 API 응답 예
```jsonc
GET /api/calendar?city=seoul&month=2026-05
{
  "city": "seoul",
  "month": "2026-05",
  "days": [
    {
      "date": "2026-05-01",
      "key": "F",  "mode": "lydian",
      "bpm": 84,   "duration": 178,
      "weather_icon": "sun",
      "preview_mp3": "https://cdn/.../preview.mp3",
      "thumb": "https://cdn/.../score-thumb.png"
    },
    { "date": "2026-05-02", "...": "..." }
  ]
}
```
달력 진입 시 1회 호출로 한 달치 메타·썸네일을 받고, 클릭 시 비로소 풀
musicxml/mp3 를 lazy-load.

---

## 12. 단계별 마일스톤 (개정)

1. **MVP-0** : 임의 날씨 → MIDI 1곡(Ionian/Dorian만), 콘솔 CLI
2. **MVP-1** : 실제 OpenWeather 연동 + 4가지 모드 + soundfont 렌더 → mp3
3. **MVP-2** : MusicXML 출력 + Verovio JPG 익스포트
4. **v1.0**  : 웹 달력 UI + OSMD 악보 뷰어 + Tone.js 동기 재생, 도시 선택
5. **v1.1**  : 아카이브 DB(songs 테이블) + 보존 정책 + 월간 합본 자동 생성
6. **v1.2**  : 감성 회귀 테스트 + 좋아요 기반 가중치(수동 라벨)
7. **v2.0**  : 공간 오디오(바이노럴), iOS/안드로이드 위젯, 악보 편집 모드

---

## 13. 열린 결정사항

- 라이선스: 샘플 라이브러리 라이선스(상업 사용 가능 여부) — VSCO2 / Sonatina / 자체 녹음?
- DB / 스토리지: Supabase(Postgres + Storage) 단일 스택 vs S3+RDS 분리. Supabase
  쪽이 MVP 속도에서 유리(이 저장소의 MCP 컨텍스트와도 일치).
- 학습형 멜로디(Magenta MusicVAE) 도입 여부 — 도입 시 "랜덤성"의 정의가 흔들림.
  현재 설계는 **규칙+의사난수**로만 한정해 재현성·검증성을 우선시.
- 악보 표기 단순화 수준: 풀 보이싱 vs 리드시트(현재 설계는 리드시트).
