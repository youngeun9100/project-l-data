# Project L Lotto Data

Project.L 앱에서 사용하는 로또6/45 역대 당첨번호 데이터 저장소입니다.

## 제공 파일

- `data/winning_numbers.json`: 1회부터 최신 회차까지의 당첨번호
- `scripts/update_lotto.py`: 동행복권 회차별 결과를 확인하고 데이터 파일을 갱신하는 스크립트
- `.github/workflows/update-lotto.yml`: 매주 자동 갱신 및 검증 작업

앱에서는 다음 주소로 JSON을 읽을 수 있습니다.

```text
https://raw.githubusercontent.com/youngeun9100/project-l-data/main/data/winning_numbers.json
```

## 데이터 형식

```json
{
  "schemaVersion": 1,
  "latestDraw": 1236,
  "latestDrawDate": "2026-08-08",
  "source": "https://www.dhlottery.co.kr/lt645/winNumber",
  "draws": [
    {
      "draw": 1,
      "date": "2002-12-07",
      "numbers": [10, 23, 29, 33, 37, 40],
      "bonus": 16
    }
  ]
}
```

## 갱신 원칙

- 동행복권 회차별 당첨번호 화면에서 사용하는 데이터 응답을 원본으로 사용합니다.
- 모든 회차가 1회부터 빠짐없이 이어지는지 검사합니다.
- 당첨번호가 1~45 사이의 서로 다른 숫자 6개인지 검사합니다.
- 잘못된 응답이나 네트워크 오류가 발생하면 기존 JSON을 변경하지 않습니다.
- 과거와 동일한 6개 조합이 다시 등장하는 것은 가능한 정상 결과이므로 오류로 처리하지 않습니다.

## 주의

이 저장소는 동행복권의 공식 서비스가 아닙니다. 원본 사이트의 구조가 바뀌면 자동 갱신 스크립트를 수정해야 할 수 있습니다.

