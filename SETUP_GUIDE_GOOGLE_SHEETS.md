# K-APT 데이터 크롤러: 구글 스프레드시트 연동 및 GitHub Actions 설정 가이드

본 문서는 K-APT 낙찰 데이터를 구글 스프레드시트에 자동으로 적재하고, IP 차단 우회를 위해 GitHub Actions 환경에서 스크립트를 실행하기 위한 설정 가이드입니다.

---

## 1. 구글 클라우드(GCP) 서비스 계정 생성 및 API 활성화

파이썬 스크립트가 구글 스프레드시트에 접근하려면 권한이 있는 '서비스 계정'과 '보안 키(JSON)'가 필요합니다.

1. **Google Cloud Console 접속**: [https://console.cloud.google.com/](https://console.cloud.google.com/)
2. **새 프로젝트 생성** (또는 기존 프로젝트 선택)
3. **API 활성화**
   - 왼쪽 메뉴에서 `[API 및 서비스] -> [라이브러리]` 클릭
   - `Google Sheets API` 검색 후 **사용(Enable)** 클릭
   - `Google Drive API` 검색 후 **사용(Enable)** 클릭
4. **서비스 계정 생성**
   - 왼쪽 메뉴에서 `[API 및 서비스] -> [사용자 인증 정보(Credentials)]` 클릭
   - 위쪽의 `[+ 사용자 인증 정보 만들기] -> [서비스 계정(Service Account)]` 클릭
   - 계정 이름(예: `scraper-bot`) 입력 후 **완료(Done)** 클릭
5. **JSON 키(Key) 발급**
   - 생성된 서비스 계정 목록에서 방금 만든 계정 클릭
   - 상단 탭에서 `[키(Keys)] -> [키 추가(Add Key)] -> [새 키 만들기(Create New Key)]` 클릭
   - **JSON** 형식 선택 후 만들기 클릭
   - ⚠️ 다운로드된 `.json` 파일은 절대 외부(GitHub 공개 리포지토리 등)에 유출되지 않도록 주의하세요!

---

## 2. 구글 스프레드시트 설정

스크립트가 데이터를 기록할 빈 스프레드시트를 만들고 접근 권한을 줍니다.

1. 구글 드라이브(또는 스프레드시트)에서 새 스프레드시트 생성.
2. 1행에 아래와 같이 **헤더(컬럼명)를 순서대로 작성**합니다:
   `입찰마감일` | `물건번호` | `낙찰방법` | `입찰제목` | `낙찰 순번` | `응찰회사명` | `응찰회사사업자번호` | `대표자명` | `입찰금액` | `평가점수` | `낙찰여부` | `낙찰회사주소`
3. 브라우저 주소창(URL)을 보고 **시트 ID(Spreadsheet ID)** 를 복사해 기록해 둡니다.
   - 예: `https://docs.google.com/spreadsheets/d/여기부터_저기까지_긴_문자열/edit`
4. 우측 상단의 **[공유(Share)]** 버튼 클릭
5. 앞서 발급받은 '1. 구글 클라우드' 단계의 **서비스 계정 이메일**(예: `scraper-bot@...iam.gserviceaccount.com`)을 입력 창에 붙여넣기 합니다.
6. 권한을 **[편집자(Editor)]** 로 설정하고 공유 완료.

---

## 3. GitHub 리포지토리 생성 및 소스코드 업로드 (현재 단계)

아직 GitHub에 리포지토리(저장소)를 만들지 않으셨다면, 다음 방법 중 가장 편한 방법을 선택하여 소스코드를 업로드해 주세요. (Git이 설치되어 있지 않다면 '방법 1'이 가장 쉽습니다.)

### 방법 1: GitHub 웹사이트에서 직접 업로드 (가장 쉬움)
1. GitHub 웹사이트([https://github.com/](https://github.com/))에 로그인합니다.
2. 우측 상단의 **[+]** 아이콘을 누르고 **[New repository]** 를 클릭합니다.
3. **Repository name**에 원하는 이름(예: `kapt-scraper`)을 적고, Public 또는 Private을 선택한 뒤 **[Create repository]** 버튼을 누릅니다.
4. 생성된 리포지토리 화면 중간의 **"uploading an existing file"** 링크를 클릭합니다.
5. 현재 내 PC에 있는 파이썬 코드들(`main.py`, `scraper.py`, `.github` 폴더 등 전체)을 마우스로 드래그 앤 드롭하여 브라우저에 올립니다.
   *(주의: 1단계에서 받은 `client_secret.json` 등 권한 키 파일은 절대 올리면 안 됩니다!! `code` 폴더와 `.github` 폴더 위주로 올려주세요.)*
6. 하단의 **[Commit changes]** 버튼을 눌러 업로드를 완료합니다.

### 방법 2: GitHub Desktop 사용 (추천)
1. [GitHub Desktop](https://desktop.github.com/) 프로그램을 다운로드하고 설치 및 로그인합니다.
2. `[File] -> [New repository...]` 를 클릭하고 이름과 코드가 있는 로컬 경로(`f:\프로젝트\KAPT 낙찰정보 가져오기`)를 지정하여 생성합니다.
3. 프로그램 상단 메뉴의 `[Repository] -> [Repository settings] -> [Ignored Files]` 에 `*.json` 과 `*.csv` 를 적어 보안 키가 올라가지 않게 합니다.
4. 좌측 하단의 summary에 "Init" 등을 적고 **[Commit to main]** 클릭 후, 상단의 **[Publish repository]** 버튼을 눌러 GitHub로 코드를 올립니다.

---

## 4. GitHub 리포지토리 Secrets 설정 (매우 중요)

이제 올라간 소스코드가 담긴 **GitHub 리포지토리(Repository)** 페이지로 이동합니다.
GitHub Actions 환경에서 파이썬 코드가 구글 시트에 안전하게 접근할 수 있도록 보안 키를 숨겨서 등록해야 합니다.

1. 리포지토리 상단의 `[Settings] -> [Secrets and variables] -> [Actions]` 메뉴 클릭 (왼쪽 사이드바).
2. **[New repository secret]** 버튼 클릭
3. 첫 번째 Secret 등록:
   - **Name**: `GCP_SERVICE_ACCOUNT_JSON`
   - **Secret**: 1단계에서 다운로드 받은 확장자가 `.json`인 파일의 속 내용을 메모장으로 열어서 전체 복사를 한 뒤 이곳에 붙여넣기.
   - [Add secret] 클릭
4. 두 번째 Secret 등록:
   - **Name**: `GOOGLE_SHEET_ID`
   - **Secret**: 2단계에서 기록해둔 **시트 ID 문자열**을 붙여넣기.
   - [Add secret] 클릭

---

## 5. 로컬 환경 테스트 (선택 사항)

자신의 PC에서 먼저 구글 스프레드시트에 잘 들어가는지 테스트할 수 있습니다.

1. 필요한 패키지 설치:
   ```bash
   pip install gspread oauth2client
   ```
2. 다운로드 받은 JSON 키 파일을 현재 작업 폴더(코드 폴더) 안에 넣고 이름을 `client_secret.json`으로 변경합니다.
3. `.env` 파일을 만들거나 윈도우 환경 변수로 시트 ID 설정:
   ```env
   GOOGLE_SHEET_ID=여러분의_시트_ID
   ```
   *참고: `client_secret.json` 등 보안 파일은 반드시 `.gitignore` 에 추가하여 GitHub에 백업되지 않도록 하세요.*
4. `python main.py` 실행 시 콘솔에 "구글 시트에 00건이 저장되었습니다."와 함께 구글 시트에 값이 써지는지 확인합니다.

이제 완벽히 세팅되었습니다! 매일 정해진 시간이나 원할 때 GitHub Actions 탭에서 코드를 실행할 수 있습니다.
