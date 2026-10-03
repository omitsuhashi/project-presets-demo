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
| `--version 2.1.0` など明示 | 指定した公開版を選ぶ。major 更新は明示指定。TypeScript 1.x の適用には v1.5.0 の更新 script を使う |
| `--version` を省略 | 対象言語の配布物がある、現在と同じ major の最新 stable Release を選ぶ |
| Profile の変更 | アプリの移行が必要。通常の更新 CLI は停止する |

2.2.0 以降の更新 script は draft / prerelease・別言語・配布物が欠けた Release を採用しません。導入済みと同じ版なら、ファイル変更・再導入・PR 作成を行わず終了します。日常の CI 検証は案件側の workflow で行います。明示指定は `--version 2.2.0` と対象言語のタグ（例: `--version python-v2.2.0`）を使えます。

## 2. 手動で更新 PR を作る

### 一時取得した CLI で更新する

初回と同じ `npx` / `uvx` の入口を使えます。未 commit の作業を保存し、更新用 branch で、現在の Profile を変えずに新版を適用します。以下は Node.js / Python スクリプトの例です。Hono・Next.js・Django・FastAPI は marker の現在の Profile に置き換えます。

```sh
# pnpm 未導入でも、このターミナル内で固定版を一時実行できる。
pnpm() { npx --yes --ignore-scripts --package=pnpm@11.28.0 -- pnpm "$@"; }

git switch -c codex/update-project-preset
PRESET_VERSION=2.1.0
# TypeScript の案件で実行
npx --yes --allow-remote=root --ignore-scripts \
  "https://github.com/omitsuhashi/project-presets-demo/releases/download/v${PRESET_VERSION}/project-presets-demo-${PRESET_VERSION}.tgz" \
  typescript-node --setup
pnpm exec project-presets typescript-node --check
pnpm exec eslint .
pnpm exec tsc --noEmit
pnpm run --if-present build
pnpm run --if-present test

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
git clone --depth 1 --branch v2.1.0 \
  https://github.com/omitsuhashi/project-presets-demo.git ../preset-provider

git switch -c codex/update-project-preset
# 2.1.0 は公開済み版での例。採用する新版に置き換える。
uv run --no-project --python 3.12 python ../preset-provider/scripts/update-consumer.py \
  --directory . --version 2.1.0
```

script は版を導入してからその版の CLI で管理対象を更新するため、**更新 script に全体の preview モードはありません**。最初の導入 CLI の書き込みなし表示は、インストール済み版についての確認です。更新は branch 上で行い、diff とテストを確認します。

最新版を自動で選ぶ場合は `gh auth login` を済ませてから `--version` を省略します。自動選択でも major は上がりません。

```sh
uv run --no-project --python 3.12 python ../preset-provider/scripts/update-consumer.py --directory .
```

配布側が更新 script / 新しい Profile への対応をリリースした時は、配布元 checkout のタグもその公開済み版に更新します。package の版を変えるだけで更新用の script のコードは変わりません。

```sh
# PRESET_TOOL_VERSION を採用する公開済みのツール版に置き換える。
PRESET_TOOL_VERSION=2.1.0
git -C ../preset-provider fetch --depth 1 origin tag "v${PRESET_TOOL_VERSION}"
git -C ../preset-provider switch --detach "v${PRESET_TOOL_VERSION}"
```

### 自動で行う処理

