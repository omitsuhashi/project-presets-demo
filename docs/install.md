# 利用側への導入

利用側の担当者が、Profile を一つ選び、固定した配布版と設定・lockfile を Git に保存するための手順です。初回導入後の更新は [利用側の更新・復旧](update.md) を使います。

この手順は公開済みの `v1.2.0` を使います。TypeScript は Node.js 24 / npm 12、Python は Python 3.12 / uv 0.11.7 で検証しています。npm・PyPI のアカウント、GitHub 認証、Git submodule は初回導入には不要です。ツールの導入は [Node.js](https://nodejs.org/en/download) / [uv](https://docs.astral.sh/uv/getting-started/installation/) を参照してください。

## TypeScript

新規プロジェクト専用の例です。既存案件は後述の「既存案件」の手順で配布物の導入と設定統合を行います。

```sh
mkdir typescript-demo
cd typescript-demo
npm init -y
npm pkg set type=module
npm pkg delete scripts.test

PRESET_VERSION=1.2.0
npm install --package-lock-only --allow-remote=root --ignore-scripts --save-dev --save-exact \
  "https://github.com/omitsuhashi/project-presets-demo/releases/download/v${PRESET_VERSION}/project-presets-demo-${PRESET_VERSION}.tgz" \
  eslint@9.39.5 typescript@6.0.3
npm ci --allow-remote=root --ignore-scripts

# 初回に一つ選ぶ。node / hono / next はそれぞれ別の構成。
PRESET_PROFILE=typescript-node
npm exec -- project-presets "$PRESET_PROFILE"         # 書き込みなしの確認
npm exec -- project-presets "$PRESET_PROFILE" --write --sync
npm exec -- project-presets "$PRESET_PROFILE" --check
```

`PRESET_PROFILE` は `typescript-node`、`typescript-hono`、`typescript-next` から選びます。初回の `--write` が `eslint.config.mjs` / `tsconfig.json` / `.project-preset.json` を作り、必要な依存を `package.json` に追加します。`--sync` が npm lock を生成して再導入します。Hono・Next.js・React は実行用依存、preset・lint・型定義は開発用依存です。

アプリのコード・起動 scripts は案件側で用意します。Node.js の最小確認は次のとおりです。

```sh
printf 'const greeting: string = "Hello";\nconsole.log(greeting);\n' > main.ts
npm exec -- eslint .
npm exec -- tsc --noEmit
node main.ts
```

Hono は [app.ts / server.ts](../examples/hono) を配置し、`node server.ts` で起動できます。Next.js は [app/](../examples/next/app) を配置し、`npm exec -- next dev` で起動します。更新時に build / test を実行するため、Next.js の例では次も設定します。

```sh
npm pkg set 'scripts.dev=next dev' 'scripts.build=next build --webpack'
```

初回に作った共通設定の参照は残し、案件固有のルールを追加できます。

```js
import preset from 'project-presets-demo/node'; // Hono は /hono、Next.js は /next
export default [...preset, { rules: { '@typescript-eslint/no-unused-vars': 'warn' } }];
```

`tsconfig.json` は共通設定の `extends` を残して `include` や `compilerOptions` を追加します。CLI は登録後の二つの設定ファイルを上書きしません。管理対象の依存の手動変更・削除と Profile 切替は停止します。

検証後、既存 Git repository または `git init` した repository に次を commit します。

```sh
git add package.json package-lock.json eslint.config.mjs tsconfig.json .project-preset.json
# 作成したアプリのコードと .gitignore も別途追加する。
git commit -m "Adopt TypeScript project preset"
```

`node_modules/`、`.next/`、`*.tsbuildinfo` は `.gitignore` に入れます。install script は実行していません。アプリの依存で必要な script は案件側で判断して実行します。

## Python

新規プロジェクト専用の例です。既存案件は後述の「既存案件」の手順で配布物の導入と設定統合を行います。

```sh
mkdir python-demo
cd python-demo
uv init --bare --name python-demo --python 3.12
uv python pin 3.12

PRESET_VERSION=1.2.0
uv add --dev "project-presets-demo @ https://github.com/omitsuhashi/project-presets-demo/releases/download/v${PRESET_VERSION}/project_presets_demo-${PRESET_VERSION}-py3-none-any.whl"

# 初回に一つ選ぶ。scripts / django / fastapi はそれぞれ別の構成。
PRESET_PROFILE=python-scripts
uv run --locked project-presets-python "$PRESET_PROFILE"   # 書き込みなしの確認
uv run --locked project-presets-python "$PRESET_PROFILE" --write --sync
uv run --locked project-presets-python "$PRESET_PROFILE" --check
```

`PRESET_PROFILE` は `python-scripts`、`python-django`、`python-fastapi` から選びます。wheel が Ruff の版と設定を同梱し、CLI が設定を `.project-presets/ruff/` にコピーして `[tool.ruff].extend` を追加します。

| Profile | 実行用依存 | Ruff 設定 |
| --- | --- | --- |
| `python-scripts` | なし | correctness / import / bugbear、print を許可 |
| `python-django` | Django 6.1.1 | 共通設定 + `DJ` / `T20` |
| `python-fastapi` | FastAPI 0.142.2 / Uvicorn 0.54.0 | 共通設定 + `FAST` / `T20`、`Annotated` を使用 |

フレームワークは利用側の `[project].dependencies` に登録されます。preset / Ruff は開発用依存です。`uv sync --locked --no-dev` でもアプリの実行用依存は残ります。DB driver や認証の追加パッケージは案件側で導入します。

選んだ Profile に応じてアプリを作り、検証します。

**スクリプト**

```sh
printf 'print("Hello")\n' > main.py
uv run --locked ruff check .
uv run --locked python main.py
```

**Django** — 初回から `PRESET_PROFILE=python-django` として上記を適用した後に実行します。

```sh
uv run --locked django-admin startproject demo .
uv run --locked ruff check .
uv run --locked python manage.py check
uv run --locked python manage.py test
uv run --locked python manage.py runserver
```

[最小 HTTP アプリ](../examples/django) も参照できます。Django の DB migration・本番用の secret / host / server 設定は案件側の作業です。

**FastAPI** — 初回から `PRESET_PROFILE=python-fastapi` として上記を適用した後、[main.py / test_main.py](../examples/fastapi) を配置します。

```sh
uv run --locked ruff check .
uv run --locked python -m unittest discover
uv run --locked uvicorn main:app
# 別のターミナル: curl http://127.0.0.1:8000/health
```

案件固有の Ruff 設定は `pyproject.toml` に記載します。例えば Django は次の参照を残します。

```toml
[tool.ruff]
extend = ".project-presets/ruff/django.toml"
target-version = "py312"
line-length = 100
```

scripts は `scripts.toml`、FastAPI は `fastapi.toml` を使います。コピーした `.project-presets/ruff/` を手で変更・削除すると更新を停止するため、上書きは `[tool.ruff]` / `[tool.ruff.lint]` に追加します。

検証後、次を commit します。

```sh
git add pyproject.toml uv.lock .python-version .project-preset.json .project-presets/ruff
# アプリのコードと .gitignore も別途追加する。
git commit -m "Adopt Python project preset"
```

`.venv/`、`.ruff_cache/`、`__pycache__/`、開発用の `db.sqlite3` は `.gitignore` に入れます。

## 既存案件

導入用 branch で、既存の manifest とアプリテストを使います。上記の配布物の install コマンドだけを実行し、既存設定の参照を共通設定に統合します。新規用の `npm init` / `uv init` / `scripts.test` の削除は行いません。管理対象の依存は [profiles.json](../profiles.json) の exact pin に合わせます。Python の既存依存を揃える時も `uv add` で manifest / lock を更新します。

既存設定を保持したまま登録するには、選んだ Profile で `--adopt --write --sync` を使います。その後に `--check`、lint、型チェック、アプリのテストを実行して導入 PR をレビューします。`--adopt` は依存の競合や Profile 切替を強制するオプションではありません。

```sh
# TypeScript / Hono の既存案件の例
npm exec -- project-presets typescript-hono --adopt --write --sync
npm exec -- project-presets typescript-hono --check
# Python / Django の既存案件の例
uv run --locked project-presets-python python-django --adopt --write --sync
uv run --locked project-presets-python python-django --check
```

旧 Python submodule 配布は、Git の通常の手順で submodule を取り外し、設定参照を wheel 方式へ変更する移行 PR を作ります。既存の Profile を別のフレームワークへ切り替える場合も、アプリの移行を含めて別途レビューします。

参照: [npm install](https://docs.npmjs.com/cli/v12/commands/npm-install/)、[uv の依存管理](https://docs.astral.sh/uv/concepts/projects/dependencies/)、[Ruff の継承と上書き](https://docs.astral.sh/ruff/configuration/)。
