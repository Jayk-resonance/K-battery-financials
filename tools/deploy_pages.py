#!/usr/bin/env python3
"""dashboard.html -> docs/index.html (GitHub Pages 배포용 복사).

사용법:
  python3 tools/build_dashboard_data.py     # 데이터 갱신
  python3 tools/assemble_dashboard.py       # dashboard.html 생성
  python3 tools/deploy_pages.py             # docs/index.html 로 복사
  git add docs && git commit && git push    # Pages 자동 반영

이 저장소는 대시보드 전용(단일 목적)이므로 docs/ 루트에 바로 배포한다.
배포 주소는 저장소 Settings → Pages에서 소스를 이 브랜치의 /docs 로 설정한 뒤 <pages-url>/.

주의: docs/index.html 은 **생성물**이다. 직접 편집하지 말 것 —
      다음 배포 때 덮어쓰인다. UI 수정은 projects/dashboard/dashboard_template.html 에서 한다.
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 저장소 루트
SRC = os.path.join(ROOT, "projects", "dashboard", "dashboard.html")
DST_DIR = os.path.join(ROOT, "docs")
DST = os.path.join(DST_DIR, "index.html")

if not os.path.exists(SRC):
    raise SystemExit("dashboard.html 이 없습니다. 먼저 assemble_dashboard.py 를 실행하세요.")

os.makedirs(DST_DIR, exist_ok=True)
shutil.copy2(SRC, DST)

# Jekyll 처리 비활성화 (밑줄 시작 경로 등이 무시되는 문제 방지)
nojekyll = os.path.join(DST_DIR, ".nojekyll")
if not os.path.exists(nojekyll):
    open(nojekyll, "w").close()

print(f"배포 파일 갱신: docs/index.html ({os.path.getsize(DST)//1024}KB)")
print("다음: git add docs && git commit -m 'deploy: 대시보드 갱신' && git push")
