# 配布側の更新・公開

配布側の保守担当者が、依存・共通設定を更新し、検証した固定版を GitHub Release に公開する手順です。公開後の適用は [利用側の更新](update.md) に従います。npm / PyPI への publish は行いません。

## 1. 更新候補と配布版を決める

[Dependabot](../.github/dependabot.yml) は npm・uv・GitHub Actions の更新候補を毎週 PR にします。手動で候補を選んでも同じ手順です。候補 PR のマージだけでは配布物は公開されません。

配布版は言語ごとに独立して管理します。変更した言語だけ版を上げ、対応するタグだけ公開します。

| 言語 | 版の管理元 | 新しいタグ | 配布物 |
| --- | --- | --- | --- |
| TypeScript | `package.json` | `typescript-vX.Y.Z` | npm tarball |
| Python | `pyproject.toml` / `uv.lock` | `python-vX.Y.Z` | wheel / sdist |

2.1.0 以前の `vX.Y.Z` は統合配布として保持します。新規公開では使いません。この変更では両方に更新処理の変更があるため 2.2.0 を準備します。以後は一方だけ 2.2.1 に上げても、もう一方を 2.2.0 のままにできます。同じ言語の Node / Hono / Next、scripts / Django / FastAPI は現在一つのパッケージです。

テスト・手順書・CI だけの変更では利用側のパッケージ版を上げません。共通の更新 script / workflow テンプレートの動作を変えた場合は、その変更が必要な両言語を更新します。

| 変更 | 配布版の判断 |
| --- | --- |
| 互換性を保つ修正・依存更新 | patch |
| 互換性を保つ CLI 機能の追加、既存 Profile に影響しない新しい Profile | minor |
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

Node.js 24 / npm 12、uv 0.11.7、Python 3.12、Git、GitHub CLI を使います。内部の管理・検証・pack は pnpm 11.28.0 に固定します。Dependabot の `npm` ecosystem は pnpm lock も対象です。push・PR・Release 操作には配布 repository への書き込み権限が必要です。

GitHub CLI 未認証なら `gh auth login` を行います。Git の push に HTTPS を使う場合は `gh auth setup-git` でその認証を使えます。

pnpm 未導入でも固定版を使えるシェル関数を用意し、lock から導入します。

```sh
# pnpm 未導入でも、このターミナル内で固定版を一時実行できる。
pnpm() { npx --yes --ignore-scripts --package=pnpm@11.28.0 -- pnpm "$@"; }
pnpm install --frozen-lockfile --ignore-scripts
```

## 2. manifest・Profile・設定を揃える

更新候補に応じて次を変更します。

| 対象 | 同じ PR で変更する場所 |
| --- | --- |
| TypeScript / ESLint / Hono / Next.js / React / 型定義 | `profiles.json` の依存、`package.json` の `dependencies`（ESLint / TypeScript）または検証用 `devDependencies`、該当する `peerDependencies` / 設定 |
| npm パッケージ自体が依存する共通 lint ツール | `package.json` の `dependencies`、必要な設定 |
| pnpm | `package.json` の `dependencies.pnpm` / `packageManager`、CI と手順書の固定版。一時 CLI と利用側は同じ pnpm を使う |
| Ruff | `pyproject.toml` の `dependencies`、`python/profiles.json` の全 Profile の `devDependencies`、互換用 `profiles/python-scripts/requirements-dev.txt` |
| Django / FastAPI / Uvicorn | `pyproject.toml` の `optional-dependencies`、`python/profiles.json` の対応 Profile の `dependencies` |
| TypeScript の共通設定 | `typescript/` |
| Python の共通設定 | `python/project_presets_demo/config/` |
| CLI / 更新処理 | `scripts/apply-profile.mjs` / `python/project_presets_demo/__init__.py` / `scripts/update-consumer.py` |

Next.js と `eslint-config-next` は同じ版に揃えます。React・型定義、framework の Python / Node 要件も併せて確認します。新しい Profile を作る時は代表アプリと導入・更新テストも追加します。workflow の原本は `python/project_presets_demo/update-presets.yml` 一つで、npm tarball と Python wheel の両方に含まれます。既存利用側の同名 workflow は保持するため、必要な更新 script の移行は別途案内します。

manifest の更新には pnpm / uv の通常の操作を使えます。Python の例は、候補から選んだ版を `DJANGO_VERSION` に設定して実行します。

```sh
# DJANGO_VERSION に検証対象の実在する版を設定した後に実行する。
uv add --optional django "django==${DJANGO_VERSION}" --no-sync
# python/profiles.json の python-django の版も同じ値にする。
```

配布元の lockfile は配布元の検証環境を固定します。**その lockfile 自体は利用側にコピーされません。** 利用側へ配る固定版は package metadata / Profile に含めます。間接依存だけの lock 更新を利用側にも当てる場合は、利用側の lock 更新 PR を別途作って検証します。

## 3. 配布版と変更説明を更新する

