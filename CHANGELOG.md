# Changelog

## 1.4.0

- `npx` / `uvx` から事前導入なしに `--setup` を実行可能。CLI が実行版と同じ GitHub Release を開発用依存へ登録し、Linter・選択したフレームワーク・設定・native lock を揃える。
- 同じ入口から明示した新版へ更新可能。公式配布 URL は実行 CLI の版に追従し、採用版と設定を案件へ保存。
- Python の依存確認は利用側の環境を検査。一時実行 CLI の環境に Django / FastAPI がなくても、利用側の導入・確認ができる。
- ローカル artifact や別の配布先には `--source URL` を指定。既存の公式以外の配布元は保持。
- 一時実行からの preview・導入・確認・更新、再実行、既存設定保持、既存更新 script と revert を検証。導入・更新・公開の手順を更新。

既存の事前導入、`npm exec` / `uv run`、`--write --sync`、`--check` は引き続き利用可能。Profile の依存版・lint ルールは 1.3.0 と同じ。Node.js / npm または Python / uv と利用側 manifest が前提。公開済み配布物は差し替えない。

## 1.3.0

- TypeScript / Python CLI に `--setup` を追加。設定の適用・Profile の依存登録・native lock の更新・依存のインストールを一回で実行。
- npm パッケージが ESLint / TypeScript の固定版に直接依存。初回は配布パッケージ一つだけを導入し、CLI で Node.js / Hono / Next.js の構成を揃えられる。
- Python も wheel 一つと CLI から Ruff・Django または FastAPI / Uvicorn を導入。実行用 / 開発用依存の分離は維持。
- 配布パッケージだけからの導入、CLI の一括 setup、再実行、既存設定保持、旧版からの更新 / revert を検証。導入・更新・公開の手順も更新。

既存のオプションなし preview、`--write --sync`、`--check` は引き続き利用可能。Profile の依存版・lint ルールは 1.2.0 と同じ。既存案件は通常の更新手順で 1.3.0 に更新できる。既存の lint 設定は参照統合後に `--adopt --setup` で登録する。

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
