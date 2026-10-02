# 配布側の更新・公開

配布側の保守担当者が、依存・共通設定を更新し、検証した固定版を GitHub Release に公開する手順です。公開後の適用は [利用側の更新](update.md) に従います。npm / PyPI への publish は行いません。

## 1. 更新候補と配布版を決める

[Dependabot](../.github/dependabot.yml) は npm・uv・GitHub Actions の更新候補を毎週 PR にします。手動で候補を選んでも同じ手順です。候補 PR のマージだけでは配布物は公開されません。

配布版は npm と Python で同じ `X.Y.Z` にします。

| 変更 | 配布版の判断 |
| --- | --- |
| 互換性を保つ修正・依存更新 | patch |
| 既存 Profile に影響しない新しい Profile | minor |
| 既存 CI を失敗させる lint、非互換な runtime / framework、管理対象の削除 | major、または利用側の移行を明示した別 Profile |

フレームワーク自身の版の数字だけで配布版を決めず、利用側への影響で判断します。例えば Django の feature 更新はアプリの migration / 非互換変更を確認します。

作業用 checkout の例です。既存 checkout があれば clone は省きます。

```sh
git clone https://github.com/omitsuhashi/project-presets-demo.git
cd project-presets-demo
git switch main
git pull --ff-only
git switch -c codex/update-presets
```

Node.js 24 / npm 12、uv 0.11.7、Python 3.12、Git、GitHub CLI を使います。push・PR・Release 操作には配布 repository への書き込み権限が必要です。

GitHub CLI 未認証なら `gh auth login` を行います。Git の push に HTTPS を使う場合は `gh auth setup-git` でその認証を使えます。

## 2. manifest・Profile・設定を揃える

更新候補に応じて次を変更します。

| 対象 | 同じ PR で変更する場所 |
| --- | --- |
| TypeScript / ESLint / Hono / Next.js / React / 型定義 | `profiles.json` の依存、`package.json` の検証用 `devDependencies`、該当する `peerDependencies` / 設定 |
| npm パッケージ自体が依存する共通 lint ツール | `package.json` の `dependencies`、必要な設定 |
| Ruff | `pyproject.toml` の `dependencies`、全 Python Profile の `devDependencies`、互換用 `profiles/python-scripts/requirements-dev.txt` |
| Django / FastAPI / Uvicorn | `pyproject.toml` の `optional-dependencies`、対応 Profile の `dependencies` |
| TypeScript の共通設定 | `typescript/` |
| Python の共通設定 | `python/project_presets_demo/config/` |
| CLI / 更新処理 | `scripts/apply-profile.mjs` / `python/project_presets_demo/__init__.py` / `scripts/update-consumer.py` |

Next.js と `eslint-config-next` は同じ版に揃えます。React・型定義、framework の Python / Node 要件も併せて確認します。新しい Profile を作る時は代表アプリと導入・更新テストも追加します。

manifest の更新には npm / uv の通常の操作を使えます。Python の例は、候補から選んだ版を `DJANGO_VERSION` に設定して実行します。

```sh
# DJANGO_VERSION に検証対象の実在する版を設定した後に実行する。
uv add --optional django "django==${DJANGO_VERSION}" --no-sync
# profiles.json の python-django の版も同じ値にする。
```

配布元の lockfile は配布元の検証環境を固定します。**その lockfile 自体は利用側にコピーされません。** 利用側へ配る固定版は package metadata / Profile に含めます。間接依存だけの lock 更新を利用側にも当てる場合は、利用側の lock 更新 PR を別途作って検証します。

## 3. 配布版と変更説明を更新する

次は `1.2.1` を準備する例です。公開済みかを確認し、未使用の版を選んでください。この例の実行は公開操作ではありません。

```sh
PRESET_RELEASE=1.2.1
npm version "$PRESET_RELEASE" --no-git-tag-version --ignore-scripts
uv version "$PRESET_RELEASE" --no-sync
npm install --package-lock-only --ignore-scripts --no-audit --no-fund
uv lock
```