次は TypeScript のみ `2.2.1` を準備する例です。公開済みかを確認し、未使用の版を選んでください。Python の版は変更しません。

```sh
PRESET_RELEASE=2.2.1
pnpm version "$PRESET_RELEASE" --no-git-tag-version --no-git-checks --config.ignore-scripts=true
pnpm install --lockfile-only --no-frozen-lockfile --ignore-scripts
```

Python の変更なら上記に代えて実行します。TypeScript の版は変更しません。

```sh
PRESET_RELEASE=2.2.1
uv version "$PRESET_RELEASE" --no-sync
uv lock
```

lockfile を文字列置換で編集しません。[pnpm](https://pnpm.io/cli/install)、[uv version](https://docs.astral.sh/uv/reference/cli/#uv-version)。`CHANGELOG.md` は言語・版・変更内容・移行作業を明記します。公開前の版を公開済みとして手順書に書きません。

workflow テンプレートの `PRESET_TAG` は CLI が対象言語の実行版に置き換え、reusable workflow と `provider-ref` の両方へ固定します。既存利用側の workflow は保持するため、参照の移行は [更新手順](update.md#言語別リリースへの移行) に従います。`.github/workflows/update-consumer.yml` の checkout は利用側が渡した `provider-ref` を使います。

## 4. 検証して PR をマージする

```sh
pnpm install --frozen-lockfile --ignore-scripts
uv lock --check
pnpm run lint
pnpm run demo:ts
pnpm run demo:py
uv run --locked ruff check --config python/base.toml python/project_presets_demo scripts/check-packages.py scripts/update-consumer.py scripts/check-release-routing.py
pnpm test
git diff --check
```

CI は catalog と manifest の版、Hono / Next.js、Python の各構成を検証します。wheel / tarball を実際に build して導入・更新し、lock、設定保持、手動変更の拒否、revert を確認します。更新後の Ruff / Node 型定義は現在の catalog の採用版を使います。テスト内の `1.0.0` / `2.0.0` は一時的な配布物です。実際に公開済みの 1.5.0 から npm → pnpm の移行・失敗時の lock 保持・revert も確認します。

古い版を使うテスト用構成もあるため、非互換なルールや runtime を変更した時はその構成と移行テストも見直します。検証不能な互換性を前提に自動マージしません。

変更を commit / push して PR を作り、CI と変更説明を確認してマージします。GitHub の既定 branch は `main` です。公開は次のタグ操作で行います。

## 5. 検証した commit を公開する

PR のマージ後、`main` の CI 成功を確認してから、変更した言語のタグだけ push します。TypeScript の例です。Python の公開なら `PRESET_LANGUAGE=python` にし、`uv version --short` で版を確認します。

```sh
git switch main
git pull --ff-only
PRESET_LANGUAGE=typescript
PRESET_RELEASE=2.2.1
node -p "JSON.parse(require('node:fs').readFileSync('package.json')).version"
PRESET_TAG="${PRESET_LANGUAGE}-v${PRESET_RELEASE}"
git tag "$PRESET_TAG"
git push origin "$PRESET_TAG"
```

[release workflow](../.github/workflows/release.yml) はタグと対象パッケージの版だけを照合し、既存の lint・デモ・更新テストを実行します。成功した場合、対象言語の配布物と `SHA256SUMS` だけを draft Release に添付して公開します。別言語の配布物は build / 公開しません。

[GitHub Actions](https://github.com/omitsuhashi/project-presets-demo/actions/workflows/release.yml) の成功と Release の公開を確認します。

```sh
gh release view "$PRESET_TAG" --repo omitsuhashi/project-presets-demo
PRESET_ARTIFACTS="/tmp/project-presets-${PRESET_TAG}"
gh release download "$PRESET_TAG" --repo omitsuhashi/project-presets-demo --dir "$PRESET_ARTIFACTS"
(cd "$PRESET_ARTIFACTS" && shasum -a 256 -c SHA256SUMS)
```

対象言語の `npx` / `uvx` で新規導入・更新・`--check`・アプリテストを行います。TypeScript の URL は `releases/download/typescript-vX.Y.Z/project-presets-demo-X.Y.Z.tgz`、Python は `releases/download/python-vX.Y.Z/project_presets_demo-X.Y.Z-py3-none-any.whl` です。

Release の全体の latest 表示は更新選択に使いません。利用側は対象言語のタグと配布物から同じ major の最新 stable 版を選びます。旧 `release/v1` はこの言語別タグで進めません。

## 公開に失敗した時

タグを push しただけでは公開成功とは見なしません。Actions の失敗ログと `gh release view` を確認します。

- Release が未作成なら原因を解消し、同じ commit で再実行可能な処理だけを再実行します。ソース修正が必要なら新しい配布版を準備します。
- 未公開 draft が残った場合は、draft であることを確認して取り除いてから workflow を再実行します。公開済み Release にはこの操作をしません。
- 公開済みタグ・配布物の内容は差し替えません。公開後に問題が分かったら修正版を新しい版として配布し、利用側は更新または更新 PR の revert で復旧します。
