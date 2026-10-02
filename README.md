# project-presets-demo

言語・フレームワーク・依存パッケージの版と、それに合う lint / TypeScript 設定を配布するデモです。**GitHub Release に npm tarball と Python wheel を公開します。npm・PyPI のアカウントや、利用側の GitHub 認証は不要です。**

利用側は配布版を固定し、更新時にパッケージ・管理対象の設定・依存・lockfile を同じ PR で変更します。アプリのコードと案件固有の設定は利用側が保守します。

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

## TypeScript の導入

Node.js 24 と npm を使います。空の npm プロジェクトで次を実行します。

```sh
npm init -y
npm pkg set type=module
npm pkg delete scripts.test
npm install --package-lock-only --allow-remote=root --ignore-scripts --save-dev --save-exact \
  https://github.com/omitsuhashi/project-presets-demo/releases/download/v1.2.0/project-presets-demo-1.2.0.tgz \
  eslint@9.39.5 typescript@6.0.3
npm ci --allow-remote=root --ignore-scripts

# Profile を選んで差分を見る。書き込みは --write の時だけ。
npm exec -- project-presets typescript-hono
npm exec -- project-presets typescript-hono --write --sync
npm exec -- project-presets typescript-hono --check
```

`typescript-next`、`typescript-node` も同じ方法です。`--sync` は npm lock を生成して `npm ci` します。依存の install script は実行しません。必要な script は案件側で明示して実行してください。

CLI は Profile の依存と `.project-preset.json` を管理します。`eslint.config.mjs` と `tsconfig.json` は初回だけ作り、以後は共通設定の import / extends を残して案件側で上書きできます。

```js
import preset from 'project-presets-demo/hono';
export default [...preset, { rules: { '@typescript-eslint/no-unused-vars': 'warn' } }];
```

既存案件では import / extends と依存をレビューして統合した後、`--adopt --write --sync` で登録します。管理対象の依存の手動変更・削除や Profile 切替は検出して停止します。[Hono](examples/hono)、[Next.js](examples/next)、[Node.js](examples/typescript) の最小アプリも参照できます。

## Python の導入

Python 3.12 と uv を使います。Node.js と Git submodule は不要です。

```sh
uv init --bare --python 3.12
uv python pin 3.12
uv add --dev 'project-presets-demo @ https://github.com/omitsuhashi/project-presets-demo/releases/download/v1.2.0/project_presets_demo-1.2.0-py3-none-any.whl'
uv run --locked project-presets-python python-scripts
uv run --locked project-presets-python python-scripts --write --sync
uv run --locked project-presets-python python-scripts --check
uv run --locked ruff check .
```

wheel が Ruff の exact version を依存として持つので、preset の更新と Ruff の更新が同じ uv lock に入ります。CLI は配布された設定を `.project-presets/ruff/` に配置し、`pyproject.toml` に薄い参照を追加します。設定ファイルと `.project-preset.json` は commit してください。

フレームワークを使う案件では、初回から `python-django` または `python-fastapi` を選びます。上記の wheel を導入した後、例えば Django は次のように始められます。

```sh
uv run --locked project-presets-python python-django
uv run --locked project-presets-python python-django --write --sync
uv run --locked project-presets-python python-django --check
uv run --locked django-admin startproject demo .
uv run --locked python manage.py check
uv run --locked python manage.py test
```

FastAPI は `python-fastapi --write --sync` を適用し、[main.py と HTTP テスト](examples/fastapi) を配置して `uv run --locked uvicorn main:app` で起動します。テストは `uv run --locked python -m unittest discover` です。[Django の最小アプリ](examples/django) も `/health` の応答をテストします。

フレームワークの固定版は wheel の optional dependency metadata から取得し、CLI が **利用側の `[project].dependencies` に登録**します。Ruff と preset は開発用なので、`uv sync --locked --no-dev` でもアプリに必要な Django / FastAPI / Uvicorn は残ります。DB driver、認証、業務アプリの依存は案件側で追加します。

Django は `DJ`、FastAPI は `FAST` を共通 correctness / import / bugbear ルールに加えます。両方で print を検査し、FastAPI の引数には `Annotated` を使います。Django 用は `django.toml`、FastAPI 用は `fastapi.toml` を `extend` します。既存依存は exact pin に合わせて統合してください。管理する依存の手動変更・削除、Profile の切替は停止します。例は開発用の最小アプリです。Django の本番設定・migration、FastAPI の業務テストは利用側で検証します。

```toml
[tool.ruff]
extend = ".project-presets/ruff/scripts.toml"
target-version = "py312"
line-length = 100

[tool.ruff.lint]
ignore = ["F401"]
```

既存の Ruff 設定がある時は `extend` を統合してから `--adopt --write --sync` します。`pyproject.toml` の案件固有の設定とコードを保持します。配布側が管理する `.project-presets/ruff/` のファイルを手で変更・削除した場合は停止します。上書きは `pyproject.toml` に記載してください。

旧 submodule 配布から移行する時は、submodule を取り外す変更と wheel の導入をレビューしてください。CLI は submodule の中に設定を書き込みません。旧 Git 配布の設定パスは互換用に残しています。

