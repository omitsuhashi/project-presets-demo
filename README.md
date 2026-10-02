# project-presets-demo

言語・フレームワーク・依存パッケージの版と、それに合う lint / TypeScript 設定を配布するデモです。**GitHub Release の npm tarball / Python wheel を固定して導入します。npm・PyPI のアカウントは不要です。**

## 最初の導入

既存の `package.json` / `pyproject.toml` があるプロジェクトでは、`npx` / `uvx` から CLI 一回で設定・必要な依存・lockfile が揃います。配布パッケージの事前インストールも、Linter やフレームワークの個別インストールも不要です。

```sh
# TypeScript: node / hono / next のいずれかを選ぶ
npx --yes --allow-remote=root --ignore-scripts \
  https://github.com/omitsuhashi/project-presets-demo/releases/download/v1.4.0/project-presets-demo-1.4.0.tgz \
  typescript-node --setup

# Python: scripts / django / fastapi のいずれかを選ぶ
uvx --python 3.12 \
  --from https://github.com/omitsuhashi/project-presets-demo/releases/download/v1.4.0/project_presets_demo-1.4.0-py3-none-any.whl \
  project-presets-python python-django --setup
```

既存の lint 設定がある場合は、[導入手順の既存案件](docs/install.md#既存案件) に従って参照を統合し `--adopt --setup` を使います。Node.js / npm・Python / uv の導入、新規 manifest の作成手順も導入手順に記載しています。オプションなしは preview、`--check` は整合性の確認です。CLI が採用版の共通パッケージも開発用依存に登録するため、CI では npm / uv lock から同じ設定を再現できます。

## 使い方・更新手順

| 読み手と作業 | 手順書 | 完了時の状態 |
| --- | --- | --- |
| 利用側: 初めて導入する | [TypeScript / Python の導入](docs/install.md) | Profile・配布版・設定・lock を固定して commit |
| 配布側: 共通設定・依存を更新する | [配布物の更新・公開](docs/publish.md) | 検証済み commit にタグを付け、Release の配布物を公開 |
| 利用側: 新版を適用する | [更新 PR・適用・復旧](docs/update.md) | 更新をレビューしてマージし、lock から実行環境を再構築 |

配布側の更新 PR → 固定タグ / GitHub Release → 利用側の更新 PR → マージ / 依存の再導入、という流れです。Release の公開だけでは利用側は変わりません。手動または [更新 workflow](examples/update-presets.yml) で更新 PR を作ります。

## 選べる構成

| Profile | 用途 | 主な依存と設定 |
| --- | --- | --- |
| `typescript-node` | Node.js 24 | TypeScript 6.0.3、ESLint 9.39.5、NodeNext / strict |
| `typescript-hono` | Node.js 24 / HTTP API | Hono 4.13.12、Node adapter 2.1.3、Node 用 lint / TypeScript |
| `typescript-next` | Node.js 24 / Next.js App Router | Next.js 16.3.8、React 19.3.0、対応する lint / 型定義 / compiler 設定 |
| `python-scripts` | Python 3.12 / スクリプト | Ruff 0.16.10、correctness / import / bugbear 設定、print を許可 |
| `python-django` | Python 3.12 / Django | Django 6.1.1、Ruff の `DJ` ルール、service 用の print 検査 |
| `python-fastapi` | Python 3.12 / HTTP API | FastAPI 0.142.2、Uvicorn 0.54.0、Ruff の `FAST` ルール、`Annotated` を推奨 |

[profiles.json](profiles.json) と各パッケージの manifest を CI で照合します。Next.js と `eslint-config-next` も同じ版に揃え、代表アプリで検証します。

ESLint 9 は [2026-08-06 に EOL](https://eslint.org/version-support/) です。Next.js の React plugin の peer 対応に合わせて、このデモでは 9 を固定しています。本運用に昇格する前に、保守中のツールを使える組み合わせへ移行してください。このデモの検証対象と、組織のサポート範囲は別に決めます。

## 配布するものと管理する範囲

[公開版 v1.4.0](https://github.com/omitsuhashi/project-presets-demo/releases/tag/v1.4.0) は npm tarball・Python wheel / sdist・`SHA256SUMS` を含みます。初回導入と明示した版の適用は、公開 URL から GitHub 認証なしで行えます。

- TypeScript: Profile の実行用 / 開発用依存と marker を管理。利用側は共通 package の設定を import / extends し、案件固有の上書きを保守。
- Python: framework は実行用依存、preset / Ruff は開発用依存。コピーした共通設定と marker を管理し、案件固有の上書きは `pyproject.toml` で保守。
- 両言語: アプリのコード・追加テスト・フレームワーク移行・DB migration・デプロイは利用側の責任。管理依存・Python の配布設定の手動変更 / 削除、TypeScript の設定ファイルの削除、Profile 切替は CLI が検出して停止。

[配布側の Dependabot](.github/dependabot.yml) は更新候補を作ります。採用版と共通設定を揃え、[release workflow](.github/workflows/release.yml) で検証・公開します。公開済みタグ・配布物は差し替えません。更新用 script は [scripts/update-consumer.py](scripts/update-consumer.py) です。

## 検証

```sh
npm ci --ignore-scripts
uv lock --check
npm run lint
npm run demo:ts
npm run demo:py
npm test
```

CI では manifest / catalog の整合性、Hono の応答、Next.js の build、Django / FastAPI のアプリを検証します。実際の tarball / wheel の導入・依存更新、ネイティブの lock、設定保持、手動変更の拒否、開発依存なしの Python 実行、revert を確認します。テスト用の `v2.0.0` は一時 fixture です。

旧 Python submodule の設定パスは互換用に残しています。新規導入は wheel を使い、移行方法は [導入手順](docs/install.md#既存案件) を参照してください。

MIT License.