`npm version` が `package.json` / `package-lock.json`、`uv version` が `pyproject.toml` / `uv.lock` の版を更新します。lockfile を文字列置換で編集しません。[npm version](https://docs.npmjs.com/cli/v12/commands/npm-version/)、[uv version](https://docs.astral.sh/uv/reference/cli/#uv-version)。

次も更新して同じ PR に含めます。

- `CHANGELOG.md`: 変更、互換性、対象 Profile、利用側で必要な作業。
- `README.md` / `docs/install.md` / `docs/update.md`: 推奨する配布版・依存の版・公開 URL・実行例。
- `.github/workflows/update-consumer.yml` の配布元 checkout の `ref` と、`examples/update-presets.yml` の reusable workflow の固定タグ: 新しい配布タグを指定。

新しいタグは CI 中には未公開ですが、通常の検証 workflow はこの reusable workflow を呼び出しません。配布物の公開後に、そのタグで利用側の workflow を実行します。新しい Profile や更新 CLI を使う利用側には、workflow の参照タグの更新も案内します。

## 4. 検証して PR をマージする

```sh
npm ci --ignore-scripts
uv lock --check
npm run lint
npm run demo:ts
npm run demo:py
uv run --locked ruff check --config python/base.toml python/project_presets_demo scripts/check-packages.py scripts/update-consumer.py
npm test
git diff --check
```

CI は catalog と manifest の版、Hono / Next.js、Python の各構成を検証します。wheel / tarball を実際に build して導入・更新し、lock、設定保持、手動変更の拒否、revert を確認します。更新後の Ruff / Node 型定義は現在の catalog の採用版を使います。テスト内の `1.0.0` / `2.0.0` は一時的な配布物であり、GitHub の公開版ではありません。

古い版を使うテスト用構成もあるため、非互換なルールや runtime を変更した時はその構成と移行テストも見直します。検証不能な互換性を前提に自動マージしません。

変更を commit / push して PR を作り、CI と変更説明を確認してマージします。GitHub の既定 branch は `main` です。公開は次のタグ操作で行います。

## 5. 検証した commit を公開する

PR のマージ後、`main` の CI 成功を確認してから実行します。`PRESET_RELEASE` は準備した版です。

```sh
git switch main
git pull --ff-only
PRESET_RELEASE=1.2.1
# npm と Python の版がこの値と一致することを確認する。
npm pkg get version
uv version --short
git tag "v${PRESET_RELEASE}"
git push origin "v${PRESET_RELEASE}"
```

[release workflow](../.github/workflows/release.yml) がタグと二つのパッケージ版の一致を確認し、lint・デモ・更新テストを再実行します。成功すると以下を build して draft Release に添付し、公開します。

- npm tarball: `project-presets-demo-X.Y.Z.tgz`
- Python wheel: `project_presets_demo-X.Y.Z-py3-none-any.whl`
- Python sdist: `project_presets_demo-X.Y.Z.tar.gz`
- `SHA256SUMS`

[GitHub Actions](https://github.com/omitsuhashi/project-presets-demo/actions/workflows/release.yml) でタグの実行が成功し、Release が公開されたことを確認します。公開した配布物をダウンロードして checksum と導入を確認します。

```sh
gh release view "v${PRESET_RELEASE}" --repo omitsuhashi/project-presets-demo
PRESET_ARTIFACTS="/tmp/project-presets-${PRESET_RELEASE}"
gh release download "v${PRESET_RELEASE}" --repo omitsuhashi/project-presets-demo --dir "$PRESET_ARTIFACTS"
(cd "$PRESET_ARTIFACTS" && shasum -a 256 -c SHA256SUMS)
```

[導入手順](install.md) の配布版をこの版に置き換え、TypeScript と Python の新規導入・`--check`・アプリテストを行います。旧版を導入した案件でも [更新手順](update.md) を試します。Release notes は該当する changelog の変更・互換性・移行方法を記載します。必要なら、その本文をファイルに保存して `gh release edit "v${PRESET_RELEASE}" --notes-file /path/to/release-notes.md` で反映します。

旧 Git 配布を保守する `release/v1` は、公開が成功した v1 系 commit だけに進めます。

```sh
# v1 系の公開が成功した後に実行する。v2 以降には使用しない。
git push origin "v${PRESET_RELEASE}:refs/heads/release/v1"
```

## 公開に失敗した時

タグを push しただけでは公開成功とは見なしません。Actions の失敗ログと `gh release view` を確認します。

- Release が未作成なら原因を解消し、同じ commit で再実行可能な処理だけを再実行します。ソース修正が必要なら新しい配布版を準備します。
- 未公開 draft が残った場合は、draft であることを確認して取り除いてから workflow を再実行します。公開済み Release にはこの操作をしません。
- 公開済みタグ・配布物の内容は差し替えません。公開後に問題が分かったら修正版を新しい版として配布し、利用側は更新または更新 PR の revert で復旧します。