## 両言語の更新と復旧

[更新 script](scripts/update-consumer.py) は、選択済みの Profile に応じて新しい配布物を導入し、その版の設定・依存・lock を更新して検証します。script は利用側のディレクトリの外に置きます。

```sh
# 利用側のルートで実行。
uv run --no-project --python 3.12 python /path/to/preset-provider/scripts/update-consumer.py --version 1.2.0
```

版を省略すると `gh` で公開済みの Release を調べ、現在と同じ major の最新版を選びます。prerelease・draft・未公開版は自動採用しません。major 更新やロールバックは `--version` で明示します。アプリのフレームワーク切替や業務コード移行は自動変換しません。

- TypeScript: パッケージ、管理依存、npm lock の整合性、lint、型チェックと、設定済みの `build` / `test` scripts を検証します。
- Python: パッケージ、同梱設定、Ruff、実行用のフレームワーク依存、uv lock の整合性と lint を検証します。Django は標準の `manage.py check` / `test` も実行します。FastAPI などの案件のテストは `test-command` に追加してください。

更新の途中で install・検証が失敗したら、PR をマージせず残った差分を確認します。ファイル置換とパッケージ管理をまたぐ処理はトランザクションではありません。元の manifest・lock・marker・管理設定を戻し、TypeScript は `npm ci --allow-remote=root --ignore-scripts`、Python は `uv sync --locked` で復旧します。マージ後は更新 PR を revert して同じ操作をします。

## 更新 PR を自動で受け取る

[workflow サンプル](examples/update-presets.yml) を利用側の `.github/workflows/update-presets.yml` に置きます。実装はこの repository の固定タグを参照する reusable workflow です。

毎週、現在の major の公開済み版を選び、パッケージ・依存・設定・lock の差分を PR にします。手動実行では版を指定できます。同じ版の更新 branch が既にある場合は、その branch を上書きしません。マージは利用側が判断します。

GitHub Actions の設定で「Allow GitHub Actions to create and approve pull requests」を有効にしてください。専用 PAT は不要です。ただし `GITHUB_TOKEN` で作る PR の workflow は承認待ちになるため、**必要なアプリテストを `test-command` に指定し、PR 作成前に実行してください。** Python では、例えば `uv run --locked python -m unittest discover` を指定します。自動更新は新方式を導入済みの案件が対象です。

monorepo では `directory` を指定できます。同じ Profile が複数ディレクトリにある場合の更新は、まず手動 script で各ディレクトリに適用してください。サンプルの PR branch 名は一つの Profile あたり一つです。

## 配布側の保守

配布元の Dependabot は npm・uv・GitHub Actions の更新候補を毎週作ります。候補の版を採用する時は catalog と manifest を揃えて検証します。依存だけを更新した PR は整合性の CI で停止し、自動マージしません。Python の検査は `uv.lock` に固定した実際の Ruff を使います。

1. Profile、パッケージ manifest、対応設定を変更し、代表アプリと更新・復旧のテストを通す。
2. npm と Python の配布版を揃え、`npm install --package-lock-only` と `uv lock` で配布元の lock も更新し、changelog に変更・互換性・移行方法を記載する。
3. 検証済み commit に `vX.Y.Z` を付けて push する。
4. [release workflow](.github/workflows/release.yml) が再検証し、tarball・wheel・sdist・SHA256SUMS を含む Release を公開する。

公開済みタグと配布物は差し替えません。既存 CI を新たに失敗させる lint ルール、非互換な runtime / framework、管理対象の削除は major または明示した移行として配布します。依存の更新は利用者への影響を基準に判断します。npm・PyPI への登録は、この GitHub 配布には必要ありません。

## この repository の検証

```sh
npm ci --allow-remote=root --ignore-scripts
npm run lint
npm run demo:ts
npm run demo:py
npm test
```

CI では Git 配布の互換性、Hono の応答、Next.js の build に加え、実際に build した npm tarball / Python wheel を導入・更新します。ネイティブの lock、設定の更新、案件固有の上書き、手動変更の拒否、commit の revert と復旧を確認します。テストの `v2.0.0` は一時 fixture です。

Python 3.12 上で Django の system check / HTTP テストと FastAPI / Uvicorn の実 HTTP 応答を確認します。開発依存を除いた実行、フレームワークの旧版から新版への更新、lint ルール、設定保持、依存の手動変更・削除と Profile 切替の拒否、revert 後の再実行を検証します。

参照: [npm tarball install](https://docs.npmjs.com/cli/v11/commands/npm-install/)、[uv package distribution](https://docs.astral.sh/uv/guides/package/)、[Ruff configuration](https://docs.astral.sh/ruff/configuration/)、[GitHub workflow trigger rules](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow)。

Framework の参照: [Django 6.1 / Python 互換性](https://docs.djangoproject.com/en/6.1/faq/install/)、[FastAPI のサーバー起動](https://fastapi.tiangolo.com/deployment/manually/)、[Ruff の Django / FastAPI ルール](https://docs.astral.sh/ruff/rules/)。

MIT License.
