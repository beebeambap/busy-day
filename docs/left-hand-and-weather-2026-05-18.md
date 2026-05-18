# busy-day — 왼손 작곡 체계 & 날씨 알고리즘 (2026-05-18)

`song-selection-2026-05-18.md`의 보조 문서. 두 가지를 다룬다:
1. **왼손 작곡(harmony + bass)이 어떻게 결정되는가** — 결론: **장르 기반 룩업 테이블**
2. **날씨 입력이 어떻게 곡으로 변환되는가** — 4-d feature 공간 → 가중 추첨

---

## 1. 왼손은 정말 장르 기반인가? — **Yes**

`compose/comping.py`의 핵심 자료구조는 **장르 × 박자(beats_per_bar)** 2-D 룩업 테이블이다. 모든 진입점이 이 테이블을 통한다.

```python
# comping.py — 왼손 룩업 구조
_H44 = { "ambient": [...], "neo_classical": [...], "folk": [...],
         "bossa_nova": [...], "jazz_ballad": [...], "lo_fi": [...] }
_H34 = { ... }   # 3/4 (왈츠)
_H68 = { ... }   # 6/8 (지그)

_B44 = { ... }   # 베이스 동일 구조
_B34 = { ... }
_B68 = { ... }

# 매 마디 호출
harmony_pattern_for(genre, meter, section, rng)
bass_pattern_for   (genre, meter, section, rng)
```

각 셀(cell)은 `(start_beat, dur_beats, voice_kind, vel_mult)` 튜플의 리스트. **장르마다 canonical 1개 + alt 1–4개**가 있고, 섹션별로 다음 확률로 추첨된다.

| 섹션 | canonical | alt |
|---|---|---|
| INTRO / OUTRO | 100% | 0% |
| A | 70% | 30% |
| B | 25% | 75% |
| A_PRIME | 60% | 40% |

→ "B 섹션에서 다른 셀이 들리도록" 강제하는 구조. 같은 패턴이 16마디 반복되지 않게 막는 장치.

**날씨/intent는 왼손 패턴 선택에 직접 영향 안 줌.** 둘 다 *장르*를 통해서만 간접 영향:
- 날씨 → features → `pick_genre()` → 장르 결정 → 패턴 테이블 선택
- intent의 `preferred_genre` / `avoid_genres`도 동일 경로

예외: tape 편곡(transform_ir)에서 `genre_override` 적용 시 동일 멜로디를 새 장르 패턴으로 재배치.

---

## 2. 장르별 왼손 패턴 카탈로그 (4/4 기준)

모든 패턴은 한 마디(4 beats) 안에서 정의. 표기:
- `T@D` = 비트 T에서 D비트 길이로 hit (예: `0@4` = 다운비트에 온음표)
- voice 종류 — harmony: `all` 전체화음 / `top` 상성부(3rd+5th[+7th]) / `top3` 상3음 / `root_5` 근음+5도
- voice 종류 — bass: `root` 근음 / `fifth` 5도 / `third` 3도 / `fifth_up` 옥타브 위 5도

### 2.1 Ambient — 패드, 정적

| | Canonical | Alt 1 | Alt 2 | Alt 3 |
|---|---|---|---|---|
| **Harmony** | `all 0@4` (온음표 1발) | `all 0@2` + `top 2@2` (호흡) | `all 0.5@3.5` (Eno suspension, 비트1 무음) | — |
| **Bass** | `root 0@4` (드론) | `root 0@2` + `fifth 2@2` | `root 0@2` (절반 무음) | 쿼터펄스: `root third fifth third` |

**의도**: 가장 조용한 장르 — 패드 한 발이 마디 전체를 채우는 게 기본. 빨라지면 (alt 3 베이스로) 쿼터 펄스 추가.

### 2.2 Neo-classical — 알베르티 + 블록 코드

| | Canonical | Alt 1 | Alt 2 | Alt 3 | Alt 4 |
|---|---|---|---|---|---|
| **Harmony** | 블록+3 스탭 `all 0@1 / top 1@1 / top 2@1 / top 3@1` (Yiruma) | 긴 다운비트 + 아르페지오 꼬리 | 굴리는 아르페지오 (Einaudi 페달 sustain) | 3비트 sustain + 답구절 | — |
| **Bass** | **알베르티 8분 8발** (모차르트 왼손) | walking 쿼터 1-3-5-3 | 페달 포인트 (root 0@4) | 옥타브 도약 (root → fifth_up) | 스칼라 walking (Schubert 리트) |