| 言語 | 更新するもの | 実行する検証 |
| --- | --- | --- |
| TypeScript | 配布 tarball、Profile の依存、pnpm lock、marker | preset / lock の整合性、ESLint、`tsc --noEmit`、設定済みの `build` / `test` scripts |
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
git add package.json pnpm-lock.yaml .project-preset.json .github/workflows/update-presets.yml
git commit -m "Update TypeScript project preset"
```

Python は次を commit します。

```sh
git add pyproject.toml uv.lock .project-preset.json .project-presets/ruff .github/workflows/update-presets.yml
git commit -m "Update Python project preset"
```

必要なアプリ変更も追加して branch を push し、PR を作ります。自動マージはせず、CI・Release notes・案件固有の変更を確認してマージします。

### npm の 1.x から pnpm へ移行する

1.x の案件は同じ major を追うため、自動では 2.x に上がりません。上記の 2.1.0 の一時 CLI を使うか、2.1.0 の更新 script / workflow に `--version 2.1.0`（workflow input は `version: 2.1.0`）を指定します。`--setup` は `packageManager` を固定し、既存 `package-lock.json` / `npm-shrinkwrap.json` を pnpm の `import` で取り込み、最新 manifest で lock を生成します。frozen install と配布版確認が成功した後に npm lock を削除します。途中で失敗した場合は元の npm lock を保持します。

移行 PR には `pnpm-lock.yaml` の追加、npm lock の削除、manifest / marker、CI の install / build / test コマンド変更を含めます。削除も commit するため、前述の `git add` に加え、存在していた npm lock を `git add -u -- package-lock.json`（shrinkwrap があれば同様）で stage します。CI は固定 pnpm で `install --frozen-lockfile --ignore-scripts` を使います。pnpm の厳格な依存配置で、未宣言の依存に頼ったアプリはエラーになる場合があるため、必要な依存をアプリ側で明示して lint / 型チェック / build / test を通します。

移行前へ戻す場合は移行 commit を revert し、復元した npm lock で `npm ci --allow-remote=root --ignore-scripts` を実行します。未 commit の失敗なら Git から元の manifest / npm lock / marker を戻し、今回新規作成された未追跡の `pnpm-lock.yaml` だけを取り除いてから npm ci を行います。2.x の script は TypeScript 1.x の適用を変更前に停止します。1.x を継続する案件は v1.5.0 の script / workflow を使用してください。

Python は従来の uv 導入・更新のままです。共通の配布版番号は 2.1.0 に揃えています。

## 3. 更新 PR を自動で受け取る

`--setup` が `.github/workflows/update-presets.yml` を自動作成します。2.0.0 以前の導入済み案件でも、2.1.0 の CLI で同じ Profile の `--setup` を実行すると、依存の更新と一緒に追加します。手動コピーは不要です。生成された workflow を導入・更新 PR に含め、利用側の既定 branch にマージします。既存の同名ファイルは上書きしません。必要な追加テストを編集するため、次に FastAPI の例を示します。

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
    uses: omitsuhashi/project-presets-demo/.github/workflows/update-consumer.yml@v2.1.0
    with:
      version: ${{ inputs.version || '' }}
      test-command: uv run --locked python -m unittest discover
```

TypeScript は `package.json` に `build` / `test` を設定し、追加検証が必要なら `test-command` に指定します。Django は標準の `manage.py check` / `test` を共通 script が実行します。必要な追加テストを同じ input に指定できます。`directory: apps/api` などで独立した project の位置を指定できます。TypeScript CLI はそのディレクトリの lock を管理し、親 workspace を更新しません。共有 pnpm workspace lock や `workspace:` 依存がある案件は、その workspace の移行・更新を別途扱います。子 project に生成した workflow は repository ルートの `.github/workflows/` に移して `directory` を設定します。

利用側 repository の Settings → Actions → General で「Allow GitHub Actions to create and approve pull requests」を有効にします。Organization の設定で制限されている場合は管理者が設定します。専用 PAT は不要で、workflow の `GITHUB_TOKEN` を使います。

毎週月曜 02:15 UTC（日本時間 11:15）、現在と同じ major の最新版で検証し、差分があれば更新 PR を作ります。Actions の手動実行でも version を指定できます。同じ Profile / 版の branch が既にあれば上書きしません。

`GITHUB_TOKEN` で作成した PR の `pull_request` workflow は承認待ちになるため、**必要な案件テストを `test-command` に指定して PR 作成前に実行し、PR でも必要な workflow を承認して確認してください。** [GitHub の trigger rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)。

生成した workflow を既定 branch に commit / push し、Actions の PR 作成を許可するまでは自動更新は稼働しません。通常の依存・lint の新版は同じ major から自動で取得するため、配布版ごとの workflow 編集は不要です。更新用 workflow 自体の参照タグは固定して保持します。新しい更新 script 対応が必要な時だけ参照タグを別の PR で更新します。同じ Profile が複数ディレクトリにある場合、現在の branch 名は Profile / 版で共通なので、手動 script でまとめて更新します。

