# 利用側の更新・適用・復旧

導入済みの利用側担当者が、新しい配布版を一つの更新 PR にまとめ、検証・レビュー後に適用する手順です。初回は [導入手順](install.md) の「`npx` / `uvx` から CLI の `--setup`」、公開作業は [配布側の更新](publish.md) を使います。

**配布側が Release を公開しても、利用側のファイルや実行環境は自動では変わりません。** 手動または workflow が更新 PR を作り、利用側がマージした後、各環境で lock に沿って依存を再導入します。自動更新の対象は `.project-preset.json` がある案件です。

## 1. 対象版と変更内容を確認する

利用側の repository で作業します。

```sh
cat .project-preset.json
git status --short
```

marker に現在の Profile / 配布版が記録されています。未 commit の作業は先に保存し、[Release notes](https://github.com/omitsuhashi/project-presets-demo/releases) から適用する版・移行作業を確認します。TypeScript の共通設定はパッケージ内なので、利用側の diff と併せて配布元のタグ間の差分も確認します。

下表は更新 script / workflow の版指定です。一時実行 CLI は取得 URL に含めた固定版を使います。

| 選び方 | 動作 |
| --- | --- |
| `--version 1.4.0` など明示 | 指定した公開版を選ぶ。major 更新・ダウングレードも明示指定 |
| `--version` を省略 | 現在と同じ major で、現在以上の最新 stable Release を選ぶ |
| Profile の変更 | アプリの移行が必要。通常の更新 CLI は停止する |

自動選択は draft / prerelease を採用しません。現在と最新版が同じでも再導入・再検証し、ファイル差分がなければ自動 PR は作られません。

## 2. 手動で更新 PR を作る

### 一時取得した CLI で更新する

初回と同じ `npx` / `uvx` の入口を使えます。未 commit の作業を保存し、更新用 branch で、現在の Profile を変えずに新版を適用します。以下は Node.js / Python スクリプトの例です。Hono・Next.js・Django・FastAPI は marker の現在の Profile に置き換えます。

```sh
git switch -c codex/update-project-preset
PRESET_VERSION=1.4.0
# TypeScript の案件で実行
npx --yes --allow-remote=root --ignore-scripts \
  "https://github.com/omitsuhashi/project-presets-demo/releases/download/v${PRESET_VERSION}/project-presets-demo-${PRESET_VERSION}.tgz" \
  typescript-node --setup
npm exec -- project-presets typescript-node --check
npm exec -- eslint .
npm exec -- tsc --noEmit
npm run build --if-present
npm run test --if-present

# Python の案件で実行
uvx --python 3.12 \
  --from "https://github.com/omitsuhashi/project-presets-demo/releases/download/v${PRESET_VERSION}/project_presets_demo-${PRESET_VERSION}-py3-none-any.whl" \
  project-presets-python python-scripts --setup
uv run --locked project-presets-python python-scripts --check
uv run --locked ruff check .
# この後に案件のアプリテストを実行する。
```

公式 Release の配布 URL は実行した CLI の版に更新されます。CLI の一時実行環境と利用側の環境は分かれます。Python の `--check` は利用側の依存・lock・インストール済み版を検査するため、`uvx` からも確認できます。

`--setup` は設定・依存の適用と配布版の整合性までを扱います。上記の lint / 型チェック / build / test と、Django の `manage.py check` / `test` などは別途実行します。以下の更新 script を使うと、対応する検証まで自動実行します。検証後は本章の diff 確認・commit・レビュー・環境反映・復旧に従います。

### 更新 script で適用と検証を実行する

共通の [更新 script](../scripts/update-consumer.py) が TypeScript / Python を判別します。両言語で uv / Python 3.12 と Git を使い、TypeScript では Node.js 24 / npm も使います。明示した版の公開配布物の取得には GitHub 認証は不要です。最新版の自動検索は GitHub CLI (`gh`) の認証も必要です。

script を利用側の外に用意します。以下は利用側のルートで実行する例です。`../preset-provider` が未使用のディレクトリであることを確認してください。

```sh
git clone --depth 1 --branch v1.4.0 \
  https://github.com/omitsuhashi/project-presets-demo.git ../preset-provider

git switch -c codex/update-project-preset
# 1.4.0 は公開済み版での例。採用する新版に置き換える。
uv run --no-project --python 3.12 python ../preset-provider/scripts/update-consumer.py \
  --directory . --version 1.4.0
```

script は版を導入してからその版の CLI で管理対象を更新するため、**更新 script に全体の preview モードはありません**。最初の導入 CLI の書き込みなし表示は、インストール済み版についての確認です。更新は branch 上で行い、diff とテストを確認します。

最新版を自動で選ぶ場合は `gh auth login` を済ませてから `--version` を省略します。自動選択でも major は上がりません。

```sh
uv run --no-project --python 3.12 python ../preset-provider/scripts/update-consumer.py --directory .
```

配布側が更新 script / 新しい Profile への対応をリリースした時は、配布元 checkout のタグもその公開済み版に更新します。package の版を変えるだけで更新用の script のコードは変わりません。

```sh
# PRESET_TOOL_VERSION を採用する公開済みのツール版に置き換える。
PRESET_TOOL_VERSION=1.4.0
git -C ../preset-provider fetch --depth 1 origin tag "v${PRESET_TOOL_VERSION}"
git -C ../preset-provider switch --detach "v${PRESET_TOOL_VERSION}"
```

### 自動で行う処理

| 言語 | 更新するもの | 実行する検証 |
| --- | --- | --- |
| TypeScript | 配布 tarball、Profile の依存、npm lock、marker | preset / lock の整合性、ESLint、`tsc --noEmit`、設定済みの `build` / `test` scripts |
| Python | 配布 wheel、Ruff、framework の実行用依存、uv lock、コピーした設定、marker | preset / 依存 / lock の整合性、Ruff。Django は `manage.py check` / `test` も実行 |

案件のコードと設定の上書きは保持します。管理対象の依存・コピーした設定の手動変更 / 削除、Profile 切替は停止します。変更を無条件に上書きする操作は用意していません。

FastAPI や Python スクリプトのアプリテストも実行します。案件で pytest などを使っていれば、その案件のコマンドに置き換えます。

```sh
# 同梱の FastAPI サンプルの例
uv run --locked python -m unittest discover
```

### diff を確認して commit する

```sh
git diff --stat
git diff --check
git diff
```

配布版、framework / tool の版、lock、共通設定、テスト結果が揃っていることを確認します。Django の DB migration や業務コード移行、追加する本番設定はこの PR または対応する移行 PR でレビューします。

TypeScript は次を commit します。

```sh
git add package.json package-lock.json .project-preset.json
git commit -m "Update TypeScript project preset"
```

Python は次を commit します。

```sh
git add pyproject.toml uv.lock .project-preset.json .project-presets/ruff
git commit -m "Update Python project preset"
```

必要なアプリ変更も追加して branch を push し、PR を作ります。自動マージはせず、CI・Release notes・案件固有の変更を確認してマージします。

## 3. 更新 PR を自動で受け取る

[workflow サンプル](../examples/update-presets.yml) を利用側の `.github/workflows/update-presets.yml` に置き、既定 branch への PR をマージします。次は FastAPI の例です。

```yaml
name: Update preset packages
on:
  schedule:
    - cron: '15 2 * * 1'
  workflow_dispatch:
    inputs:
      version:
        description: 'Empty follows the current major'
        default: ''
        type: string
permissions:
  contents: write
  pull-requests: write
concurrency:
  group: update-preset-packages
  cancel-in-progress: false
jobs:
  update:
    uses: omitsuhashi/project-presets-demo/.github/workflows/update-consumer.yml@v1.4.0
    with:
      version: ${{ inputs.version || '' }}
      test-command: uv run --locked python -m unittest discover
```

TypeScript は `package.json` に `build` / `test` を設定し、追加検証が必要なら `test-command` に指定します。Django は標準の `manage.py check` / `test` を共通 script が実行します。必要な追加テストを同じ input に指定できます。monorepo は `directory: apps/api` など、対象 project の位置も指定します。

利用側 repository の Settings → Actions → General で「Allow GitHub Actions to create and approve pull requests」を有効にします。Organization の設定で制限されている場合は管理者が設定します。専用 PAT は不要で、workflow の `GITHUB_TOKEN` を使います。

毎週月曜 02:15 UTC（日本時間 11:15）、現在と同じ major の最新版で検証し、差分があれば更新 PR を作ります。Actions の手動実行でも version を指定できます。同じ Profile / 版の branch が既にあれば上書きしません。

`GITHUB_TOKEN` で作成した PR の `pull_request` workflow は承認待ちになるため、**必要な案件テストを `test-command` に指定して PR 作成前に実行し、PR でも必要な workflow を承認して確認してください。** [GitHub の trigger rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)。

サンプルをコピーするまでは利用側の自動更新は有効になりません。更新用 workflow の参照タグも固定されているため、新しい CLI 対応が必要な時はタグを更新します。同じ Profile が複数ディレクトリにある場合、現在の branch 名は Profile / 版で共通なので、手動 script でまとめて更新します。

## 4. マージ後に実行環境へ反映する

各開発環境・CI・デプロイでマージ済み commit を取得し、その commit の lock を使います。

```sh
# TypeScript
npm ci --allow-remote=root --ignore-scripts
# Python（開発 / CI）
uv sync --locked
# Python（実行用依存だけの環境）
uv sync --locked --no-dev
```

preset の更新だけでサーバーを再起動・再デプロイはしません。アプリの通常の build / test / deployment 手順で反映します。

配布元の lock だけが更新されても、利用側の間接依存は同じ版に揃いません。例えば Python の間接依存を個別に更新する場合は `uv lock --upgrade-package パッケージ名` と `uv sync --locked` を使い、lock の差分とアプリテストを別途レビューします。

## 5. 失敗時・適用後の復旧

更新全体はトランザクションではありません。途中の install / lint / test で失敗した場合も差分が残ることがあります。PR をマージせず、エラーと diff を確認します。設定の競合は案件側の上書きへ移すなど、原因を解消して再実行します。

更新 branch では、更新前の commit から manifest・lock・marker・管理設定を戻し、上記の `npm ci` / `uv sync --locked` で環境を復旧します。まだ更新を commit しておらず、更新前の作業を保存済みなら、次で追跡済みのファイルを `HEAD` に戻せます。

```sh
# TypeScript
git restore --source=HEAD -- package.json package-lock.json .project-preset.json
# Python
git restore --source=HEAD -- pyproject.toml uv.lock .project-preset.json .project-presets/ruff
```

更新で新規に作られた未追跡の管理設定は `git status` で確認して、そのファイルだけ取り除きます。アプリの未保存の変更を含めて `git reset --hard` する必要はありません。

マージ後は更新 commit を revert する PR を作ります。merge commit の場合は Git の通常の merge revert 手順を使います。元の manifest・lock・marker・管理設定を揃えて戻し、依存を再導入して `--check` とアプリテストを実行します。Git の revert は DB migration やデータを復旧しないため、そちらは案件の復旧手順を使います。

通常の一つの更新 commit なら、対象の SHA を確認して `PRESET_UPDATE_COMMIT` に設定した後、`git revert "$PRESET_UPDATE_COMMIT"` を使います。revert の変更も PR で検証・レビューします。