**의도**: 클래식 피아노 톤. 알베르티는 신호: "이건 피아노 솔로 작품". 페달 포인트(alt 2)는 정적 분위기.

### 2.3 Folk — 부엉-칙 + 켈틱 드론

| | Canonical | Alt 1 | Alt 2 | Alt 3 |
|---|---|---|---|---|
| **Harmony** | `root_5 0/2 + top 1/3` (부엉-칙) | + 2/4박 8분 답구절 | 켈틱 드론 `root_5 0@2 / top 2@2` (Muji-Celtic 핵심) | 릴팅 픽업 `root_5 0.5@0.5 / top 1@1.5 / root_5 2.5@1.5` |
| **Bass** | boom-chick `root fifth root fifth` | walking 1-5-3-↑5 | **켈틱 드론 root 0@4** (Muji 핵심) | stepwise 1-3-5-1 (Nick Drake) | 갤로핑 8분 (Tom Petty / 아메리카나) |

**의도**: 통기타 어쿠스틱. **Celtic drone (alt 2)는 open_fifth voicing과 페어** — Muji 매장 BGM의 정수.

### 2.4 Bossa Nova — 보사 베이스 + 신코페이션

| | Canonical | Alt 1 | Alt 2 | Alt 3 |
|---|---|---|---|---|
| **Harmony** | bossa básica: `root 0@.5 / top .75@1 / fifth 2@.5 / top 2.5@.5 / top 3@1` (and-of-1 anticipation) | late comp (뒤로 밀린 셀) | partido-alto esparso (2발만, 신코페이션 헤비) | ballad bossa (Tom Jobim) |
| **Bass** | **dotted-quarter 1.5+0.5+1.5+0.5** (보사 시그니처) | walking 핏치 1-3-5-↑5 | tumbao-feel (긴 root + 신코페이션 fifth) | 2-feel (half-note root + fifth) | 쿼터 walking (Jobim 후기) |

**의도**: 보사 정체성은 베이스의 1.5+0.5 리듬. 박자가 어긋나는 듯한 느낌은 의도된 것 — alt 4의 직선 쿼터로 너무 가면 "보사가 아님".

### 2.5 Jazz Ballad — 페달 + walking

| | Canonical | Alt 1 | Alt 2 | Alt 3 | Alt 4 |
|---|---|---|---|---|---|
| **Harmony** | 긴 스탭 `top3 0@2 / top 2@.5 / top3 2.5@1.5` | 4스탭 분주 | **rubato 온음표** `top3 0@4` (Bill Evans pause) | 2스탭 호흡 (1박 + 3박만) | — |
| **Bass** | walking 쿼터 1-3-5-3 | chromatic feel (fifth_up 삽입) | pedal-then-walk (Bill Evans 트리오) | half-note 두 발 | **bebop straight-eighths 8발** (Paul Chambers / Ray Brown) |

**의도**: 카페 재즈. RAIN 편곡이 이 장르로 강제 변환 — swing 1.50:1 + 18ms behind-the-beat 그루브로 "비 오는 카페" 톤.

### 2.6 Lo-fi — 오프비트 + 808

| | Canonical | Alt 1 | Alt 2 | Alt 3 |
|---|---|---|---|---|
| **Harmony** | lazy 2-hit `top 0.5@1.5 / top 2.5@1.5` (오프비트만) | 3hit + 신코페이션 | float (and-of-2 + and-of-4만) | **tape hiss** `top 0@4` (단발 sustain) |
| **Bass** | half + half root/fifth | walking 1-3-5-3 | **808 sustain** (긴 root + 짧은 fifth ghost) | anticipated drop | J Dilla 마이크로 신코페이션 6발 |

**의도**: 비트 그리드를 일부러 어긋남. 다운비트를 거의 안 침. 808 베이스(alt 2)는 hip-hop 서브베이스.

---

## 3. 박자별 차이 — 3/4, 6/8은 셀이 1–2개로 축소

