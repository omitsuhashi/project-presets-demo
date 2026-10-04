# project-presets-demo

言語・フレームワーク・依存パッケージの版と、それに合う lint / TypeScript 設定を配布するデモです。**GitHub Release の npm tarball / Python wheel を固定して導入します。npm・PyPI のアカウントは不要です。**

利用側の流れは **Profile を選ぶ → 固定した成果物で導入する → 更新 PR をレビューする → lock から再構築する** です。AWS インフラは独立した追加機能です。

この README の導入例は公開済み v2.1.0 を使います。開発中の v2.2.0 は、6つの Profile の版を独立して管理する未公開版です。公開タグは1回につき1つで、`release-manifest.json` が各 Profile の版と元の配布先を記録します。変更した Profile だけ build し、利用側は自分の版が変わっていなければ終了します。[版と公開単位](docs/publish.md#版と公開単位) と [既存 workflow の移行](docs/update.md#テンプレート別リリースへの移行) を参照してください。

## コードを読む入口

| 責務 | 入口 |
| --- | --- |
| Profile の構成と依存版 | [版を持たない Profile 定義](profiles/definitions.json)、版の正本は [package.json](package.json) / [pyproject.toml](pyproject.toml) |
| 利用側の TypeScript 導入・更新 | [CLI](scripts/apply-profile.mjs) → [変更計画](scripts/presets/plan.mjs) → [適用・検証](scripts/presets/project.mjs) |
| 利用側の Python 導入・更新 | [CLI](python/project_presets_demo/cli.py) → [変更計画](python/project_presets_demo/plan.py) → [適用・検証](python/project_presets_demo/project.py) |
| 配布側の公開・利用側の更新選択 | [公開処理](scripts/release_presets.py)、[更新処理](scripts/update-consumer.py)、[共有 manifest](scripts/release_manifest.py) |
| AWS インフラ | [共通 module と初回 recipe](infra/README.md)。[CLI](infra/python/project_presets_infra/cli.py) は初回生成だけを担当 |

[構成と保守方法](docs/architecture.md) に、処理の流れと変更時の検証をまとめています。

## 最初の導入

空のディレクトリから、`npx` / `uvx` の CLI 一回で manifest・設定・必要な依存・lockfile・更新 PR 用 workflow が揃います。`package.json` / `pyproject.toml` がなければ自動作成します。配布パッケージの事前インストールも、Linter やフレームワークの個別インストールも不要です。

```sh
# TypeScript: node / hono / next のいずれかを選ぶ
npx --yes --allow-remote=root --ignore-scripts \
  https://github.com/omitsuhashi/project-presets-demo/releases/download/v2.1.0/project-presets-demo-2.1.0.tgz \
  typescript-node --setup

# Python: scripts / django / fastapi のいずれかを選ぶ
uvx --python 3.12 \
  --from https://github.com/omitsuhashi/project-presets-demo/releases/download/v2.1.0/project_presets_demo-2.1.0-py3-none-any.whl \
  project-presets-python python-django --setup
```

既存の lint 設定がある場合は、[導入手順の既存案件](docs/install.md#既存案件) に従って参照を統合し `--adopt --setup` を使います。Node.js / npm・Python / uv の導入も導入手順に記載しています。オプションなしは書き込みなしの preview、`--check` は整合性の確認です。未作成のディレクトリも `PROFILE DIRECTORY --setup` で初期化できます。TypeScript 内部の依存導入・更新は配布パッケージに含む **pnpm 11.28.0** を使い、`packageManager` と `pnpm-lock.yaml` を保存します。pnpm の事前インストールは不要です。CLI が採用版の共通パッケージも開発用依存に登録するため、CI では pnpm / uv lock から同じ設定を再現できます。

1.x の TypeScript 案件は `--version 2.1.0` を明示して [pnpm へ移行](docs/update.md#npm-の-1x-から-pnpm-へ移行する) します。lockfile・CI コマンドが変わるため major を上げています。Python は uv を継続します。

## 使い方・更新手順

| 読み手と作業 | 手順書 | 完了時の状態 |
| --- | --- | --- |
| 利用側: 初めて導入する | [TypeScript / Python の導入](docs/install.md) | Profile・配布版・設定・lock を固定して commit |
| 配布側: 共通設定・依存を更新する | [配布物の更新・公開](docs/publish.md) | 検証済み commit にタグを付け、Release の配布物を公開 |
| 利用側: AWS インフラと配置を追加する | [インフラの導入・更新・デプロイ](docs/infrastructure.md) | 固定 Terraform module と案件所有の Dockerfile・設定・配置 workflow を追加 |
| 利用側: 新版を適用する | [更新 PR・適用・復旧](docs/update.md) | 更新をレビューしてマージし、lock から実行環境を再構築 |

配布側の更新 PR → 固定タグ / GitHub Release → 利用側の更新 PR → マージ / 依存の再導入、という流れです。`--setup` が `.github/workflows/update-presets.yml` を配置します。GitHub の既定 branch へ commit / push し、Settings → Actions → General の「Allow GitHub Actions to create and approve pull requests」を有効にすると、毎週月曜 11:15（日本時間）に同じ major の新しい配布版を検証し、差分があれば更新 PR を作ります。Release 公開後の適用は、この PR をレビューしてマージします。詳細は [更新手順](docs/update.md#3-更新-pr-を自動で受け取る) を参照してください。

## 選べる構成

| Profile | 用途 | 主な依存と設定 |
| --- | --- | --- |
| `typescript-node` | Node.js 24 | TypeScript 6.0.3、ESLint 9.39.5、NodeNext / strict |
| `typescript-hono` | Node.js 24 / HTTP API | Hono 4.13.12、Node adapter 2.1.3、Node 用 lint / TypeScript |
| `typescript-next` | Node.js 24 / Next.js App Router | Next.js 16.3.8、React 19.3.0、対応する lint / 型定義 / compiler 設定 |
| `python-scripts` | Python 3.12 / スクリプト | Ruff 0.16.10、correctness / import / bugbear 設定、print を許可 |
| `python-django` | Python 3.12 / Django | Django 6.1.1、Ruff の `DJ` ルール、service 用の print 検査 |
| `python-fastapi` | Python 3.12 / HTTP API | FastAPI 0.142.2、Uvicorn 0.54.0、Ruff の `FAST` ルール、`Annotated` を推奨 |

[TypeScript catalog](profiles.json) / [Python catalog](python/profiles.json) は [生成 script](scripts/catalog.py) で native manifest の固定版から作ります。CI は生成結果の一致を確認します。Next.js と `eslint-config-next` も同じ版に揃え、代表アプリで検証します。

ESLint 9 は [2026-08-06 に EOL](https://eslint.org/version-support/) です。Next.js の React plugin の peer 対応に合わせて、このデモでは 9 を固定しています。本運用に昇格する前に、保守中のツールを使える組み合わせへ移行してください。このデモの検証対象と、組織のサポート範囲は別に決めます。

## 配布するものと管理する範囲

[公開版 v2.1.0](https://github.com/omitsuhashi/project-presets-demo/releases/tag/v2.1.0) は npm tarball・Python wheel / sdist・`SHA256SUMS` を含みます。初回導入と明示した版の適用は、公開 URL から GitHub 認証なしで行えます。

- TypeScript: Profile の実行用 / 開発用依存と marker を管理。利用側は共通 package の設定を import / extends し、案件固有の上書きを保守。
- Python: framework は実行用依存、preset / Ruff は開発用依存。コピーした共通設定と marker を管理し、案件固有の上書きは `pyproject.toml` で保守。
- 両言語: アプリのコード・追加テスト・フレームワーク移行・DB migration は利用側の責任。Hono / FastAPI の AWS 配置は、共通 Terraform module と初回 recipe を追加できる。生成後の資材は案件側で保守する。管理依存・Python の配布設定の手動変更 / 削除、TypeScript の設定ファイルの削除、Profile 切替は CLI が検出して停止。

[配布側の Dependabot](.github/dependabot.yml) は更新候補を作ります。採用版と共通設定を揃え、[release workflow](.github/workflows/release.yml) で検証・公開します。公開済みタグ・配布物は差し替えません。更新用 script は [scripts/update-consumer.py](scripts/update-consumer.py) です。

## AWS インフラを追加する

[共通 Terraform module と初回 recipe](docs/infrastructure.md) をアプリと独立して配布します。
開発中の **インフラ 2.0.0** は、`init` が固定 module 参照・Dockerfile・案件内 scripts・検証/配置 workflow を一度コピーする構成です。
**生成後の root・Dockerfile・scripts・workflow は利用側が保守します。** 配布元の可変 tools branch を通常配置で実行せず、生成ファイルを継続同期しません。

初期対象は `typescript-hono` / `python-fastapi` です。アプリ preset の依存更新は継続し、module の採用版は root の ref を変える PR と plan でレビューします。
Dockerfile・workflow 等の共通修正は各案件で取り込みます。AWS の bootstrap と復旧手順は生成先の `infra/README.md` に含まれます。

2.0.0 は未公開なので、[開発版を試す手順](docs/infrastructure.md#初回にコピーする) では公開済み 1.0.0 module を明示して使います。
公開済み 1.x のタグ・wheel・`infra-tools/v1` は保持し、[所有を移す手順](docs/infrastructure.md#1x-から所有を移す) で既存 state・設定・Dockerfile を保ったまま移行できます。
認証なしの検証と実 AWS の配置確認は別です。

## 検証

```sh
# pnpm 未導入でも、このターミナル内で固定版を一時実行できる。
pnpm() { npx --yes --ignore-scripts --package=pnpm@11.28.0 -- pnpm "$@"; }
pnpm install --frozen-lockfile --ignore-scripts
uv lock --check
pnpm run lint
pnpm run demo:ts
pnpm run demo:py
pnpm test
```

CI では manifest / catalog の整合性、Hono の応答、Next.js の build、Django / FastAPI のアプリを検証します。実際の tarball / wheel の導入・依存更新、ネイティブの lock、設定保持、手動変更の拒否、開発依存なしの Python 実行、revert を確認します。導入・更新テストは一時 fixture を使い、公開済み 1.5.0 の npm lock からの移行と revert も検証します。

旧 Python submodule の設定パスは互換用に残しています。新規導入は wheel を使い、移行方法は [導入手順](docs/install.md#既存案件) を参照してください。

MIT License.
