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

## 9. 단계별 마일스톤

1. **MVP-0** : 임의 날씨 → MIDI 1곡(Ionian/Dorian만), 콘솔 CLI
2. **MVP-1** : 실제 OpenWeather 연동 + 4가지 모드 + soundfont 렌더 → mp3
3. **MVP-2** : 폼/아르페지오/텍스처 레이어, 휴머나이즈, LUFS 정규화
4. **v1.0**  : 웹 플레이어(Tone.js), 도시 선택, 매일 자동 갱신, 곡 아카이브
5. **v1.1**  : 감성 회귀 테스트 + 사용자 좋아요 기반 가중치 학습(수동 라벨)
6. **v2.0**  : 공간 오디오(바이노럴), iOS/안드로이드 위젯

---

## 10. 열린 결정사항

- 라이선스: 샘플 라이브러리 라이선스(상업 사용 가능 여부) — VSCO2 / Sonatina / 자체 녹음?
- 저장: 곡당 wav 약 30MB → 도시 100개·1년이면 1TB. mp3만 영구 보관, wav는 30일.
- 학습형 멜로디(Magenta MusicVAE) 도입 여부 — 도입 시 "랜덤성"의 정의가 흔들림.
  현재 설계는 **규칙+의사난수**로만 한정해 재현성·검증성을 우선시.