| 박자 | 셀 개수 | 비고 |
|---|---|---|
| 4/4 | canonical + 2–4 alt | 가장 풍부 |
| 3/4 | canonical + 1 alt | 왈츠 — folk는 boom-chick-chick |
| 6/8 | canonical + 1–3 alt | 지그 — folk만 4 alt (켈틱 드론, 갤로프) |

3/4와 6/8은 사실상 folk 전용 (다른 장르도 가지만 셀 다양성이 적음). 산책 intent가 4/4를 강제하는 이유: 3/4 왈츠는 "걷는 박자"가 아님.

---

## 4. 날씨 → 작곡 알고리즘

### 4.1 4-d Feature 공간 (`compose/features.py`)

| feature | 계산식 | 범위 |
|---|---|---|
| `warmth` | `(temp_c + 10) / 40 + (humidity - 60) / 200` | 0(-10°C) → 1(30°C 이상) |
| `brightness` | `1 - cloud_pct/130 - min(precip,20)/30` | 0(흐림/비) → 1(맑음/건조) |
| `wetness` | `precip_mm/20 + humidity/250 - 0.2` | 0(건조) → 1(20mm 강수) |
| `calmness` | `1 - min(wind,10)/10 - min(temp_range,15)/30` | 0(강풍/일교차 큼) → 1(잔잔) |

모두 `[0, 1]`로 클립. `humidity`는 warmth와 wetness에 동시 기여하지만 가중치가 달라 독립적.

**예시 — 2026-05-18 서울 (가상)**:
```
temp=22, cloud=20, precip=0, wind=2, humidity=55, temp_range=8
→ warmth=0.78, brightness=0.85, wetness=0, calmness=0.53
```
→ 맑고 따뜻하고 조금 활동적인 날.

### 4.2 Spec 결정 알고리즘 (`compose/mapping.py`)

각 결정은 **가중치 추첨** (`_weighted_choice`). 기본 가중치 + features 가산.

#### 4.2.1 Mode (`pick_mode`)
```
ionian     0.30 + 0.40 × brightness                       # 밝음 → 장조
dorian     0.25 + 0.30 × (1 - brightness)                 # 어두움 → 도리안
lydian     0.10 + 0.30 × (brightness × calmness)          # 맑음 + 잔잔
mixolydian 0.15 + 0.30 × (warmth × (1 - wetness))         # 따뜻 + 건조
aeolian    0.10 + 0.45 × (wetness × (1 - brightness))     # 젖음 + 어두움 → 단조
```
intent의 `mode_bias`가 있으면 이 추첨을 건너뛰고 강제.

#### 4.2.2 Key (`pick_key`)
```
base = {C:1.0, D:1.2, E:1.0, F:1.0, G:1.1, A:0.9, B:0.6}
D += 0.5 × warmth          A += 0.4 × warmth        # 따뜻 → D/A
E += 0.3 × (1-warmth)      G += 0.3 × (1-warmth)    # 추움 → E/G
F += 0.4 × wetness                                  # 비 → F
```
가장 추첨될 가능성이 높은 키: 기본 D (1.2), B는 의도적으로 낮음 (1.6kHz 영역에 더블 샵 너무 많음).

#### 4.2.3 Genre (`pick_genre`)
```
ambient      += 0.5 × calmness
bossa_nova   += 0.6 × brightness × warmth           # 밝고 따뜻
jazz_ballad  += 0.5 × warmth × wetness              # 비 오는 카페
lo_fi        += 0.5 × wetness × (1-brightness)      # 흐리고 비
neo_classical += 0.4 × (1-warmth)                   # 추움
folk         += 0.4 × brightness × (1-wetness)      # 맑고 건조
```
intent의 `preferred_genre`는 ×2.5 가산, `avoid_genres`는 ×0.05 감산, `force_genre`는 완전 강제.

#### 4.2.4 BPM (`pick_bpm`)
1. `center = 64 + (1-calmness) × 36` → 활동적일수록 빠름 (64–100)
2. 장르 조정: bossa +10, folk +8, jazz +2, lo_fi −4, ambient −2
3. `± rng.uniform(-4, 4)` 흔들기
4. 최종 60–112 범위로 클립

