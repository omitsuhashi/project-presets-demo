# 利用側への導入

利用側の担当者が、Profile を一つ選び、固定した配布版と設定・lockfile を Git に保存するための手順です。初回導入後の更新は [利用側の更新・復旧](update.md) を使います。

この手順は公開済みの `v2.1.0` を使います。TypeScript の CLI は Node.js 22.13 以上（22 系または 24 以降）/ npm を前提とし、Node.js 24 / npm 12 と Node.js 22.22.2 で検証しています。Python は Python 3.12 / uv 0.11.7 で検証しています。npm・PyPI のアカウント、GitHub 認証、Git submodule は初回導入には不要です。ツールの導入は [Node.js](https://nodejs.org/en/download) / [uv](https://docs.astral.sh/uv/getting-started/installation/) を参照してください。

**事前の `npm init` / `uv init` / `npm install` / `uv add` は不要です。** `npx` / `uvx` が固定版の CLI を一時取得し、`--setup` が manifest・設定・依存・lockfile と `.github/workflows/update-presets.yml` を一括適用します。繰り返し実行でき、案件固有の設定を保持します。書き込み前に確認したい場合は `--setup` を外すと preview、適用後の確認は `--check` です。従来の `--write --sync` も同じ処理として利用できます。

Node.js / npm または Python / uv が前提です。初回の `package.json` / `pyproject.toml` は自動作成します。アプリのコード、DB、secret、本番環境は案件側で用意します。

初期化時の project 名はディレクトリ名から作り、空白・日本語などを除いたパッケージ名に正規化します。有効な文字が残らない場合は `project` を使います。TypeScript は `version: 0.0.0` / `private: true` / `type: module`、Python は `version = "0.0.0"` / `requires-python = ">=3.12,<3.13"` を初期値にします。既存 manifest の名前・版・追加依存・設定を保持します。

ディレクトリ引数は両 CLI で `PROFILE DIRECTORY --setup` の順です。未作成のディレクトリと親ディレクトリも自動で作ります。preview と `--check` は初期化しません。導入済み marker がある状態で manifest が削除されていたら、Git からの復旧を案内して停止します。既存ファイルの構文エラーや設定・依存の競合も保持したまま停止するので、原因を解消して再実行します。一つのディレクトリには一つの Profile を適用し、TypeScript と Python は別ディレクトリを使います。

## TypeScript

新規プロジェクト専用の例です。既存案件は後述の「既存案件」の手順で配布物の導入と設定統合を行います。

```sh
mkdir typescript-demo
cd typescript-demo

# pnpm 未導入でも、このターミナル内で固定版を一時実行できる。
pnpm() { npx --yes --ignore-scripts --package=pnpm@11.28.0 -- pnpm "$@"; }

PRESET_VERSION=2.1.0
# 初回に一つ選ぶ。node / hono / next はそれぞれ別の構成。
PRESET_PROFILE=typescript-node
npx --yes --allow-remote=root --ignore-scripts \
  "https://github.com/omitsuhashi/project-presets-demo/releases/download/v${PRESET_VERSION}/project-presets-demo-${PRESET_VERSION}.tgz" \
  "$PRESET_PROFILE" --setup
pnpm exec project-presets "$PRESET_PROFILE" --check
```

`PRESET_PROFILE` は `typescript-node`、`typescript-hono`、`typescript-next` から選びます。`--setup` が `eslint.config.mjs` / `tsconfig.json` / `.project-preset.json` を作り、Profile の exact version と `packageManager: pnpm@11.28.0` を `package.json` に登録し、配布パッケージの pnpm で `pnpm-lock.yaml` とインストール済み依存を揃えます。pnpm の事前導入は不要です。上記のシェル関数は、導入後のアプリ操作を同じ固定版で行うための補助です。**ESLint・TypeScript・型定義やフレームワークを個別にインストールする必要はありません。** CLI が実行版と同じ公開 tarball を開発用依存に登録します。共通設定の import / extends が使うパッケージと、ESLint・TypeScript も自動で導入されます。Hono・Next.js・React は実行用依存、preset・lint・型定義は開発用依存です。

アプリのコード・起動 scripts は案件側で用意します。Node.js の最小確認は次のとおりです。

```sh
printf 'const greeting: string = "Hello";\nconsole.log(greeting);\n' > main.ts
pnpm exec eslint .
pnpm exec tsc --noEmit
node main.ts
```

Hono は [app.ts / server.ts](../examples/hono) を配置し、`node server.ts` で起動できます。Next.js は [app/](../examples/next/app) を配置し、`pnpm exec next dev` で起動します。更新時に build / test を実行するため、Next.js の例では次も設定します。

```sh
node --input-type=module -e 'import fs from "node:fs"; const p=JSON.parse(fs.readFileSync("package.json")); p.scripts={...p.scripts,dev:"next dev",build:"next build --webpack"}; fs.writeFileSync("package.json",JSON.stringify(p,null,2)+"\n");'
```

初回に作った共通設定の参照は残し、案件固有のルールを追加できます。

```js
import preset from 'project-presets-demo/node'; // Hono は /hono、Next.js は /next
export default [...preset, { rules: { '@typescript-eslint/no-unused-vars': 'warn' } }];
```

`tsconfig.json` は共通設定の `extends` を残して `include` や `compilerOptions` を追加します。CLI は登録後の二つの設定ファイルを上書きしません。管理対象の依存の手動変更・削除と Profile 切替は停止します。

検証後、既存 Git repository または `git init` した repository に次を commit します。

```sh
git add package.json pnpm-lock.yaml eslint.config.mjs tsconfig.json .project-preset.json .github/workflows/update-presets.yml
# 作成したアプリのコードと .gitignore も別途追加する。
git commit -m "Adopt TypeScript project preset"
```

`node_modules/`、`.next/`、`*.tsbuildinfo` は `.gitignore` に入れます。install script は実行していません。アプリの依存で必要な script は案件側で判断して実行します。

npm の既存 lock は pnpm 自身の `import` で移行し、依存導入と配布版確認が成功した後に削除します。pnpm の依存解決・配置に変わるため、[CI・復旧を含む移行手順](update.md#npm-の-1x-から-pnpm-へ移行する) に従ってアプリを検証します。

## Python

新規プロジェクト専用の例です。既存案件は後述の「既存案件」の手順で配布物の導入と設定統合を行います。

```sh
mkdir python-demo
cd python-demo

PRESET_VERSION=2.1.0
# 初回に一つ選ぶ。scripts / django / fastapi はそれぞれ別の構成。
PRESET_PROFILE=python-scripts
uvx --python 3.12 \
  --from "https://github.com/omitsuhashi/project-presets-demo/releases/download/v${PRESET_VERSION}/project_presets_demo-${PRESET_VERSION}-py3-none-any.whl" \
  project-presets-python "$PRESET_PROFILE" --setup
uv run --locked project-presets-python "$PRESET_PROFILE" --check
```

`PRESET_PROFILE` は `python-scripts`、`python-django`、`python-fastapi` から選びます。**Ruff・Django・FastAPI・Uvicorn の個別インストールは不要です。** CLI が実行版と同じ公開 wheel を開発用依存に登録し、その依存である Ruff と、選んだフレームワークを導入して uv lock と利用側の実行環境を揃えます。設定を `.project-presets/ruff/` にコピーし、`[tool.ruff].extend` も追加します。

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
git add pyproject.toml uv.lock .project-preset.json .project-presets/ruff .github/workflows/update-presets.yml
# アプリのコードと .gitignore も別途追加する。
git commit -m "Adopt Python project preset"
```

`.venv/`、`.ruff_cache/`、`__pycache__/`、開発用の `db.sqlite3` は `.gitignore` に入れます。

## 自動更新 PR を有効にする

TypeScript・Python とも、`--setup` は案件の `.github/workflows/update-presets.yml` を自動作成します。配布パッケージの中に workflow を含めているので、利用側でサンプルを探してコピーする操作は不要です。既存の同名ファイルは、schedule・追加テスト・参照タグを含めてそのまま保持します。preview の `create` に作成予定を表示し、`--check` は workflow があることも確認します。削除して再配置したい場合は `--setup` を再実行します。

上記の導入 commit に workflow も含め、利用側 GitHub repository の既定 branch へ push / マージします。Settings → Actions → General の「Allow GitHub Actions to create and approve pull requests」を有効にすると、毎週月曜 11:15（日本時間）に同じ major の新しい配布版を検証し、差分があれば PR を作ります。専用 PAT の登録は不要です。この GitHub 側の設定や repository の公開・push は CLI から行いません。Actions の手動実行でも確認できます。

PR を作る前に lint / 型チェック / `package.json` の build / test、Django の check / test を実行します。Python スクリプト・FastAPI のアプリテストや追加検証は、生成した workflow の `test-command` に案件のコマンドを設定してください。詳細と GitHub の実行承認については [更新手順](update.md#3-更新-pr-を自動で受け取る) を参照してください。

生成先は指定した project ディレクトリです。GitHub は repository ルートの `.github/workflows/` を実行するので、その project を一つの repository として commit します。既存 monorepo の子 project で使う場合は、生成ファイルを repository ルートに移し、workflow の `directory: apps/api` などを設定します。同じ repository の複数 project は一つの workflow でまとめるなど、案件の構成に合わせます。

## 既存案件

導入用 branch で、既存の manifest とアプリテストを使います。既存設定の参照を共通設定に統合してから、上記の一時実行コマンドに `--adopt` を付けて実行します。管理対象の依存が未導入なら CLI が追加します。既存の版が競合する場合は、[TypeScript catalog](../profiles.json) / [Python catalog](../python/profiles.json) の exact pin に合わせてから登録します。Python の既存依存を揃える時も `uv add` で manifest / lock を更新します。

既存設定を保持したまま登録するには、選んだ Profile で `--adopt --setup` を使います。その後に `--check`、lint、型チェック、アプリのテストを実行して導入 PR をレビューします。`--adopt` は依存の競合や Profile 切替を強制するオプションではありません。

```sh
# pnpm 未導入でも、このターミナル内で固定版を一時実行できる。
pnpm() { npx --yes --ignore-scripts --package=pnpm@11.28.0 -- pnpm "$@"; }

PRESET_VERSION=2.1.0
# TypeScript / Hono の既存案件の例
npx --yes --allow-remote=root --ignore-scripts \
  "https://github.com/omitsuhashi/project-presets-demo/releases/download/v${PRESET_VERSION}/project-presets-demo-${PRESET_VERSION}.tgz" \
  typescript-hono --adopt --setup
pnpm exec project-presets typescript-hono --check
# Python / Django の既存案件の例
uvx --python 3.12 \
  --from "https://github.com/omitsuhashi/project-presets-demo/releases/download/v${PRESET_VERSION}/project_presets_demo-${PRESET_VERSION}-py3-none-any.whl" \
  project-presets-python python-django --adopt --setup
uv run --locked project-presets-python python-django --check
```

旧 Python submodule 配布は、Git の通常の手順で submodule を取り外し、設定参照を wheel 方式へ変更する移行 PR を作ります。既存の Profile を別のフレームワークへ切り替える場合も、アプリの移行を含めて別途レビューします。

一時実行した CLI は npm / uv のキャッシュに置かれます。採用した配布パッケージと Linter は CLI が案件の開発用依存へ登録するため、CI と他の開発環境でも lock から同じ構成を再現できます。配布パッケージの事前導入も可能で、導入後は `pnpm exec` / `uv run` で実行できます。

通常は実行した CLI と同じ版の GitHub Release を登録します。別の配布先やローカル artifact を使う場合は `--source URL` を指定します。TypeScript は HTTP(S) / `file:` / Git、Python は HTTP(S) / `file://` の wheel URL を使えます。既存の公式以外の配布元は保持されるため、そこから別の版へ更新する場合は新しい配布元を明示してください。公開 URL は固定版を使い、実行 CLI と配布物の版を揃えます。

参照: [npm exec / npx](https://docs.npmjs.com/cli/v12/commands/npm-exec/)、[pnpm install](https://pnpm.io/cli/install)、[pnpm import](https://pnpm.io/cli/import)、[uvx](https://docs.astral.sh/uv/guides/tools/)、[uv の依存管理](https://docs.astral.sh/uv/concepts/projects/dependencies/)、[Ruff の継承と上書き](https://docs.astral.sh/ruff/configuration/)。

## 言語別の配布 URL

上記の 2.1.0 は公開済みの統合配布です。2.2.0 以降の公開後は、TypeScript の URL を `releases/download/typescript-vX.Y.Z/project-presets-demo-X.Y.Z.tgz`、Python の URL を `releases/download/python-vX.Y.Z/project_presets_demo-X.Y.Z-py3-none-any.whl` にします。各言語で実際に公開されている版を選び、版番号を揃える必要はありません。2.2.0 はこの変更で準備する版であり、PR のマージだけでは公開されません。