## 4. マージ後に実行環境へ反映する

各開発環境・CI・デプロイでマージ済み commit を取得し、その commit の lock を使います。

```sh
# TypeScript
# pnpm 未導入でも、このターミナル内で固定版を一時実行できる。
pnpm() { npx --yes --ignore-scripts --package=pnpm@11.28.0 -- pnpm "$@"; }
pnpm install --frozen-lockfile --ignore-scripts
# Python（開発 / CI）
uv sync --locked
# Python（実行用依存だけの環境）
uv sync --locked --no-dev
```

preset の更新だけでサーバーを再起動・再デプロイはしません。アプリの通常の build / test / deployment 手順で反映します。

配布元の lock だけが更新されても、利用側の間接依存は同じ版に揃いません。例えば Python の間接依存を個別に更新する場合は `uv lock --upgrade-package パッケージ名` と `uv sync --locked` を使い、lock の差分とアプリテストを別途レビューします。

## 5. 失敗時・適用後の復旧

更新全体はトランザクションではありません。途中の install / lint / test で失敗した場合も差分が残ることがあります。PR をマージせず、エラーと diff を確認します。設定の競合は案件側の上書きへ移すなど、原因を解消して再実行します。

更新 branch では、更新前の commit から manifest・lock・marker・管理設定を戻し、上記の `pnpm install --frozen-lockfile --ignore-scripts` / `uv sync --locked` で環境を復旧します。2.0.0 以前へ戻す場合、今回新しく追加した workflow も戻す対象に含めます。まだ更新を commit しておらず、更新前の作業を保存済みなら、次で追跡済みのファイルを `HEAD` に戻せます。

```sh
# TypeScript
git restore --source=HEAD -- package.json pnpm-lock.yaml .project-preset.json
# Python
git restore --source=HEAD -- pyproject.toml uv.lock .project-preset.json .project-presets/ruff
```

更新で新規に作られた未追跡の管理設定は `git status` で確認して、そのファイルだけ取り除きます。アプリの未保存の変更を含めて `git reset --hard` する必要はありません。

マージ後は更新 commit を revert する PR を作ります。merge commit の場合は Git の通常の merge revert 手順を使います。元の manifest・lock・marker・管理設定を揃えて戻し、依存を再導入して `--check` とアプリテストを実行します。Git の revert は DB migration やデータを復旧しないため、そちらは案件の復旧手順を使います。

通常の一つの更新 commit なら、対象の SHA を確認して `PRESET_UPDATE_COMMIT` に設定した後、`git revert "$PRESET_UPDATE_COMMIT"` を使います。revert の変更も PR で検証・レビューします。

## 言語別リリースへの移行

2.2.0 はこの変更で準備する未公開版です。TypeScript の `typescript-v2.2.0`、Python の `python-v2.2.0` がそれぞれ公開された後に実行します。以後、別言語の Release では対象案件の版を上げません。`v2.1.0` 以前の統合配布も新しい updater で引き続き適用できます。

既存の `update-consumer.yml@v2.1.0` は古い updater を使い、言語別タグを検索しません。`--setup` は案件所有の workflow を保持するため、`.github/workflows/update-presets.yml` の以下の部分を手動で移行して commit します。schedule・directory・アプリテストは案件の設定を保持します。

```yaml
jobs:
  update:
    # Python では uses と provider-ref の両方を python-v2.2.0 にする。
    uses: omitsuhashi/project-presets-demo/.github/workflows/update-consumer.yml@typescript-v2.2.0
    with:
      provider-ref: typescript-v2.2.0
      version: ${{ inputs.version || '' }}
```

手動で更新 script を使う場合も checkout を対象言語の公開タグへ更新します。裸の版番号は 2.2.0 以降の言語別タグに解決されます。major 更新と downgrade は版を明示した時だけ行います。

```sh
# Python の例。TypeScript は typescript-v2.2.0 にする。
git -C ../preset-provider fetch origin tag python-v2.2.0
git -C ../preset-provider switch --detach python-v2.2.0
uv run --no-project --python 3.12 python ../preset-provider/scripts/update-consumer.py --directory .
```