**intent의 `bpm_clamp`가 있으면 위 식 전부 건너뛰고 `clamp_lo + rng.randint(0, hi-lo)`로 직접 추첨.** 산책(walk)이 120 BPM에 안착하는 이유 — pick_bpm의 112 글로벌 cap을 우회.

#### 4.2.5 Meter (`pick_meter`)
- bossa_nova: 무조건 4/4
- folk: `3/4:0.30 / 4/4:0.55 / 6/8:0.15` (4/4 가중 상향됨 — 너무 자주 왈츠가 뽑혀 perceived energy가 떨어졌었음)
- ambient: 4/4(0.6) / 6/8(0.4)
- 그 외: `3/4:0.20 / 4/4:0.65 / 6/8:0.15`

intent의 `force_meter` (산책=4/4)가 있으면 위 추첨 건너뛰고 강제.

#### 4.2.6 Motif (`pick_motif`)
`data/motifs.json` 카탈로그에서 tag 기반 가산. 주요 가산:
- `warm` +0.6×warmth, `bright` +0.6×brightness, `wet` +0.6×wetness
- `sparse` +0.4×calmness, `wide_leap` +0.4×brightness
- `celtic` +0.5 (고정 — Muji-Celtic 핵심), `pentatonic` +0.3×brightness

### 4.3 Activity → 멜로디 밀도

`_apply_activity_density()` (arrange.py)는 spec 결정 *후* 멜로디 단계에서 적용:
```
activity = 1 - features.calmness   # active intent는 calmness↓ → activity↑
if activity > 0.40:
    p_insert = min(0.85, (activity - 0.30) × 1.5)
    # 0.6박 이상의 긴 음표를 확률 p_insert로 passing tone으로 쪼갬
```
산책(walk)이 `calmness -0.25`를 거는 이유 — 멜로디 밀도까지 적극적으로 만들기 위해.

### 4.4 오른손 평행 3도 화음

활동도 따라 활성화 (arrange.py 멜로디 루프):
```
첫 음 (note_idx==0, dur≥0.35박): 항상 3도 화음 추가
그 외 (dur≥0.35박): 확률 0.20 + activity × 0.35로 추가
```
산책 같은 활동적 intent → 마디당 더 많은 3도 화음 → 풍부한 오른손.

---

## 5. 결정 흐름 요약 (한 마디 기준)

```
weather (KMA aggregate)
    │
    ▼  features.extract()
[warmth, brightness, wetness, calmness]
    │
    ├─ intent.apply() ─► features 보정 + bias
    │
    ▼  _decide_spec()  (가중 추첨, intent bias 우선)
{key, mode, genre, bpm, meter, motif}
    │
    ▼  compose_ir()
    │
    ├─ 마디 N의 chord_degree 결정 (progressions.py)
    │
    ├─ 오른손 (melody):  motif → 음정 추첨 → activity 기반 밀도 부스트 → 평행 3도
    │
    └─ 왼손 (harmony + bass):
         ┌── _H{34,44,68}[genre]에서 셀 추첨 (canonical/alt, section 가중)
         └── _B{34,44,68}[genre]에서 셀 추첨 (canonical/alt, section 가중)
         → 셀의 (start, dur, voice_kind)을 chord_degree와 키/모드에 적용해 음정 생성
```

---

## 6. 핵심 takeaway

1. **왼손 = 장르** — features/날씨는 장르를 *고르는* 단계에서만 작용. 일단 장르가 정해지면 왼손 패턴 후보는 고정.
2. **장르 정체성은 베이스 리듬** — 보사노바의 1.5+0.5, folk의 boom-chick, neo-classical의 알베르티 같은 시그니처 리듬을 보존해야 장르가 "들림".
3. **다양성 = section + alt** — 같은 장르 안에서 16마디 동일을 막는 장치는 (a) 마디별 alt 추첨, (b) 섹션별 confidence 곡선.
4. **날씨는 4-d 벡터** — temperature/cloud/precip/wind/humidity → (warmth, brightness, wetness, calmness). 모든 결정이 이 4개에서 파생.
5. **intent는 features를 미는 동시에 일부 결정을 hard-pin** — 예: 산책의 BPM clamp는 features 영향을 완전히 우회.
