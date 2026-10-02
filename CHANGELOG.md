# Changelog

## 1.2.0

- `python-django` と `python-fastapi` を追加。Django 6.1.1 / FastAPI 0.142.2 / Uvicorn 0.54.0 と対応する Ruff の `DJ` / `FAST` ルールを固定。
- CLI がフレームワークを利用側の実行用依存に登録し、preset・Ruff の開発用依存と分離。uv lock とコピーした設定を同時に更新。
- Django の system check / テストを更新 script に追加。FastAPI のアプリテストは caller の `test-command` で指定。
- 両フレームワークの最小 HTTP アプリ、開発依存なしの実行、旧版からの依存更新、設定保持、手動変更・削除 / Profile 切替の拒否、revert を検証。

既存 Profile のルールは変更しない。Python スクリプトは従来の設定で更新可能。フレームワークの切替、業務コード、DB migration と本番設定は案件側で移行する。既存の更新 workflow の参照タグを `v1.2.0` に更新すると新 Profile も対象になる。

## 1.0.0

- Node.js、Hono、Next.js、Python スクリプトの構成 Profile。
- フレームワーク・依存の固定版と、対応する lint / TypeScript 設定を一括管理。
- 依存差分の preview・適用・整合チェック、案件側の変更保護。
- Hono / Next.js の検証、依存と設定の更新・復旧を実証するデモ。

## 1.1.0

- GitHub Release から npm tarball と Python wheel / sdist を配布。npm・PyPI アカウント不要。
- TypeScript CLI に `--sync` を追加し、Profile 依存・npm lock・配布版の整合性を検査。
- Python wheel に Ruff の exact version と設定を同梱。案件の上書きを保持する導入・更新・検査 CLI を追加。
- 両言語の更新 script と、同じ major の Release から更新 PR を作る reusable workflow を追加。
- 実際の tarball / wheel の更新、手動変更の拒否、設定保持、lock と設定の revert を CI で検証。

既存 Git 配布の TypeScript import と Python 設定パスは保持。Python の wheel 方式へは、旧 submodule の取り外しと設定参照の変更をレビューして移行する。フレームワーク切替と業務コード移行は引き続き手動。

## 1.1.1

- npm 12 の URL 配布制限に対応し、導入・更新・復旧で direct remote package を明示的に許可。
- HTTP の tarball を使う回帰テストを追加。公開済み 1.1.0 の配布物は差し替えず、修正は新しい版に収録。
